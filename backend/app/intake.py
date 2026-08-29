"""Level 1 — Target Intake: accept a repo (git URL or ZIP), validate, extract,
and do lightweight language detection."""
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "workspaces"

EXT_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".java": "Java", ".go": "Go", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".rs": "Rust",
}

IGNORED_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}


class IntakeError(ValueError):
    pass


def workspace_dir(scan_id: str) -> Path:
    return WORKSPACE_ROOT / scan_id


def prepare_from_zip(scan_id: str, zip_bytes: bytes) -> Path:
    target = workspace_dir(scan_id)
    target.mkdir(parents=True, exist_ok=True)
    zip_path = target / "upload.zip"
    zip_path.write_bytes(zip_bytes)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                member_path = (target / member).resolve()
                if not str(member_path).startswith(str(target.resolve())):
                    raise IntakeError("Zip contains an unsafe path traversal entry")
            zf.extractall(target)
    except zipfile.BadZipFile as e:
        raise IntakeError(f"Not a valid zip file: {e}") from e
    finally:
        zip_path.unlink(missing_ok=True)

    return target


def prepare_from_git(scan_id: str, repo_url: str) -> Path:
    if not (repo_url.startswith("https://") or repo_url.startswith("git://")):
        raise IntakeError("Only https:// or git:// repo URLs are supported")
    target = workspace_dir(scan_id)
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise IntakeError(f"git clone failed: {result.stderr.strip()}")
    return target


def detect_languages(root: Path) -> dict:
    counts = Counter()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        lang = EXT_LANGUAGE.get(path.suffix.lower())
        if lang:
            counts[lang] += 1
    return dict(counts.most_common())


def cleanup(scan_id: str):
    shutil.rmtree(workspace_dir(scan_id), ignore_errors=True)
