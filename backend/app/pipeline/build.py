"""Composition root: wires concrete steps into a ScanOrchestrator.

Kept in one place so both consumers of the pipeline — the inline
(BackgroundTasks) path in main.py and the Redis/RQ consumer in worker.py —
run the exact same steps in the exact same order. Neither has to know how
the other invokes it (Dependency Inversion at the module level).
"""
from app.pipeline.orchestrator import ScanOrchestrator
from app.pipeline.steps import (
    CleanupStep,
    IntakeStep,
    LanguageDetectionStep,
    PersistFindingsStep,
    ReasoningStep,
    StaticAnalysisStep,
)


def build_orchestrator() -> ScanOrchestrator:
    return ScanOrchestrator(
        steps=[
            IntakeStep(),
            LanguageDetectionStep(),
            StaticAnalysisStep(),
            ReasoningStep(),
            PersistFindingsStep(),
        ],
        cleanup_step=CleanupStep(),
    )
