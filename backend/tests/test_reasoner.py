from pathlib import Path

from app import reasoner


def test_analyze_finding_skips_llm_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    finding = {"file": "a.py", "line": 1, "type": "x", "rule": "r", "severity": "LOW"}

    result = reasoner.analyze_finding(finding, tmp_path)

    assert result["ai_verdict"] == "NEEDS_TESTING"
    assert "skipped" in result["ai_explanation"].lower()


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
