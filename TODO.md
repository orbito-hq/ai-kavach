# AI Kavach — Build TODO

Source: `docs/scope_of_work.md`. Full scope is 18 levels; per the doc's own
recommendation we are NOT building all of them up front. We follow the
"Recommended MVP Roadmap" and build incrementally.

## MVP 1 — Working vulnerability discovery (BUILDING NOW)

Pipeline: `Repository -> Semgrep -> LLM -> Vulnerability Report`

- [x] Project skeleton: `backend/` (FastAPI) + `frontend/` (Vite + React)
- [x] `shell.nix` providing python3, nodejs, semgrep for local dev/testing
- [x] Target intake: accept a Git URL or a ZIP upload, extract to a scan workspace
- [x] Basic language/file detection (extension histogram)
- [x] Static analysis: run Semgrep (`--config=auto` fallback to bundled default
      rules if offline) and parse results into the normalized Finding schema
      (id, type, severity, file, line, evidence, rule, confidence)
- [x] SQLite persistence for scans + findings (job metadata, per Level 0.2)
- [x] Background job execution with status polling (PENDING/RUNNING/DONE/FAILED)
- [x] AI reasoning step (Level 3): send each finding + surrounding code to an
      LLM (Anthropic API) to get root cause, exploitability, and a
      Confirmed/Rejected/Needs-Testing verdict. Runs only if `ANTHROPIC_API_KEY`
      is set; otherwise findings are marked `NEEDS_TESTING` with a note that
      LLM reasoning was skipped, so the pipeline still works without a key.
- [x] REST API: create scan, get scan status, list findings, get one finding
- [x] React dashboard: upload target, watch scan progress, browse findings,
      view AI analysis + evidence per finding
- [x] Backend tests runnable via `nix-shell` (pytest)

## Not built yet (future levels, in priority order per the doc)

- [ ] Level 4 — Dynamic analysis sandbox (Docker exec, ASAN/UBSAN/GDB, crash capture)
- [ ] Level 6 — Proof of Vulnerability generation/execution/evidence store
- [ ] Level 7/8 — AI patch generation + isolated patch application (baseline vs patched trees)
- [ ] Level 9 — Patch verification pipeline (build, tests, PoV re-run, static re-scan)
- [ ] Level 10 — Regression test harness retained across patches
- [ ] Level 5 — Automated fuzzing (AFL++/libFuzzer) integration
- [ ] Level 11 — Full autonomous orchestrator state machine (DISCOVERING..COMPLETED)
- [ ] Level 12 — Retry/self-correction loop with MAX_PATCH_ATTEMPTS etc.
- [ ] Level 13 — Hardened security sandbox (resource/network limits per container type)
- [ ] Level 14 — Full evidence & report export (PDF/HTML executive report)
- [ ] Level 15 — Polished "Command Center" UI (progress bars, live operation feed)
- [ ] Level 16 — Evaluation harness + benchmark suite of vulnerable apps
- [ ] Level 17 — One-button autonomous end-to-end mode
- [ ] Level 18 — Competition hardening (crash recovery, job queue, observability)

## How to run / test (nix-shell)

```bash
nix-shell                      # drops into shell with python3, semgrep, nodejs
cd backend && pip install -r requirements.txt -q
pytest                         # run backend tests
uvicorn app.main:app --reload  # run API on :8000

cd ../frontend && npm install
npm run dev                    # run React dashboard on :5173
```
