"""Mutable state threaded through pipeline steps.

Steps depend on this shape, not on each other (Dependency Inversion) — a
step reads what it needs off the context and writes its own output back
onto it, so steps can be reordered, swapped, or added without touching
other steps.
"""
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path


@dataclass
class ScanContext:
    scan_id: str
    source: str
    zip_bytes: bytes | None
    repo_url: str | None
    logger: Logger
    target_dir: Path | None = None
    languages: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
