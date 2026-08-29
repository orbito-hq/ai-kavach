from pathlib import Path

from app.scanner import normalize


def test_normalize_maps_severity_and_fields():
    target_dir = Path("/workspace/scan-1")
    raw = {
        "check_id": "python.lang.security.dangerous-subprocess-use",
        "path": "/workspace/scan-1/src/runner.py",
        "start": {"line": 42},
        "extra": {
            "severity": "ERROR",
            "lines": "subprocess.run(user_input, shell=True)",
            "metadata": {"cwe": ["CWE-78: OS Command Injection"], "confidence": "HIGH"},
        },
    }

    finding = normalize(raw, target_dir)

    assert finding["severity"] == "CRITICAL"
    assert finding["file"] == "src/runner.py"
    assert finding["line"] == 42
    assert finding["confidence"] == "HIGH"
    assert finding["type"] == "CWE-78: OS Command Injection"
    assert "id" in finding


def test_normalize_defaults_when_metadata_missing():
    target_dir = Path("/workspace/scan-2")
    raw = {
        "check_id": "generic.rule",
        "path": "/workspace/scan-2/a.py",
        "start": {"line": 1},
        "extra": {"severity": "INFO", "lines": "", "metadata": {}},
    }

    finding = normalize(raw, target_dir)

    assert finding["severity"] == "LOW"
    assert finding["type"] == "generic.rule"
    assert finding["confidence"] == "MEDIUM"
