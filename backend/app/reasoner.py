"""Level 3 — AI Cyber Reasoning Engine.

Sends each static-analysis finding, plus a small window of surrounding source,
to an LLM for root-cause analysis and a verdict. Never scans the whole repo
with the LLM — it only reasons about findings Semgrep already flagged.

Provider selection (checked in this order):
  1. Gemini, if GEMINI_API_KEY or GEMINI_API_KEYS is set — supports rotating
     across multiple keys to ride out rate limits / parallel calls, via an
     async jittered-backoff state machine (see app.llm.gemini).
  2. Anthropic (Claude), if ANTHROPIC_API_KEY is set.
  3. Otherwise reasoning is skipped and the finding is left as
     NEEDS_TESTING, so the rest of the pipeline still runs.

Everything here is async so a finding backing off from a rate limit never
blocks another finding's reasoning call, or the rest of the process.
"""
import asyncio
import os
import threading
from pathlib import Path

from app.llm import gemini

VERDICTS = {"CONFIRMED", "REJECTED", "NEEDS_TESTING"}

SYSTEM_PROMPT = """You are a security code reviewer. You are given ONE static \
analysis finding plus the surrounding source code. Do not look for other \
vulnerabilities — only assess this specific finding.

Respond in exactly this format, nothing else:

VERDICT: <CONFIRMED|REJECTED|NEEDS_TESTING>
EXPLANATION: <2-4 sentences: root cause, whether user-controlled data reaches \
the sink, and why you reached this verdict>"""

_gemini_pool = None
_gemini_pool_lock = threading.Lock()


def _get_gemini_pool():
    """Built lazily (and cached) from the current env, so a single process
    only pays for constructing the pool once."""
    global _gemini_pool
    with _gemini_pool_lock:
        if _gemini_pool is None:
            keys = gemini.load_keys_from_env()
            if keys:
                _gemini_pool = gemini.GeminiKeyPool(keys)
        return _gemini_pool


def reset_gemini_pool():
    """Test hook: force the pool to be rebuilt from env on next use."""
    global _gemini_pool
    with _gemini_pool_lock:
        _gemini_pool = None


def max_concurrency() -> int:
    """How many findings the pipeline may reason about in parallel. With a
    Gemini key pool this scales with the number of keys (each key can have
    a call in flight at once); otherwise a small fixed concurrency is used
    so a single-key/Anthropic setup doesn't self-inflict a rate limit."""
    pool = _get_gemini_pool()
    if pool is not None:
        return max(1, pool.key_count)
    return 4


def _read_context(target_dir: Path, rel_path: str, line: int, window: int = 15) -> str:
    file_path = target_dir / rel_path
    try:
        lines = file_path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    start = max(0, line - window - 1)
    end = min(len(lines), line + window)
    numbered = [f"{i + 1}: {lines[i]}" for i in range(start, end)]
    return "\n".join(numbered)


def _build_user_prompt(finding: dict, target_dir: Path) -> str:
    context = _read_context(target_dir, finding["file"], finding["line"])
    return (
        f"Finding type: {finding['type']}\n"
        f"Rule: {finding['rule']}\n"
        f"Severity: {finding['severity']}\n"
        f"File: {finding['file']} line {finding['line']}\n\n"
        f"Evidence:\n{finding.get('evidence', '')}\n\n"
        f"Surrounding source:\n{context}"
    )


async def analyze_finding(finding: dict, target_dir: Path) -> dict:
    """Returns {'ai_verdict': ..., 'ai_explanation': ...}."""
    gemini_pool = _get_gemini_pool()
    if gemini_pool is not None:
        return await _analyze_with_gemini(finding, target_dir, gemini_pool)

    if os.environ.get("ANTHROPIC_API_KEY"):
        return await _analyze_with_anthropic(finding, target_dir)

    return {
        "ai_verdict": "NEEDS_TESTING",
        "ai_explanation": "LLM reasoning skipped: no GEMINI_API_KEY(S) or ANTHROPIC_API_KEY configured.",
    }


async def _analyze_with_gemini(finding: dict, target_dir: Path, pool) -> dict:
    user_prompt = _build_user_prompt(finding, target_dir)
    try:
        text = await pool.generate_content(SYSTEM_PROMPT, user_prompt, max_output_tokens=400)
        return _parse_response(text)
    except gemini.GeminiError as e:
        return {
            "ai_verdict": "NEEDS_TESTING",
            "ai_explanation": f"LLM reasoning failed: {e}",
        }


def _call_anthropic_sync(user_prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


async def _analyze_with_anthropic(finding: dict, target_dir: Path) -> dict:
    user_prompt = _build_user_prompt(finding, target_dir)
    try:
        # The Anthropic SDK call is blocking; run it off the event loop so a
        # slow request doesn't stall every other coroutine in the process.
        text = await asyncio.to_thread(_call_anthropic_sync, user_prompt)
        return _parse_response(text)
    except Exception as e:  # LLM/network failures shouldn't crash the pipeline
        return {
            "ai_verdict": "NEEDS_TESTING",
            "ai_explanation": f"LLM reasoning failed: {e}",
        }


def _parse_response(text: str) -> dict:
    verdict = "NEEDS_TESTING"
    explanation = text.strip()
    for line in text.splitlines():
        if line.upper().startswith("VERDICT:"):
            candidate = line.split(":", 1)[1].strip().upper()
            if candidate in VERDICTS:
                verdict = candidate
        if line.upper().startswith("EXPLANATION:"):
            explanation = line.split(":", 1)[1].strip()
    return {"ai_verdict": verdict, "ai_explanation": explanation}
