import io
import zipfile

from fastapi.testclient import TestClient

from app import db, main, reasoner


def make_zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_full_scan_lifecycle_via_api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kavach.db")
    monkeypatch.setattr(main.db, "DB_PATH", tmp_path / "kavach.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    reasoner.reset_gemini_pool()

    from app import intake
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path / "workspaces")

    with TestClient(main.app) as client:
        zip_bytes = make_zip_bytes({
            "runner.py": "import subprocess\nsubprocess.run(input(), shell=True)\n",
        })

        resp = client.post(
            "/api/scans",
            files={"file": ("target.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 200
        scan_id = resp.json()["scan_id"]

        scan = client.get(f"/api/scans/{scan_id}").json()
        assert scan["status"] in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}

        findings = client.get(f"/api/scans/{scan_id}/findings").json()
        assert isinstance(findings, list)

        assert client.get("/api/scans/does-not-exist").status_code == 404
        assert client.get("/api/scans/does-not-exist/findings").status_code == 404
        assert client.get("/api/findings/does-not-exist").status_code == 404


def test_create_scan_requires_source(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kavach.db")
    monkeypatch.setattr(main.db, "DB_PATH", tmp_path / "kavach.db")
    with TestClient(main.app) as client:
        resp = client.post("/api/scans", data={})
        assert resp.status_code == 400
