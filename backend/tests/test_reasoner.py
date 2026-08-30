import httpx
import pytest

from app import reasoner
from app.llm import gemini


@pytest.fixture(autouse=True)
def _clear_env_and_pool(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    # keep failure-path tests fast: small backoff instead of the real ~60s cap
    monkeypatch.setattr(gemini, "MAX_BACKOFF_SECONDS", 0.05)
    monkeypatch.setattr(gemini, "BASE_BACKOFF_SECONDS", 0.01)
    reasoner.reset_gemini_pool()
    yield
    reasoner.reset_gemini_pool()


async def test_analyze_finding_skips_llm_without_any_key(tmp_path):
    finding = {"file": "a.py", "line": 1, "type": "x", "rule": "r", "severity": "LOW"}

    result = await reasoner.analyze_finding(finding, tmp_path)

    assert result["ai_verdict"] == "NEEDS_TESTING"
    assert "skipped" in result["ai_explanation"].lower()


async def test_analyze_finding_uses_gemini_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    finding = {"file": "a.py", "line": 1, "type": "x", "rule": "r", "severity": "LOW"}

    async def fake_post(self, url, headers=None, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "VERDICT: CONFIRMED\nEXPLANATION: root cause found"}]}}
                ]
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await reasoner.analyze_finding(finding, tmp_path)

    assert result["ai_verdict"] == "CONFIRMED"
    assert result["ai_explanation"] == "root cause found"


async def test_analyze_finding_reports_gemini_failure_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    finding = {"file": "a.py", "line": 1, "type": "x", "rule": "r", "severity": "LOW"}

    async def fake_post(self, url, headers=None, json=None):
        request = httpx.Request("POST", url)
        return httpx.Response(500, json={}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await reasoner.analyze_finding(finding, tmp_path)

    assert result["ai_verdict"] == "NEEDS_TESTING"
    assert "failed" in result["ai_explanation"].lower()


def test_max_concurrency_scales_with_gemini_key_count(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "a,b,c")
    assert reasoner.max_concurrency() == 3


def test_max_concurrency_defaults_without_gemini():
    assert reasoner.max_concurrency() == 4


def test_parse_response_extracts_verdict_and_explanation():
    text = "VERDICT: CONFIRMED\nEXPLANATION: User input flows directly into subprocess."

    result = reasoner._parse_response(text)

    assert result["ai_verdict"] == "CONFIRMED"
    assert result["ai_explanation"] == "User input flows directly into subprocess."


def test_parse_response_falls_back_on_invalid_verdict():
    text = "VERDICT: MAYBE\nEXPLANATION: unclear"

    result = reasoner._parse_response(text)

    assert result["ai_verdict"] == "NEEDS_TESTING"


def test_read_context_returns_windowed_lines(tmp_path):
    file_path = tmp_path / "a.py"
    file_path.write_text("\n".join(f"line{i}" for i in range(1, 51)))

    context = reasoner._read_context(tmp_path, "a.py", 25, window=2)

    assert "23: line23" in context
    assert "27: line27" in context
    assert "1: line1" not in context
