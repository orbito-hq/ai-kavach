import io
import zipfile

from app import db, intake, reasoner
from app.pipeline.build import build_orchestrator
from app.pipeline.context import ScanContext
from app.pipeline.logging_utils import get_scan_logger


def make_zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_build_orchestrator_wires_expected_steps():
    orchestrator = build_orchestrator()

    names = [s.name for s in orchestrator._steps]
    assert names == ["intake", "detect_languages", "static_analysis", "ai_reasoning", "persist_findings"]
    assert orchestrator._cleanup_step.name == "cleanup"


async def test_full_pipeline_end_to_end_without_llm_key(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kavach.db")
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path / "workspaces")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    reasoner.reset_gemini_pool()

    db.init_db(tmp_path / "kavach.db")
    scan_id = "pipeline-e2e-1"
    db.create_scan(scan_id, "target.zip", "2026-08-30T00:00:00Z")

    zip_bytes = make_zip_bytes({
        "runner.py": "import subprocess\nsubprocess.run(user_input, shell=True)\n",
    })
    ctx = ScanContext(
        scan_id=scan_id, source="target.zip", zip_bytes=zip_bytes, repo_url=None,
        logger=get_scan_logger(scan_id),
    )

    await build_orchestrator().run(ctx)

    scan = db.get_scan(scan_id)
    assert scan["status"] == "COMPLETED"
    findings = db.list_findings(scan_id)
    assert len(findings) == 1
    assert findings[0]["type"] == "CWE-78: OS Command Injection"
    assert findings[0]["ai_verdict"] == "NEEDS_TESTING"
