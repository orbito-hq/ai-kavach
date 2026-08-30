import logging

import pytest

from app import db
from app.intake import IntakeError
from app.pipeline import orchestrator as orch_module
from app.pipeline.context import ScanContext
from app.pipeline.orchestrator import ScanOrchestrator
from app.scanner import ScanError


class FakeStep:
    def __init__(self, name, outcomes):
        """outcomes: list of exceptions to raise (or None to succeed), one per call."""
        self.name = name
        self._outcomes = list(outcomes)
        self.calls = 0

    async def run(self, ctx):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kavach.db")
    db.init_db(tmp_path / "kavach.db")
    db.create_scan("scan-x", "test.zip", "2026-08-30T00:00:00Z")
    return ScanContext(
        scan_id="scan-x", source="test.zip", zip_bytes=b"", repo_url=None,
        logger=logging.getLogger("test-orchestrator"),
    )


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    monkeypatch.setattr(orch_module, "BASE_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr(orch_module, "MAX_BACKOFF_SECONDS", 0.02)


async def test_all_steps_succeed_marks_scan_completed(ctx):
    steps = [FakeStep("a", [None]), FakeStep("b", [None])]
    orchestrator = ScanOrchestrator(steps=steps, cleanup_step=None)

    await orchestrator.run(ctx)

    assert db.get_scan("scan-x")["status"] == "COMPLETED"
    assert steps[0].calls == 1
    assert steps[1].calls == 1


async def test_transient_error_is_retried_then_succeeds(ctx):
    flaky = FakeStep("flaky", [ScanError("boom"), None])
    orchestrator = ScanOrchestrator(steps=[flaky], cleanup_step=None)

    await orchestrator.run(ctx)

    assert db.get_scan("scan-x")["status"] == "COMPLETED"
    assert flaky.calls == 2


async def test_transient_error_exhausts_retries_and_fails_scan(ctx):
    always_fails = FakeStep("always-fails", [ScanError("1"), ScanError("2"), ScanError("3")])
    orchestrator = ScanOrchestrator(steps=[always_fails], cleanup_step=None)

    await orchestrator.run(ctx)

    scan = db.get_scan("scan-x")
    assert scan["status"] == "FAILED"
    assert "3" in scan["error"]
    assert always_fails.calls == 3  # MAX_STEP_RETRIES=2 -> 1 initial + 2 retries


async def test_fatal_error_fails_immediately_without_retry(ctx):
    fatal = FakeStep("fatal", [IntakeError("bad zip")])
    orchestrator = ScanOrchestrator(steps=[fatal], cleanup_step=None)

    await orchestrator.run(ctx)

    scan = db.get_scan("scan-x")
    assert scan["status"] == "FAILED"
    assert "bad zip" in scan["error"]
    assert fatal.calls == 1  # no retry for fatal errors


async def test_cleanup_step_always_runs_even_on_failure(ctx):
    fatal = FakeStep("fatal", [IntakeError("bad zip")])
    cleanup = FakeStep("cleanup", [None])
    orchestrator = ScanOrchestrator(steps=[fatal], cleanup_step=cleanup)

    await orchestrator.run(ctx)

    assert cleanup.calls == 1


async def test_cleanup_step_failure_does_not_override_scan_status(ctx):
    class BrokenCleanup:
        name = "broken-cleanup"

        async def run(self, ctx):
            raise RuntimeError("cleanup exploded")

    orchestrator = ScanOrchestrator(steps=[FakeStep("a", [None])], cleanup_step=BrokenCleanup())

    await orchestrator.run(ctx)

    assert db.get_scan("scan-x")["status"] == "COMPLETED"
