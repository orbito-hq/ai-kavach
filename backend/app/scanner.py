"""Level 2 — Static Analysis: run Semgrep and normalize findings."""
import json
import subprocess
import uuid
from pathlib import Path

SEVERITY_MAP = {
    "ERROR": "CRITICAL",
    "WARNING": "MEDIUM",
    "INFO": "LOW",
}


RULES_PATH = Path(__file__).resolve().parent / "rules" / "security.yaml"


class ScanError(RuntimeError):
    pass


def run_semgrep(target_dir: Path, timeout: int = 300) -> list[dict]:
    """Run semgrep against a bundled offline ruleset and return normalized
    findings. A local rule file is used (rather than --config=auto) so scans
    are reproducible and don't depend on network access to the Semgrep
    registry (Level 18 reproducibility goal).

    --no-git-ignore is required because semgrep walks upward looking for a
    .gitignore even when the scanned target itself isn't a git repo — our
    own workspaces/ directory is gitignored in this project's own
    .gitignore, which would otherwise cause every scan to silently return
    zero findings."""
    try:
        result = subprocess.run(
            [
                "semgrep", "scan", f"--config={RULES_PATH}", "--json", "--quiet",
                "--metrics=off", "--no-git-ignore", str(target_dir),
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise ScanError("semgrep is not installed in this environment") from e
    except subprocess.TimeoutExpired as e:
        raise ScanError(f"semgrep timed out after {timeout}s") from e

    if not result.stdout.strip():
        if result.returncode not in (0, 1):
            raise ScanError(f"semgrep failed: {result.stderr[-2000:]}")
        return []

    payload = json.loads(result.stdout)
    return [normalize(r, target_dir) for r in payload.get("results", [])]


def normalize(raw: dict, target_dir: Path) -> dict:
    severity = SEVERITY_MAP.get(raw.get("extra", {}).get("severity", "INFO"), "LOW")
    metadata = raw.get("extra", {}).get("metadata", {})
    rel_path = str(Path(raw["path"]).relative_to(target_dir)) if Path(raw["path"]).is_absolute() else raw["path"]
    return {
        "id": str(uuid.uuid4()),
        "type": metadata.get("cwe", [raw.get("check_id", "unknown")])[0]
        if isinstance(metadata.get("cwe"), list) else raw.get("check_id", "unknown"),
        "severity": severity,
        "file": rel_path,
        "line": raw.get("start", {}).get("line", 0),
        "evidence": raw.get("extra", {}).get("lines", "").strip()[:2000],
        "rule": raw.get("check_id", ""),
        "confidence": metadata.get("confidence", "MEDIUM"),
    }
