"""Redis-backed consumer/worker queue for scan jobs (optional).

By default (REDIS_URL unset) scans run inline via FastAPI's BackgroundTasks
in the same process — zero extra infrastructure needed, the same "works
with nothing configured, scales up cleanly" pattern as the Gemini key pool
(app/llm/gemini.py: 1 key or many, same code path).

Setting REDIS_URL switches to a durable Redis queue consumed by a separate
`rq worker kavach-scans` process (or several — that's the "consumer-based
pipeline" and real cross-process parallelism):
  - jobs survive an API-process restart instead of being lost mid-scan
  - RQ retries the whole job automatically on an unhandled worker crash,
    with backoff intervals — failover above and beyond the in-process
    per-step retries the orchestrator already does
  - multiple worker processes/machines can drain the same queue

Run Redis for local dev with `docker compose up -d redis` (see
docker-compose.yml at the repo root), then:
    export REDIS_URL=redis://localhost:6380/0
    rq worker kavach-scans   # in a second terminal, from backend/
"""
import os

from redis import Redis
from rq import Queue, Retry

QUEUE_NAME = "kavach-scans"
RETRY_INTERVALS = [10, 30, 90]  # seconds between RQ's whole-job retries
JOB_TIMEOUT_SECONDS = 600


def redis_url() -> str | None:
    return os.environ.get("REDIS_URL")


def is_enabled() -> bool:
    return bool(redis_url())


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=Redis.from_url(redis_url()))


def enqueue_scan(scan_id: str, source: str, zip_bytes: bytes | None, repo_url: str | None):
    from app.worker import process_scan_job  # local import: avoid requiring rq/redis when unused

    queue = get_queue()
    queue.enqueue(
        process_scan_job,
        scan_id, source, zip_bytes, repo_url,
        retry=Retry(max=len(RETRY_INTERVALS), interval=RETRY_INTERVALS),
        job_timeout=JOB_TIMEOUT_SECONDS,
    )
