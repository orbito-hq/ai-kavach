"""Pipeline steps.

Single Responsibility: each step does exactly one thing. Open/Closed: a new
step is a new class — the orchestrator never needs to change to support it.
Every step is a thin async wrapper; genuinely blocking work (subprocess
calls, file I/O, sqlite) is pushed onto a worker thread via
asyncio.to_thread so it never stalls the event loop or other scans/findings
in flight.
"""
import asyncio
from abc import ABC, abstractmethod

from app import db, intake, reasoner
from app.pipeline.context import ScanContext
from app.scanner import run_semgrep


class PipelineStep(ABC):
    name: str

    @abstractmethod
    async def run(self, ctx: ScanContext) -> None: ...


class IntakeStep(PipelineStep):
    name = "intake"

    async def run(self, ctx: ScanContext) -> None:
        if ctx.zip_bytes is not None:
            ctx.target_dir = await asyncio.to_thread(intake.prepare_from_zip, ctx.scan_id, ctx.zip_bytes)
        else:
            ctx.target_dir = await asyncio.to_thread(intake.prepare_from_git, ctx.scan_id, ctx.repo_url)
        ctx.logger.info("intake complete: target_dir=%s", ctx.target_dir)


class LanguageDetectionStep(PipelineStep):
    name = "detect_languages"

    async def run(self, ctx: ScanContext) -> None:
        ctx.languages = await asyncio.to_thread(intake.detect_languages, ctx.target_dir)
        await asyncio.to_thread(db.update_scan, ctx.scan_id, languages=ctx.languages)
        ctx.logger.info("languages detected: %s", ctx.languages)


class StaticAnalysisStep(PipelineStep):
    name = "static_analysis"

    async def run(self, ctx: ScanContext) -> None:
        ctx.findings = await asyncio.to_thread(run_semgrep, ctx.target_dir)
        for finding in ctx.findings:
            finding["scan_id"] = ctx.scan_id
        ctx.logger.info("static analysis found %d finding(s)", len(ctx.findings))


class ReasoningStep(PipelineStep):
    """Independent per finding, so calls run concurrently — bounded by
    reasoner.max_concurrency(), which scales with the number of configured
    Gemini keys (one in-flight call per key) rather than hammering one."""

    name = "ai_reasoning"

    async def run(self, ctx: ScanContext) -> None:
        semaphore = asyncio.Semaphore(reasoner.max_concurrency())

        async def reason_one(finding: dict) -> dict:
            async with semaphore:
                result = await reasoner.analyze_finding(finding, ctx.target_dir)
                ctx.logger.info(
                    "reasoned about %s:%s -> %s",
                    finding["file"], finding["line"], result["ai_verdict"],
                )
                return result

        ai_results = await asyncio.gather(*(reason_one(f) for f in ctx.findings))
        for finding, ai_result in zip(ctx.findings, ai_results):
            finding.update(ai_result)


class PersistFindingsStep(PipelineStep):
    name = "persist_findings"

    async def run(self, ctx: ScanContext) -> None:
        for finding in ctx.findings:
            await asyncio.to_thread(db.add_finding, finding)
        ctx.logger.info("persisted %d finding(s)", len(ctx.findings))


class CleanupStep(PipelineStep):
    name = "cleanup"

    async def run(self, ctx: ScanContext) -> None:
        await asyncio.to_thread(intake.cleanup, ctx.scan_id)
        ctx.logger.info("workspace cleaned up")
