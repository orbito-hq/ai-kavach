from app import db


def test_scan_and_finding_lifecycle(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    db.create_scan("scan-1", "https://example.com/repo.git", "2026-08-29T00:00:00Z", db_path)
    scan = db.get_scan("scan-1", db_path)
    assert scan["status"] == "PENDING"
    assert scan["source"] == "https://example.com/repo.git"

    db.update_scan("scan-1", db_path, status="RUNNING", languages={"Python": 3})
    scan = db.get_scan("scan-1", db_path)
    assert scan["status"] == "RUNNING"
    assert "Python" in scan["languages"]

    db.add_finding(
        {
            "id": "f-1",
            "scan_id": "scan-1",
            "type": "CWE-78",
            "severity": "CRITICAL",
            "file": "src/runner.py",
            "line": 42,
            "evidence": "subprocess.run(user_input)",
            "rule": "python.lang.security.dangerous-subprocess",
            "confidence": "HIGH",
            "ai_verdict": "CONFIRMED",
            "ai_explanation": "User input reaches subprocess without sanitization.",
        },
        db_path,
    )

    findings = db.list_findings("scan-1", db_path)
    assert len(findings) == 1
    assert findings[0]["ai_verdict"] == "CONFIRMED"

    fetched = db.get_finding("f-1", db_path)
    assert fetched["file"] == "src/runner.py"

    db.update_scan("scan-1", db_path, status="COMPLETED")
    assert db.get_scan("scan-1", db_path)["status"] == "COMPLETED"

    scans = db.list_scans(db_path)
    assert len(scans) == 1
