"""Level 3 — AI Cyber Reasoning Engine.

Sends each static-analysis finding, plus a small window of surrounding source,
to Claude for root-cause analysis and a verdict. Never scans the whole repo
with the LLM — it only reasons about findings Semgrep already flagged.

If no ANTHROPIC_API_KEY is configured the reasoning step is skipped and the
finding is left as NEEDS_TESTING, so the rest of the pipeline still runs.
"""
import os
from pathlib import Path

VERDICTS = {"CONFIRMED", "REJECTED", "NEEDS_TESTING"}

SYSTEM_PROMPT = """You are a security code reviewer. You are given ONE static \
analysis finding plus the surrounding source code. Do not look for other \
vulnerabilities — only assess this specific finding.

Respond in exactly this format, nothing else:

VERDICT: <CONFIRMED|REJECTED|NEEDS_TESTING>
EXPLANATION: <2-4 sentences: root cause, whether user-controlled data reaches \
the sink, and why you reached this verdict>"""


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


def analyze_finding(finding: dict, target_dir: Path) -> dict:
    """Returns {'ai_verdict': ..., 'ai_explanation': ...}."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "ai_verdict": "NEEDS_TESTING",
            "ai_explanation": "LLM reasoning skipped: ANTHROPIC_API_KEY is not configured.",
        }

    context = _read_context(target_dir, finding["file"], finding["line"])
    user_prompt = (
        f"Finding type: {finding['type']}\n"
        f"Rule: {finding['rule']}\n"
        f"Severity: {finding['severity']}\n"
        f"File: {finding['file']} line {finding['line']}\n\n"
        f"Evidence:\n{finding.get('evidence', '')}\n\n"
        f"Surrounding source:\n{context}"
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text
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
