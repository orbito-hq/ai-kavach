import fakeredis
import pytest
from rq import Queue

from app import queue as queue_module


def test_is_enabled_reflects_redis_url_env(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert queue_module.is_enabled() is False

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert queue_module.is_enabled() is True


def test_enqueue_scan_pushes_a_job_onto_the_queue(monkeypatch):
    fake_conn = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(queue_module, "get_queue", lambda: Queue(queue_module.QUEUE_NAME, connection=fake_conn))

    queue_module.enqueue_scan("scan-123", "repo.zip", b"zipbytes", None)

    q = Queue(queue_module.QUEUE_NAME, connection=fake_conn)
    assert q.count == 1
    job = q.jobs[0]
    assert job.args == ("scan-123", "repo.zip", b"zipbytes", None)
    assert job.retries_left == len(queue_module.RETRY_INTERVALS)
