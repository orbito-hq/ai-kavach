"""Per-scan structured logging (Level 14 evidence / Level 18 observability).

Every step transition, retry, and failure for a scan is written to its own
log file, so the "why did this scan fail / take so long" question always
has an answer without re-running anything.
"""
import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def get_scan_logger(scan_id: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"kavach.scan.{scan_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(LOG_DIR / f"{scan_id}.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def read_scan_log(scan_id: str) -> str:
    path = LOG_DIR / f"{scan_id}.log"
    return path.read_text() if path.exists() else ""
