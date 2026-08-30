import httpx
import pytest

from app.llm import gemini


def make_response(status_code, json_body=None, headers=None):
    request = httpx.Request("POST", "https://example.com")
    return httpx.Response(
        status_code=status_code,
        json=json_body or {},
        headers=headers or {},
        request=request,
    )


def success_body(text="VERDICT: CONFIRMED\nEXPLANATION: yes"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def patch_async_post(monkeypatch, handler):
    """handler(self, url, headers=None, json=None) -> httpx.Response, sync or async."""

    async def fake_post(self, url, headers=None, json=None):
        result = handler(self, url, headers=headers, json=json)
        return result

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def test_load_keys_from_env_prefers_multi(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "a, b ,, c")
    monkeypatch.setenv("GEMINI_API_KEY", "single")

    assert gemini.load_keys_from_env() == ["a", "b", "c"]


def test_load_keys_from_env_falls_back_to_single(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "single-key")

    assert gemini.load_keys_from_env() == ["single-key"]


def test_load_keys_from_env_empty_when_unset(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert gemini.load_keys_from_env() == []


async def test_generate_content_success_with_single_key(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1"])
    patch_async_post(monkeypatch, lambda self, url, headers, json: make_response(200, success_body()))

    text = await pool.generate_content("system", "user")

    assert "CONFIRMED" in text


async def test_generate_content_rotates_past_rate_limited_key(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1", "key-2"])
    calls = []

    def handler(self, url, headers, json):
        key = headers["X-goog-api-key"]
        calls.append(key)
        if key == "key-1":
            return make_response(429, {}, headers={"Retry-After": "100"})
        return make_response(200, success_body())

    patch_async_post(monkeypatch, handler)

    text = await pool.generate_content("system", "user")

    assert "CONFIRMED" in text
    assert calls[0] == "key-1"
    assert "key-2" in calls


async def test_generate_content_retries_single_key_after_failure(monkeypatch):
    pool = gemini.GeminiKeyPool(["only-key"])
    attempts = {"n": 0}

    def handler(self, url, headers, json):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return make_response(429, {}, headers={"Retry-After": "0.05"})
        return make_response(200, success_body())

    patch_async_post(monkeypatch, handler)

    text = await pool.generate_content("system", "user", max_attempts=4)

    assert "CONFIRMED" in text
    assert attempts["n"] == 2


async def test_generate_content_raises_after_exhausting_attempts(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1"])
    patch_async_post(monkeypatch, lambda self, url, headers, json: make_response(500, {}))

    with pytest.raises(gemini.ServerError):
        await pool.generate_content("system", "user", max_attempts=2)


async def test_generate_content_wraps_network_error_as_server_error(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1"])

    async def raise_timeout(self, url, headers=None, json=None):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", raise_timeout)

    with pytest.raises(gemini.ServerError):
        await pool.generate_content("system", "user", max_attempts=1)


async def test_call_disables_thinking_by_default(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1"])
    captured = {}

    def handler(self, url, headers, json):
        captured["payload"] = json
        return make_response(200, success_body())

    patch_async_post(monkeypatch, handler)
    await pool.generate_content("system", "user")

    assert captured["payload"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


async def test_generate_content_raises_on_unexpected_response_shape(monkeypatch):
    pool = gemini.GeminiKeyPool(["key-1"])
    patch_async_post(
        monkeypatch,
        lambda self, url, headers, json: make_response(200, {"candidates": [{"finishReason": "SAFETY"}]}),
    )

    with pytest.raises(gemini.GeminiError):
        await pool.generate_content("system", "user", max_attempts=1)


async def test_generate_content_does_not_block_other_coroutines(monkeypatch):
    """A key stuck cooling down should park on asyncio.sleep, not a thread
    -blocking sleep — so unrelated work scheduled on the same loop still runs
    while it waits."""
    import asyncio

    pool = gemini.GeminiKeyPool(["key-1"])

    async def slow_fail_then_succeed(self, url, headers=None, json=None):
        if slow_fail_then_succeed.calls == 0:
            slow_fail_then_succeed.calls += 1
            return make_response(429, {}, headers={"Retry-After": "0.2"})
        return make_response(200, success_body())

    slow_fail_then_succeed.calls = 0
    monkeypatch.setattr(httpx.AsyncClient, "post", slow_fail_then_succeed)

    ticks = []

    async def ticker():
        for _ in range(5):
            ticks.append(1)
            await asyncio.sleep(0.02)

    results = await asyncio.gather(pool.generate_content("system", "user"), ticker())

    assert "CONFIRMED" in results[0]
    assert len(ticks) == 5  # the ticker made real progress while the pool waited
