"""SQLite persistence for scan and finding metadata (Level 0.2 / Level 2 output)."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "kavach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    languages TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    file TEXT NOT NULL,
    line INTEGER NOT NULL,
    evidence TEXT,
    rule TEXT,
    confidence TEXT,
    ai_verdict TEXT,
    ai_explanation TEXT
);
"""


@contextmanager
def get_conn(db_path: Path = None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = None):
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def create_scan(scan_id: str, source: str, created_at: str, db_path: Path = None):
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO scans (id, source, status, languages, error, created_at) "
            "VALUES (?, ?, 'PENDING', NULL, NULL, ?)",
            (scan_id, source, created_at),
        )


def update_scan(scan_id: str, db_path: Path = None, **fields):
    if not fields:
        return
    if "languages" in fields and isinstance(fields["languages"], dict):
        fields["languages"] = json.dumps(fields["languages"])
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [scan_id]
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE scans SET {columns} WHERE id = ?", values)


def get_scan(scan_id: str, db_path: Path = None):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return dict(row) if row else None


def list_scans(db_path: Path = None):
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM scans ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def add_finding(finding: dict, db_path: Path = None):
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO findings (id, scan_id, type, severity, file, line, evidence, "
            "rule, confidence, ai_verdict, ai_explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding["id"],
                finding["scan_id"],
                finding["type"],
                finding["severity"],
                finding["file"],
                finding["line"],
                finding.get("evidence"),
                finding.get("rule"),
                finding.get("confidence"),
                finding.get("ai_verdict"),
                finding.get("ai_explanation"),
            ),
        )


def update_finding(finding_id: str, db_path: Path = None, **fields):
    if not fields:
        return
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [finding_id]
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE findings SET {columns} WHERE id = ?", values)


def list_findings(scan_id: str, db_path: Path = None):
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM findings WHERE scan_id = ? ORDER BY "
            "CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 "
            "WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END",
            (scan_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_finding(finding_id: str, db_path: Path = None):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        return dict(row) if row else None
