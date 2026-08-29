"""MVP1 pipeline: Repository -> Semgrep -> LLM -> Vulnerability Report."""
from pathlib import Path

from app import db, intake, reasoner
from app.scanner import ScanError, run_semgrep


def run_scan(scan_id: str, source: str, zip_bytes: bytes | None, repo_url: str | None):
    db.update_scan(scan_id, status="RUNNING")
    try:
        if zip_bytes is not None:
            target_dir = intake.prepare_from_zip(scan_id, zip_bytes)
        else:
            target_dir = intake.prepare_from_git(scan_id, repo_url)

        languages = intake.detect_languages(target_dir)
        db.update_scan(scan_id, languages=languages)

        findings = run_semgrep(target_dir)
        for finding in findings:
            finding["scan_id"] = scan_id
            ai_result = reasoner.analyze_finding(finding, target_dir)
            finding.update(ai_result)
            db.add_finding(finding)

        db.update_scan(scan_id, status="COMPLETED")
    except (intake.IntakeError, ScanError) as e:
        db.update_scan(scan_id, status="FAILED", error=str(e))
    except Exception as e:  # pragma: no cover - safety net for unexpected errors
        db.update_scan(scan_id, status="FAILED", error=f"Unexpected error: {e}")
    finally:
        intake.cleanup(scan_id)
