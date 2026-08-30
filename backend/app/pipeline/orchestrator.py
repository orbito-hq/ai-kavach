"""Runs an ordered list of PipelineStep objects against a ScanContext.

- Dependency Inversion: the orchestrator only knows about the PipelineStep
  abstraction, not any concrete step — callers (build.py) assemble whichever
  steps/order they need.
- Retries a step that raises a transient error (ScanError — e.g. a semgrep
  timeout) with jittered exponential backoff, up to MAX_STEP_RETRIES times.
  A fatal error (IntakeError — bad input) fails the scan immediately with
  no retry, since retrying won't fix a malformed upload or bad repo URL.
- The cleanup step always runs, success or failure, and never itself fails
  the scan (its own errors are logged, not raised) — this is the local,
  in-process half of "failover"; the other half (surviving a whole worker
  process crash) is handled by the Redis/RQ consumer queue in app/queue.py
  retrying the entire job.
"""
import asyncio
import random

from app import db
from app.intake import IntakeError
from app.pipeline.context import ScanContext
from app.pipeline.steps import PipelineStep
from app.scanner import ScanError

RETRYABLE_EXCEPTIONS = (ScanError,)
FATAL_EXCEPTIONS = (IntakeError,)

MAX_STEP_RETRIES = 2
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 15.0


def _jittered_backoff(attempt: int) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**n))."""
    return random.uniform(0, min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2 ** attempt)))


class ScanOrchestrator:
    def __init__(self, steps: list[PipelineStep], cleanup_step: PipelineStep | None = None):
        self._steps = steps
        self._cleanup_step = cleanup_step

    async def run(self, ctx: ScanContext) -> None:
        await asyncio.to_thread(db.update_scan, ctx.scan_id, status="RUNNING")
        try:
            for step in self._steps:
                await self._run_step_with_retries(step, ctx)
            await asyncio.to_thread(db.update_scan, ctx.scan_id, status="COMPLETED")
            ctx.logger.info("scan completed successfully")
        except FATAL_EXCEPTIONS as e:
            ctx.logger.error("scan failed (fatal): %s", e)
            await asyncio.to_thread(db.update_scan, ctx.scan_id, status="FAILED", error=str(e))
        except Exception as e:  # pragma: no cover - safety net for unexpected errors
            ctx.logger.exception("scan failed (unexpected)")
            await asyncio.to_thread(db.update_scan, ctx.scan_id, status="FAILED", error=f"Unexpected error: {e}")
        finally:
            if self._cleanup_step is not None:
                try:
                    await self._cleanup_step.run(ctx)
                except Exception:
                    ctx.logger.exception("cleanup step '%s' failed", self._cleanup_step.name)

    async def _run_step_with_retries(self, step: PipelineStep, ctx: ScanContext) -> None:
        attempt = 0
        while True:
            try:
                ctx.logger.info("step '%s' starting (attempt %d)", step.name, attempt + 1)
                await step.run(ctx)
                ctx.logger.info("step '%s' succeeded", step.name)
                return
            except FATAL_EXCEPTIONS:
                raise
            except RETRYABLE_EXCEPTIONS as e:
                attempt += 1
                if attempt > MAX_STEP_RETRIES:
                    ctx.logger.error("step '%s' failed after %d attempts: %s", step.name, attempt, e)
                    raise
                delay = _jittered_backoff(attempt)
                ctx.logger.warning(
                    "step '%s' failed (attempt %d/%d): %s — retrying in %.1fs",
                    step.name, attempt, MAX_STEP_RETRIES, e, delay,
                )
                await asyncio.sleep(delay)
