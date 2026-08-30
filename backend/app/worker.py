"""Consumer entry point for `rq worker kavach-scans`.

Runs the exact same ScanOrchestrator the inline (BackgroundTasks) path
uses (see app/pipeline/build.py) — the only difference between the two
modes is who invokes it and whether the job survives a crash/restart, not
what work gets done.
"""
import asyncio

from app.pipeline.build import build_orchestrator
from app.pipeline.context import ScanContext
from app.pipeline.logging_utils import get_scan_logger


def process_scan_job(scan_id: str, source: str, zip_bytes: bytes | None, repo_url: str | None):
    ctx = ScanContext(
        scan_id=scan_id,
        source=source,
        zip_bytes=zip_bytes,
        repo_url=repo_url,
        logger=get_scan_logger(scan_id),
    )
    asyncio.run(build_orchestrator().run(ctx))
