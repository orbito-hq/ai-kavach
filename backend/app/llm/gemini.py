"""Async Gemini client with multi-API-key rotation and a jittered-backoff
state machine.

Why async: a blocking retry/cooldown loop (the previous implementation)
ties up a whole thread per in-flight reasoning call, including any thread
sleeping through a cooldown. Under real load (rate limits, a slow/overloaded
"thinking" model, transient 503s — all observed against the live API) that
serializes work and can stall the pipeline for minutes. Running the call as
a coroutine means a key on cooldown just parks on `await asyncio.sleep(...)`
without blocking anything else in the process, and many findings can be in
flight/backing off independently at once.

Per-call state machine:

    ACQUIRE_KEY --(key free)--> CALL --(2xx)--> SUCCESS
         ^                       |
         |                       +--(429)--> RATE_LIMITED --+
         |                       |                          |
         |                       +--(5xx/network)-> SERVER_ERROR -+
         |                                                   |    |
         +---------------- jittered backoff, cooldown key <--+----+
         |
    (all keys cooling down)
         |
         v
    WAIT_FOR_KEY --(sleep until soonest key frees)--> ACQUIRE_KEY

Attempts exhausted with no success -> EXHAUSTED (raises the last error).

Thinking is explicitly disabled (thinkingBudget=0): this call is a bounded
classification task (pick a verdict, write 2-4 sentences), and Gemini's
"thinking" models otherwise burn many extra seconds of latency per call for
no benefit here.
"""
import asyncio
import enum
import os
import random
import time

import httpx

DEFAULT_MODEL = "gemini-flash-latest"
DEFAULT_TIMEOUT_SECONDS = 60.0
BASE_BACKOFF_SECONDS = 1.0
RATE_LIMIT_BASE_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 60.0
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(RuntimeError):
    pass


class RateLimitedError(GeminiError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ServerError(GeminiError):
    """Transient failure (5xx, timeout, connection error) — backs off and
    retries rather than giving up immediately."""


class CallState(enum.Enum):
    ACQUIRE_KEY = "ACQUIRE_KEY"
    WAIT_FOR_KEY = "WAIT_FOR_KEY"
    CALL = "CALL"
    EXHAUSTED = "EXHAUSTED"


def load_keys_from_env() -> list[str]:
    """GEMINI_API_KEYS is a comma-separated list; GEMINI_API_KEY is a single
    key. If both are set, GEMINI_API_KEYS wins."""
    multi = os.environ.get("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in multi.split(",") if k.strip()]
    if keys:
        return keys
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    return [single] if single else []


def _jittered_backoff(failure_count: int, base: float, cap: float) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**n))."""
    return random.uniform(0, min(cap, base * (2 ** failure_count)))


class GeminiKeyPool:
    def __init__(
        self,
        keys: list[str],
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not keys:
            raise ValueError("GeminiKeyPool requires at least one API key")
        self._keys = list(keys)
        self._model = model
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._next_index = 0
        self._cooldown_until = {key: 0.0 for key in self._keys}
        self._failure_counts = {key: 0 for key in self._keys}

    @property
    def key_count(self) -> int:
        return len(self._keys)

    async def _acquire_key(self) -> tuple[str | None, float]:
        """Returns (key, wait_seconds). key is None if every key is on
        cooldown, in which case wait_seconds is how long until the soonest
        one frees up."""
        now = time.monotonic()
        async with self._lock:
            n = len(self._keys)
            for offset in range(n):
                idx = (self._next_index + offset) % n
                key = self._keys[idx]
                if self._cooldown_until[key] <= now:
                    self._next_index = (idx + 1) % n
                    return key, 0.0
            soonest_wait = min(self._cooldown_until.values()) - now
            return None, max(soonest_wait, 0.1)

    async def _record_failure_and_cooldown(self, key: str, explicit_delay: float | None, base: float):
        async with self._lock:
            self._failure_counts[key] += 1
            delay = explicit_delay if explicit_delay is not None else _jittered_backoff(
                self._failure_counts[key], base, MAX_BACKOFF_SECONDS
            )
            self._cooldown_until[key] = time.monotonic() + delay

    async def _record_success(self, key: str):
        async with self._lock:
            self._failure_counts[key] = 0

    async def generate_content(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 400,
        max_attempts: int | None = None,
    ) -> str:
        attempts = max_attempts or max(len(self._keys) * 3, 3)
        last_error: Exception | None = None
        state = CallState.ACQUIRE_KEY
        key: str | None = None
        wait_seconds = 0.0

        for _ in range(attempts):
            if state is CallState.ACQUIRE_KEY:
                key, wait_seconds = await self._acquire_key()
                state = CallState.CALL if key else CallState.WAIT_FOR_KEY

            if state is CallState.WAIT_FOR_KEY:
                await asyncio.sleep(wait_seconds)
                state = CallState.ACQUIRE_KEY
                continue

            try:
                text = await self._call(key, system_prompt, user_prompt, max_output_tokens)
                await self._record_success(key)
                return text
            except RateLimitedError as e:
                last_error = e
                await self._record_failure_and_cooldown(key, e.retry_after, RATE_LIMIT_BASE_BACKOFF_SECONDS)
            except GeminiError as e:
                last_error = e
                await self._record_failure_and_cooldown(key, None, BASE_BACKOFF_SECONDS)
            state = CallState.ACQUIRE_KEY

        raise last_error or GeminiError("All Gemini API keys exhausted")

    async def _call(self, key: str, system_prompt: str, user_prompt: str, max_output_tokens: int) -> str:
        url = API_URL_TEMPLATE.format(model=self._model)
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json", "X-goog-api-key": key},
                    json=payload,
                )
        except httpx.HTTPError as e:
            raise ServerError(f"Gemini request failed: {e}") from e

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitedError(
                "Gemini rate limit hit",
                retry_after=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 500:
            raise ServerError(f"Gemini API error {response.status_code}: {response.text[:500]}")
        if response.status_code >= 400:
            raise GeminiError(f"Gemini API error {response.status_code}: {response.text[:500]}")

        data = response.json()
        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError) as e:
            finish_reason = data.get("candidates", [{}])[0].get("finishReason")
            raise GeminiError(
                f"Unexpected Gemini response shape (finishReason={finish_reason}): {data}"
            ) from e
