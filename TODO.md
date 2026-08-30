# AI Kavach — Build TODO

Source: `docs/scope_of_work.md`. Full scope is 18 levels; per the doc's own
recommendation we are NOT building all of them up front. We follow the
"Recommended MVP Roadmap" and build incrementally.

## MVP 1 — Working vulnerability discovery (BUILDING NOW)

Pipeline: `Repository -> Semgrep -> LLM -> Vulnerability Report`

- [x] Project skeleton: `backend/` (FastAPI) + `frontend/` (Vite + React)
- [x] `shell.nix` providing python3, nodejs for local dev/testing (app runs
      here); `docker-compose.yml` providing Redis as an optional dev
      dependency (see below) — Docker is used only for that, not for
      running the app itself
- [x] Target intake: accept a Git URL or a ZIP upload, extract to a scan workspace
- [x] Basic language/file detection (extension histogram)
- [x] Static analysis: Semgrep against a bundled offline ruleset
      (`app/rules/security.yaml` — not `--config=auto`, so scans don't
      depend on the Semgrep registry and are reproducible per Level 18) with
      `--no-git-ignore` (this project's own `.gitignore` would otherwise
      cause semgrep to silently skip everything under `backend/workspaces/`)
- [x] SQLite persistence for scans + findings (job metadata, per Level 0.2)
- [x] AI reasoning step (Level 3): send each finding + surrounding code to an
      LLM to get root cause, exploitability, and a Confirmed/Rejected/Needs-
      Testing verdict. Provider is picked automatically: Gemini if
      `GEMINI_API_KEY`/`GEMINI_API_KEYS` is set, else Anthropic if
      `ANTHROPIC_API_KEY` is set, else reasoning is skipped and findings are
      marked `NEEDS_TESTING` — the pipeline always works without a key.
- [x] Gemini async client (`app/llm/gemini.py`): multi-key round-robin pool
      with a per-call jittered-backoff state machine
      (ACQUIRE_KEY → CALL → SUCCESS, or → RATE_LIMITED/SERVER_ERROR → backoff
      → ACQUIRE_KEY, until attempts are EXHAUSTED). Works identically with
      exactly one key (retries that key after its own cooldown). Thinking
      is disabled (`thinkingBudget: 0`) — this is a bounded classification
      call, and Gemini's thinking mode otherwise adds 10-90s+ of latency per
      call for no benefit here (observed against the live API, including a
      transient 503 under load).
- [x] Pipeline rebuilt as SOLID step objects behind an orchestrator
      (`app/pipeline/`): `PipelineStep` steps (Intake, LanguageDetection,
      StaticAnalysis, Reasoning, PersistFindings, Cleanup) each do one job
      (Single Responsibility); `ScanOrchestrator` depends only on the step
      abstraction (Dependency Inversion) and can run any list of them; a new
      step is a new class, not an orchestrator change (Open/Closed). Fully
      async end to end — every blocking call (subprocess, sqlite, file I/O)
      runs via `asyncio.to_thread`, and independent findings' reasoning
      calls run concurrently via `asyncio.gather`, bounded by
      `reasoner.max_concurrency()` — nothing blocks the whole process while
      waiting on the network or a cooldown.
- [x] Per-step retry with jittered exponential backoff for transient
      failures (`ScanError`, e.g. a semgrep timeout); a fatal error
      (`IntakeError` — bad upload/URL) fails the scan immediately with no
      retry. Cleanup always runs, success or failure, and never overrides
      the scan's final status. `GET /api/scans/{id}/logs` exposes the
      full per-step, per-retry log for a scan (Level 14/18).
- [x] Optional Redis/RQ consumer queue (`app/queue.py`, `app/worker.py`):
      with `REDIS_URL` unset, scans run inline via FastAPI BackgroundTasks
      in-process — zero extra infra, same pattern as 1-vs-many Gemini keys.
      Setting `REDIS_URL` switches to a durable queue consumed by
      `rq worker kavach-scans`: jobs survive an API-process restart, and RQ
      retries the whole job automatically (with backoff) if a worker
      crashes mid-scan — failover above the in-process per-step retries.
      `docker-compose.yml` runs Redis for local dev (`docker compose up -d
      redis`) on its own bridge network; the app itself is not
      dockerized, it still runs via nix-shell.
- [x] REST API: create scan, get scan status, list findings, get one
      finding, get a scan's log
- [x] React dashboard: upload target, watch scan progress, browse findings,
      view AI analysis + evidence per finding, view the raw scan log
- [x] Backend tests runnable via `nix-shell` (pytest, pytest-asyncio,
      fakeredis for hermetic queue tests)

## Not built yet (future levels, in priority order per the doc)

- [ ] Level 4 — Dynamic analysis sandbox (Docker exec, ASAN/UBSAN/GDB, crash capture)
- [ ] Level 6 — Proof of Vulnerability generation/execution/evidence store
- [ ] Level 7/8 — AI patch generation + isolated patch application (baseline vs patched trees)
- [ ] Level 9 — Patch verification pipeline (build, tests, PoV re-run, static re-scan)
- [ ] Level 10 — Regression test harness retained across patches
- [ ] Level 5 — Automated fuzzing (AFL++/libFuzzer) integration
- [ ] Level 11 — Full autonomous agent state machine (DISCOVERING..COMPLETED)
      across the whole scan-to-report flow, not just within reasoning/queue
- [ ] Level 12 — Cross-stage self-correction loop (patch fails -> re-analyze
      -> new patch), with MAX_PATCH_ATTEMPTS — the per-step retry we have
      today only covers transient infra failures, not "the LLM's answer was
      wrong, try again with different context"
- [ ] Level 13 — Hardened security sandbox (resource/network limits per container type)
- [ ] Level 14 — Full evidence & report export (PDF/HTML executive report) —
      the per-scan log is a start, not the full report
- [ ] Level 15 — Polished "Command Center" UI (progress bars, live operation feed)
- [ ] Level 16 — Evaluation harness + benchmark suite of vulnerable apps
- [ ] Level 17 — One-button autonomous end-to-end mode
- [ ] Level 18 — Remaining competition hardening (crash recovery is partly
      covered by the Redis/RQ path; still missing: versioned prompts/tools,
      reproducible Docker images for the app itself, resource quotas)

## How to run / test

```bash
nix-shell                      # drops into shell with python3, nodejs
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -q
pytest                         # run backend tests (Redis tests use fakeredis, no real server needed)

# Optional — enable AI reasoning (Level 3). Without either of these,
# findings are still detected, just marked NEEDS_TESTING.
export GEMINI_API_KEYS="key1,key2,key3"   # comma-separated, rotates on rate limit
# or: export GEMINI_API_KEY="key1"        # single key also works
# or: export ANTHROPIC_API_KEY="..."      # used only if no Gemini key is set

uvicorn app.main:app --reload  # run API on :8000

cd ../frontend && npm install
npm run dev                    # run React dashboard on :5173
```

### Optional: Redis-backed consumer queue instead of inline execution

```bash
docker compose up -d redis                 # from repo root — dev-only dependency
export REDIS_URL=redis://localhost:6380/0  # in the shell running uvicorn AND in a second shell
cd backend && source .venv/bin/activate
rq worker kavach-scans --worker-class rq.worker.SimpleWorker   # the consumer
```
With `REDIS_URL` set, `POST /api/scans` enqueues a job instead of running inline; the
`rq worker` process(es) consume the queue, retrying a whole job automatically (with
backoff) if a worker crashes mid-scan. Unset `REDIS_URL` (or don't run `docker compose`)
to go back to inline execution — no code changes needed either way.

`--worker-class rq.worker.SimpleWorker` is required on macOS: RQ's default worker forks
a subprocess per job, and Python's `fork()` after the Objective-C runtime has
initialized (triggered by something in the httpx/certifi/anthropic stack) crashes hard
on macOS — a known platform issue, not specific to this project. `SimpleWorker` runs
jobs in the worker's own process instead of forking, which sidesteps it. On Linux this
isn't needed, but it's harmless there too.
