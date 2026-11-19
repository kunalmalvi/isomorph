# Verification status

This file states what was executed in the authoring sandbox and what was only written to specification. The authoring sandbox has Python 3.11 and pytest (phase 4 also used pip and Node, see below). It has no FastAPI, Pydantic, SQLAlchemy, Alembic, httpx, NumPy, NetworkX or PostgreSQL, and `npm install` for the old frontend is blocked. Phase 1 to 3 results below were produced without a package index.

Command run: `cd backend && python3 -m pytest tests -q -rs`

Result after phase 2: 169 passed, 2 skipped (baseline before phase 2 was 148 passed, 2 skipped). `python3 -m compileall -q backend scripts` passes.

Phase 3 FEAT-001 follow-ups (see the Phase 3 section below for final counts): 177 passed, 2 skipped. Executed (stdlib): annotation purge and orphan cleanup in `services/annotations.py`, seed links for every citation (`database/seed.py` plan and `MemorySink`), upload `interpreted` flag and `store_upload` in `core/uploads.py`, perception synonyms and plural normalisation, SSE default of 15 seconds. UNVERIFIED (no FastAPI or SQLAlchemy): the calls in `api/main.py` (startup cleanup), `api/routers/projects.py` (purge on delete), `api/routers/problems.py` (upload response), `SqlSink` savepoint conflict handling, the new models and `migrations/versions/0002_seed_constraints.py`. `npm install --package-lock-only` in `frontend/` still fails with 403, so no lock file exists (UNVERIFIED).

## Executed and passing (stdlib only)
| Area | Test files | What is covered |
|---|---|---|
| Intelligence engine, experiments, knowledge base | `tests/intelligence/*` | Schemas, perception, graph engine, fingerprints, matching, mapping, transformation, hypotheses, validation, learning, benchmarks, seeded experiments |
| Password hashing, JWT, role order | `tests/platform/test_security.py` | scrypt round trip, unique salts, policy, tampered and expired tokens, `alg: none` rejection |
| Rate limiter, upload validator, settings, error envelope, SSE | `tests/platform/test_rate_limit_uploads.py` | Sliding window, size cap, extension and signature checks, path stripping, production secret check, event ordering and timeout |
| AI provider abstraction | `tests/platform/test_ai_providers.py` | Local provider default and determinism, refusal of unsupported tasks, no silent fallback when a key is missing, OpenAI, Anthropic and Gemini request shapes against a mocked transport, retry with backoff, non-retryable errors, local rate limit, usage tracking, schema failure raises instead of fabricating |
| Orchestrator, run stores, job runner | `tests/platform/test_orchestrator.py` | All nine stages run and are inspectable, determinism, stage edit marks downstream stale, rerun downstream and rerun from, invalid edit rejected, provider failure fails the stage without output, AI output labelled `ai_hypothesis`, JSON file persistence across store instances, async job, cancellation, unexpected exception recorded, duplicate submission rejected |
| Stepwise derivation, reports, problem builder | `tests/platform/test_derivation_reports.py` | Mapping to concept to hypothesis to experiment to validation helpers, report markdown with provenance and disclaimer, partial runs report missing stages as none |
| Migration against design doc | `tests/platform/test_migration_schema.py` (4 of 5 tests) | All 35 documented tables and every documented column exist in migration 0001, foreign keys reference earlier tables, enum values, isolation columns |

## Written but NOT executed (UNVERIFIED)
These files compile (`compileall`) but have never been imported with their real dependencies.
- `backend/api/**`: FastAPI app, routers, Pydantic schemas, dependencies, SQL backed run store.
- `backend/database/**`: SQLAlchemy 2.x models and session helpers.
- `backend/migrations/**` and `backend/alembic.ini`: Alembic environment and initial migration, including the pgvector path and the JSON fallback.
- `backend/Dockerfile` and `backend/requirements.txt`: versions pinned to a compatible set, never installed, image never built.

## Frontend, Docker and deployment files (UNVERIFIED)
`npm install` returns HTTP 403 in the authoring sandbox and Docker cannot run (no conmon), so none of the following was built, linted, rendered or executed.
- `frontend/**`: Next.js 14 App Router, strict TypeScript, Tailwind, hand written shadcn style components, React Flow, Recharts, lucide-react. Eleven sections (Overview, New Discovery, My Investigations with a workspace page, Structural DNA, Discovery Universe, Transformation Studio, Hypothesis Arena, Validation Lab, Discovery Archive, Knowledge Library, Settings), a login page and a command palette.
- `frontend/tests/unit/*.test.ts` (vitest) and `frontend/e2e/*.spec.ts` (Playwright): written, never run.
- `docker-compose.yml`, `frontend/Dockerfile`, `.env.example`: never built or started.

What was actually run for the frontend:
- `python3 -m json.tool` on `package.json` and `tsconfig.json`: valid JSON.
- The globally installed TypeScript 5.9 compiler on the project without React, Next or other packages: every reported error was a consequence of the missing type packages (module not found, implicit any on event handlers, missing `children` and `key` props, `process` and `__dirname`). No error pointed at an application logic mistake, but this is a weak check and does not replace `npm run typecheck`.
- Node 22 with type stripping executed the pure modules `lib/format.ts`, `lib/arena.ts`, `lib/graph-layout.ts`, `lib/commands.ts` and `services/sse.ts` against a small assertion script (weights total, CSV escaping and formula neutralisation, comparison limit of three, layout termination on cycles, SSE buffer parsing). All assertions passed. The vitest files were not run.

Frontend behavior that is intentionally limited, and visible as such in the UI:
- Image and scanned PDF uploads are accepted and validated but not interpreted; text PDFs are read since phase 5. The New Discovery page says so.
- The Discovery Universe 3D view is a dependency free SVG projection added in phase 2 (UNVERIFIED, never rendered). The chart and table remain.
- Hypothesis Arena decisions and notes are saved through new API endpoints in phase 2 (UNVERIFIED), with `localStorage` as fallback.
- Stage progress and status badges come from the SSE endpoint (`fetch` based reader with an Authorization header). Counts on the Overview come from the `total` field of list endpoints. No metric is computed or invented in the browser.

Backend change made while writing the frontend: `backend/api/main.py` CORS `allow_methods` now includes `PUT`, which the stage edit endpoint needs from a browser on another origin.

## Skipped tests and reasons
| Test | Reason for skip | What it checks when it runs |
|---|---|---|
| `tests/platform/test_api.py` (whole module, 13 tests) | `fastapi` is not installed. The module also needs `sqlalchemy`, `pydantic` and `httpx`. | Authentication, error envelope, registration and login, project isolation between two users, viewer, editor and owner permissions, last owner protection, pagination bounds, problem child validation, upload limits (413 and 422), weights must sum to 100, provider status without secrets, knowledge endpoints, full discovery flow with stage edit and rerun, mapping to transformation to hypothesis to validation chain, report export, SSE stream, archive and restore, auth rate limit (429) |
| `tests/platform/test_migration_schema.py::test_models_match_migration_when_sqlalchemy_available` | `sqlalchemy` is not installed | ORM tables and columns equal the migration TABLES list |

In `-rs` output the skips read `could not import 'fastapi'` and `could not import 'sqlalchemy'`.

## How to verify on a real machine
1. `python -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements-dev.txt`
2. `cd backend && python -m pytest tests -q -rs` (expect zero skips).
3. With PostgreSQL 16 and pgvector: `export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/isomorph`, then `alembic upgrade head && alembic downgrade base && alembic upgrade head` from `backend/`.
4. Without pgvector: set `USE_PGVECTOR=false` before the migration and when running the API.
5. Start the API with `uvicorn api.main:create_app --factory` from `backend/` and open `/api/v1/docs`.
6. From the repository root: `docker build -f backend/Dockerfile -t isomorph-backend .`

## Known limitations
- Seed knowledge is served from `data/` JSON. A phase 2 idempotent seeding function can load it into the knowledge tables, but it is not run automatically and was never run against a database (UNVERIFIED).
- `frontend/package-lock.json` does not exist (see docs/benchmark-notes.md).
- The OpenAI, Gemini and Anthropic adapters follow the public API shapes and were tested only against a mocked transport. They have never called a real endpoint.
- The job runner is in process (thread pool). On startup runs left `queued` or `running` are marked failed with reason `interrupted by restart` (single API process assumed). There is no external queue.
- The rate limiter is in memory and per process. `X-Forwarded-For` is honored only when the peer is listed in `TRUSTED_PROXIES`.
- Only the perception stage can use a remote provider. Other stages are deterministic engine code.

## Review fixes (2026-01-01-000001-review)

| Finding | Resolution | Verified |
|---|---|---|
| Template experiments always `supported` | Template specs carry `illustrative: true`; `validate` caps them at `inconclusive` with a caveat. Rolling models are unchanged. | `tests/intelligence/test_review_fixes.py` (run) |
| Edited hypothesis keeps old experiment | `PATCH /hypotheses/{id}` clears `experiment` when statement, prediction or falsifier change, so validation returns `untested`. | Code only, API not runnable here. No executed test. |
| Lists leak deleted and archived projects | `visible_project_ids` joins `Project` and filters `deleted_at` and `archived_at`. | Test added in `test_api.py` (skipped without FastAPI) |
| Authorization after lookup | `load_problem` now runs first in `add_relationship` and `add_evidence`. | Test added in `test_api.py` (skipped without FastAPI) |
| Rolling `None` crash | `is_rolling_context` requires numeric values for all three variables, else the problem uses (capped) templates. | `test_review_fixes.py` (run) |
| SSE holds a thread per client | Not fixed. Needs a load test and an async rewrite that cannot be validated without FastAPI. Deployment docs should size the threadpool until then. | Open |
| Committed `tsbuildinfo` | Already untracked in HEAD and ignored by `frontend/.gitignore`; nothing to change. | `git ls-files` |
| Rate limiter keyed on client host | Not changed (reviewer marked possible; depends on proxy setup). | Open |

## Phase 2 additions

| Item | Executed | UNVERIFIED |
|---|---|---|
| Server side hypothesis decisions and notes (JSON file store, service layer) | Store and service tests in `tests/platform/test_phase2_platform.py` | API endpoints, API tests in `test_api.py`, frontend arena fallback, vitest for `mergeAnnotations` |
| Restart recovery of queued and running runs | Stdlib tests | SQL backed run store path in `api/db_store.py` |
| Trusted proxy rate limit client key | Stdlib tests | `api/deps.py` wiring |
| Bounded SSE polling with reconnect | Stdlib tests of the generator and framing | Router streaming, `frontend/services/sse.ts` reconnect |
| Idempotent knowledge seeding | Logic tests with a fake store | Run against SQLAlchemy and PostgreSQL |
| End to end test: run, edit hypothesis, rerun downstream, validate | Executed, stale flags and validation output asserted | Same flow through HTTP |
| 3D Discovery Universe | `frontend/lib/universe-layout.ts` executed under Node (`node frontend/tests/universe-check.mts`, passes) | `universe-3d.tsx` rendering, `frontend/tests/unit/universe.test.ts` (vitest never run) |
| Kiro specs, steering, hook schema note | Documentation only | Hook JSON schema is a guess |

## Phase 2 review follow-ups (UNVERIFIED frontend)
After two review rounds the following frontend changes were written but not run (no vitest, tsc or npm): debounced and ordered note saves in the hypotheses page, newer-edit merge in `lib/arena.ts`, unbounded SSE reconnect with a 10 consecutive failure limit in `services/sse.ts`. Backend parts (X-Forwarded-For line joining, seed source logging) are covered by stdlib tests. The annotation orphan filter in `discoveries.py` and the compose volume are UNVERIFIED. Known open: SSE holds one threadpool thread per stream (max 30 s), SQL seed sink has no unique constraints, orphan annotation files stay on disk.

## Phase 3 (FEAT-001 and FEAT-002)

Final counts: `cd backend && python3 -m pytest tests -q` gives 177 passed, 2 skipped (169 passed, 2 skipped at the start of phase 3; 8 tests added in `tests/platform/test_phase3_followups.py`). The two skips are the SQLAlchemy model comparison in `test_migration_schema.py` and the FastAPI API tests module guard in `test_api.py`.

Reruns at the end of phase 3: `python3 -m compileall -q backend scripts` passes. `python3 scripts/validate_seed_data.py` prints `seed data OK`. `python3 scripts/run_demo.py` exits 0; it rewrote `data/demo/sample_investigation.json` only in the perception limitations text (now mentions the synonym table). `python3 scripts/evaluate_benchmarks.py` exits 0 with MRR 0.9286 against a lexical baseline of 0.2566. The benchmark has n=7 and tuning overlaps evaluation, see `docs/benchmark-notes.md`. The roller demo best cross-domain score is still about 36.5/100 and was not tuned.

| Item | Executed | UNVERIFIED |
|---|---|---|
| Annotation purge and orphan cleanup | `test_purge_and_orphan_cleanup`, `test_cleanup_removes_files_and_ignores_foreign_files` | Startup call in `api/main.py`, purge on delete in `api/routers/projects.py` |
| Every citation linked for systems and mechanisms | `test_every_citation_is_linked_for_systems_and_mechanisms` (seed plan and `MemorySink`) | `SqlSink` writes, new link tables |
| Upload `interpreted` flag | `test_interpretation_flag`, `test_pdf_is_stored_and_flagged_not_interpreted` | Response wiring in `api/routers/problems.py` |
| Perception synonyms and plural normalisation | three perception tests in `test_phase3_followups.py`, benchmark MRR unchanged | None. Still keyword based. |
| Seed unique constraints, migration 0002, savepoint conflict handling | Nothing (needs SQLAlchemy and PostgreSQL) | All of it |
| SSE default 15 s | `test_default_sse_duration_is_short` and other SSE tests | Router streaming under load, sizing guidance in `docs/api-contracts.md` is untested |
| `npm install --package-lock-only` | Attempted, HTTP 403 | `frontend/package-lock.json` still absent |
| Kiro specs and steering | Documentation only. Each spec has requirements, user stories, acceptance criteria, edge cases and a test traceability table pointing to real tests. Each steering file has concrete rules taken from the code. | Test names were checked against the files in `backend/tests`; skipped API tests are marked as such in the specs |
| Frontend (all of it) | Nothing new this phase | No npm, tsc, vitest or Playwright. Docker is broken, no image was built. |

Known open after phase 3: the SSE design still holds one thread per open stream. The rate limiter is per process. The OpenAI, Gemini and Anthropic adapters have never called a real endpoint. Images and scanned PDFs are stored but not read (text PDFs are read since phase 5).

## Phase 3 review round 1

Result: `cd backend && python3 -m pytest tests -q` gives 181 passed, 2 skipped (4 new tests in `tests/platform/test_phase3_followups.py`). `run_demo.py`, `evaluate_benchmarks.py` and `validate_seed_data.py` exit 0, `compileall` passes. The API, SQL and migration changes below could not run (no FastAPI, SQLAlchemy, Alembic, PostgreSQL) and are UNVERIFIED.

| Review issue | Resolution | Executed | UNVERIFIED |
|---|---|---|---|
| 1. Startup sweep deletes on an empty or mismatched database | Fixed in part. `safe_cleanup_orphans` and `cleanup_uploads` do nothing when the live set is empty. Not fixed: a non-empty but wrong database (for example an older backup) still removes files for runs it does not know. Accepted because a grace period or quarantine adds state for a case that operators control; back up `STATE_DIR` before restoring a database. | `test_safe_cleanup_skips_empty_live_set` | Startup wiring in `api/main.py` |
| 2. Soft-deleted runs lose notes | Fixed. The sweep treats every existing session row as live, soft-deleted or not. Notes of a deleted project are purged at delete time by `delete_project`. | None (needs SQL) | Query in `api/main.py` |
| 3. Uploads never cleaned up | Fixed. `purge_uploads` runs on problem delete and project delete, and the startup sweep removes upload folders of problems whose row is gone. | `test_purge_and_cleanup_uploads` | Router wiring |
| 4. No upload quota | Fixed. At most 20 files and 50 MB per problem (`MAX_FILES_PER_SCOPE`, `MAX_BYTES_PER_SCOPE` in `core/uploads.py`), 413 when exceeded. Repeat content does not count twice. Limits are module constants, not settings. | `test_upload_quota_per_scope` | Response mapping to 413 |
| 5. Ambiguous synonyms | Fixed. Removed tap, pool, pile, lane, grid, router, gas, coal, dam, tube, fuse, resistance. Ordinary prose containing them gets no role. The unknown noun fallback may still list such a word with role None. | `test_ordinary_prose_with_ambiguous_words_makes_no_entities`, benchmark MRR unchanged | None |
| 6. Purge after commit can fail the request | Fixed. Purges are wrapped in try/except OSError with a log warning. Startup cleanup is the backstop. The global handler would otherwise map OSError to 500. | None | `api/routers/projects.py`, `problems.py` |
| 7. Migration 0002 does not backfill links | Fixed. The migration inserts a link row from each parent `source_id`. Other citations still need `python -m database.seed` after upgrade. | None | Migration up and down, backfill SQL |

## Phase 4: zero-dependency app and bundled web UI

Goal: make ISOMORPH easy to run, install and manage. `python3 ./isomorph serve` needs only Python 3.9+.

### What ran (sandbox: Python 3.11.15, Node 22.23, pip 26.2, no Docker, no browser)
| Check | Command | Result |
|---|---|---|
| Full test suite | `cd backend && python3 -m pytest tests -q -rs` | 218 passed, 2 skipped after the phase 4 review fixes (208 passed before them; 181 passed before phase 4; the skips need FastAPI and SQLAlchemy) |
| JS syntax | `node --check backend/isomorph_app/static/app.js` and `lib.js` | Pass (also run inside pytest) |
| UI helper tests | `node backend/tests/platform/ui_helpers.test.mjs` | 11 groups pass: upload checks, SSE parser with split chunks, error messages, score formatting, mapping layout, filtering, hypothesis merge, routing |
| Compile | `python3 -m compileall -q backend scripts` | Pass |
| Engine scripts | `python3 scripts/run_demo.py`, `evaluate_benchmarks.py`, `validate_seed_data.py` | Run, seed data OK |
| Real HTTP | Started `python3 ./isomorph serve --no-browser --port 8799`, requested `/`, `/app.js`, `/api/v1/health` | 200 for all, clean shutdown. `tests/platform/test_ui_bundle.py` also serves the UI from a live server thread |
| Static safety | `test_ui_bundle.py` | No external URLs or CDN, no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or `eval` in `app.js` or `lib.js`; the demo example text equals `data/demo/roller_problem.json`; every API path the UI calls exists in `server.py` |
| Packaging | `python3 -m venv --system-site-packages .scratch/venv && .scratch/venv/bin/python -m pip install --no-deps --no-build-isolation -e .`, then `isomorph version` and `isomorph doctor` from another directory; `pip wheel --no-deps --no-build-isolation .` | Editable install and wheel build succeeded, wheel contains the `static/` files, doctor passes. The wheel carries code only; the knowledge data is read from the checkout's `data/` (or `ISOMORPH_DATA_DIR`), so use an editable install from a checkout. `serve` and `doctor` now fail with a clear message when `data/` is missing |

### Phase 4 review fixes (executed in `tests/platform/test_phase4_review.py`)
| Review issue | Change | Status |
|---|---|---|
| No CSRF or DNS-rebinding defence | Without a token, `Host` must be localhost, 127.0.0.1, ::1 or the configured host (403 otherwise). A browser `Origin` must equal `Host` (403 otherwise). Request bodies need `Content-Type: application/json` (415 otherwise) | Tested over raw HTTP. Not tested with a real browser |
| Wheel lacks knowledge data | Not packaged. `serve` exits 2 and `doctor` fails with a message naming `ISOMORPH_DATA_DIR` and editable install. README notes it | Tested with a missing data directory |
| Restore or reset under a live server | `serve` writes `server.lock` (pid, host, port) in the data directory and removes it on exit. `restore` and `reset` refuse while the pid is alive unless `--force`. A second `serve` on the same directory refuses. Stale locks are ignored | Tested with in-process and real server processes. On Windows liveness uses a port probe, not tested |
| No security headers | `Content-Security-Policy`, `X-Frame-Options: DENY` and `Referrer-Policy` on every response | Tested. CSP effect on the real UI in a browser was not observed, so an inline style or script would only show up when rendering |
| Token brute force and cleartext | 10 failed bearer attempts per minute per client address, then 429. `serve` warns on a non-loopback bind about plain HTTP | Throttle tested. Warning text not tested. No TLS is provided |
| UI never rendered | Not fixed. No browser or Playwright exists in the sandbox | Still UNVERIFIED |

### UNVERIFIED
- **Rendering in a real browser.** No browser or Playwright exists in the sandbox. Layout, CSS, SVG mapping graph, keyboard behavior, focus handling, responsive breakpoints and the `fetch` based live progress stream in an actual browser were never observed. The JS was only syntax checked and its pure helpers executed under Node. Runtime errors in DOM code are possible.
- Accessibility (screen reader behavior, contrast) was not tested.
- `./install.sh` was not run end to end (it needs network access for pip's build isolation). The same install was verified with `--no-build-isolation` as above.
- Docker: `Dockerfile.simple` and `docker-compose.simple.yml` were never built or run. The older `docker-compose.yml`, `backend/Dockerfile` and `frontend/Dockerfile` remain unbuilt.
- `make` targets were not run (make availability not checked); they call the same commands as above.
- Non-loopback serving with a token over a real network, Windows, browser auto-open, and load beyond a few concurrent clients.
- The FastAPI, SQLAlchemy, PostgreSQL and Next.js stack is untouched and still UNVERIFIED. The two skipped tests are its tests.

### Honest limits of the product
- Perception is keyword and sentence-pattern based, not language understanding.
- Text PDFs are read on a best-effort basis (phase 5). Scanned or encrypted PDFs and all images are not interpreted.
- The roller demo's best match scores about 36.5 out of 100 (a weak match). Its parameters are placeholders, so validation results are capped at inconclusive. Engine scoring was not changed in this phase.
- Jobs run in an in-process thread pool. A restart fails interrupted runs; the UI offers Resume.
- Single user, local mode. Projects, members and accounts from the older API are not part of this runtime.

## Phase 5: unfamiliar vocabulary and real upload reading

Goal: reduce missed roles for unfamiliar words, and read uploaded text, CSV and text PDFs instead of only storing them.

### What ran (sandbox: Python 3.11, no browser, no network, no FastAPI or SQLAlchemy)
| Check | Command | Result |
|---|---|---|
| Full test suite | `cd backend && python3 -m pytest tests -q -rs` | 254 passed, 2 skipped (218 before phase 5; 235 after perception; the skips need FastAPI and SQLAlchemy) |
| Compile | `python3 -m compileall -q backend scripts` | Pass |
| Benchmarks | `python3 scripts/evaluate_benchmarks.py` | 7 of 7 positives beat all negatives, MRR 0.9286, hit@1 1.0, unchanged |
| Demo | `python3 scripts/run_demo.py` | Runs. Roller top score about 36.5, unchanged. Only the limitations text in `data/demo/sample_investigation.json` changed |
| Seed data | `python3 scripts/validate_seed_data.py` | seed data OK (111 systems since phase 6; citations unverified, see benchmark-notes.md) |
| Held-out perception | `python3 scripts/evaluate_perception.py` | Coverage 0.220 to 0.440, accuracy 0.115 to 0.404, precision when assigned 1.000 to 0.857, detection recall 0.788 to 0.846 |
| Upload over HTTP | `tests/platform/` tests start a live server on a free port | Upload of a stdlib-built PDF (uncompressed and Flate) returns extracted text, then a discovery starts from `upload_id`. Scanned or empty PDF, images, oversized and bad-magic files report not interpreted or are rejected |
| Fake provider | tests for `classify_unknown_roles` | Raises on provider failure and rejects roles outside the enum |

### UNVERIFIED
- **Remote AI role classification and vision.** `classify_unknown_roles` and image description were only tested with fake providers. No real OpenAI, Gemini or Anthropic endpoint was called.
- **Real-world PDFs.** The extractor was only tested on PDFs the tests build with the stdlib. PDFs from real producers (custom encodings, object streams, ToUnicode maps, columns) may fail or give scrambled text. Encrypted and scanned PDFs are reported as not interpreted.
- **UI in a browser.** The new server-file input in the bundled UI was syntax checked only. It was never rendered or clicked.
- **FastAPI upload route.** `POST /problems/{id}/uploads` in the older FastAPI stack still uses the old interpretation (PDF and images not read). It was not changed and cannot run here.
- Held-out numbers come from a set the code author wrote, so they do not estimate performance on other people's text.
- **PDF extractor limits (phase 5 review fix).** The parser scans linearly, and caps objects (5000), streams (200), inflated bytes (2 MB per stream, 4 MB total) and wall clock (4 s). Reaching any cap reports "not interpreted" instead of partial text. Extraction results are cached in memory per digest (16 entries), so repeated discoveries from one upload do not re-parse. Bounded time is asserted in `test_phase5_uploads.py` with adversarial PDFs. The 4 s budget is checked between objects and every 2048 tokens, not preemptively.

## Phase 6: KB growth, source metadata and held-out benchmark

Goal: grow the knowledge base to 111 systems with per-source confidence, and add a held-out benchmark with labels a reviewer can re-grade.

### What ran (sandbox: Python 3.11, no browser, no network, no FastAPI or SQLAlchemy)
| Check | Command | Result |
|---|---|---|
| Full test suite | `cd backend && python3 -m pytest tests -q -rs` | 276 passed, 2 skipped (the skips need FastAPI and SQLAlchemy) |
| Compile | `python3 -m compileall -q backend scripts` | Pass |
| Tuning benchmarks | `python3 scripts/evaluate_benchmarks.py` | 7 of 7 positives beat all negatives, MRR 0.9286, hit@1 1.0 |
| Held-out benchmark | `python3 scripts/evaluate_heldout.py` | 20 queries: strong hit@1 0.95, hit@3 1.0, MRR 0.975, nDCG@10 0.8324, 0 lookalikes above the best strong analog. Banner printed. See `docs/benchmark-notes.md` |
| Seed data | `python3 scripts/validate_seed_data.py` | seed data OK (111 systems) |
| Demo | `python3 scripts/run_demo.py` | Runs. Roller top match Variable air volume zone control 37.5; `run_demo.py` rewrote `docs/sample-discovery-report.md` and `data/demo/sample_investigation.json` because the top match changed (commit `a69a66f`); the regenerated files are committed |

### UNVERIFIED
- **Citations.** No citation was checked online (no network; doi.org returned 403). All are recalled from memory and carry `verification: unverified_no_network`.
- **No independent review.** All held-out labels are `author_labelled` with `independent_review: none`. The label author also wrote the matcher. `scripts/compare_reviews.py` has only run on a synthetic file.
- **No browser.** The bundled UI was not rendered in a real browser in this phase.
- The held-out set was never tuned against, but it is small (20 queries) and mostly close to structures already in the knowledge base.

## Phase 7: labelled parameters, uncertainty analysis and bite limit fix

Goal: replace the roller demo's unlabelled placeholder numbers with parameter records that state their source, range and confidence, add an uncertainty analysis, and fix a wrong bite limit.

### What ran (sandbox: Python 3.11, no browser, no network, no FastAPI or SQLAlchemy)
| Check | Command | Result |
|---|---|---|
| Full test suite | `cd backend && python3 -m pytest tests -q -rs` | 288 passed, 2 skipped (12 new tests in `tests/intelligence/test_phase7_parameters.py`; the skips need FastAPI and SQLAlchemy) |
| Tuning benchmarks | `python3 scripts/evaluate_benchmarks.py` | MRR 0.9286, unchanged |
| Held-out benchmark | `python3 scripts/evaluate_heldout.py` | MRR 0.975, unchanged |
| Demo | `python3 scripts/run_demo.py` | Roller top match arch_vav_zone_control 37.5, second Human core temperature regulation 36.5, unchanged. The script is deterministic (fixed seeds) and rewrites `docs/sample-discovery-report.md` and `data/demo/sample_investigation.json` |

### Bite limit correction
The maximum single-pass draft for a two roll mill is `2R(1 - 1/sqrt(1+mu^2))`. The earlier code used half of that value. The error was conservative (it rejected passes that can bite), and it has been fixed in `experiments/runners.py` (`max_bite_draft`). The constraint validator `_bite` keeps a commented copy of the formula (to avoid an import cycle), and a test asserts the two agree. Existing bite tests changed to a 0.8 reduction where the old limit mattered.

### Parameters
| Parameter | Kind | Basis | Status |
|---|---|---|---|
| Copper K=315 MPa, n=0.54 | handbook-level, recalled | Annealed copper, range plus or minus 15 percent by analyst judgment | Medium confidence, `unverified_no_network` |
| Silver K=320 MPa, n=0.40 | derived estimate | From recalled annealed fine silver tensile strength (about 125 to 170 MPa); K range 250 to 450 | Low confidence, `unverified_no_network`. Measured tensile data is needed |
| Friction 0.08 (range 0.03 to 0.12) | handbook-level, recalled | Lubricated cold rolling. Nominal moved from 0.12 to 0.08 | Low to medium confidence, `unverified_no_network` |
| Roll radius | assumption | Range chosen by the analyst | Not sourced |
| Mill modulus (range 100 to 500 kN/mm) | assumption | Must come from the mill's measured stretch curve | Not sourced |
| Roll force limit 90 kN | what-if rating | The user must replace it with the real machine rating | Not sourced |
| Width, thickness, reduction, tolerance | user input | Taken from the problem statement | Not checked |

### Results of the uncertainty analysis (conceptual model)
- Nominal copper, 20 percent single pass: roll force 37.9 kN.
- Monte Carlo pass fraction (force within limit and bite OK): 70 percent for one pass, 93 percent for two passes. Low friction causes the failures, because the bite condition then fails.
- Feedback beat open loop gauge control in 100 percent of 60 samples.
- These fractions depend on the assumed ranges above. They are not probabilities for a real mill.

### UNVERIFIED
- **No material value was checked against a source.** There is no network. Every K, n, friction range and citation is recalled from memory.
- **Silver is a low confidence estimate** derived from a recalled tensile strength, not a measurement.
- **Friction range** is recalled and unverified.
- **Mill modulus, roll radius and the 90 kN force limit are not sourced.** The limit is a what-if rating.
- **The model omits** roll flattening, strip tension, temperature rise, roll deflection and edge effects.
- **No comparison with measured mill data exists.** Results are conceptual, not verified, not certified engineering analysis.
- **UI not rendered in a browser.**
- **Held-out labels** are still author labelled with no independent review.
- **`python3 ./isomorph doctor`** fails under the default home here because `/root/.isomorph` is read-only (same on the base commit). It passes with `ISOMORPH_HOME` set to a writable directory.
- **`serve` health request by hand** was not run in this phase. The pytest live-server tests cover serving.

## Phase 9: self-improving loop and correlated sampling

### What ran (sandbox: Python 3.11, Node 22, no browser, no network, no FastAPI or SQLAlchemy)
- `cd backend && python3 -m pytest tests -q`: 336 passed, 2 skipped (FastAPI and SQLAlchemy missing). Before phase 9 (`baseline.json`): 288 passed, 2 skipped.
- `python3 scripts/run_demo.py`, `evaluate_benchmarks.py`, `evaluate_heldout.py`, `evaluate_perception.py`, `validate_seed_data.py` and `python3 -m compileall -q backend scripts` all ran and passed. `data/demo/sample_investigation.json` is unchanged by the demo run.
- Executed: evidence log, versioned registry with audit log, regression gate, lexicon overlay, conditional priors, the app wiring (HTTP server and CLI end to end in a temp home, including rollback), and optional correlated Monte Carlo sampling.

### Before and after (real runs, `baseline.json` against this phase, no learned data active)
| Metric | Before | After |
|---|---|---|
| Tuning set MRR (7 pairs) | 0.9286 | 0.9286 |
| Tuning set hit@1 | 1.0 | 1.0 |
| Tuning set mean margin | 13.0658 | 13.0658 |
| Held-out retrieval MRR, strong (20 queries) | 0.975 | 0.975 |
| Held-out retrieval nDCG@10 | 0.8324 | 0.8324 |
| Held-out hit@1 strong | 0.95 | 0.95 |
| Perception detection recall | 0.846 | 0.846 |
| Perception role coverage | 0.44 | 0.44 |
| Perception role accuracy | 0.404 | 0.404 |
| Perception precision when assigned | 0.857 | 0.857 |
| Roller demo best score | 37.5 | 37.5 |
| Seed systems, validation | 111, OK | 111, OK |
| Tests | 288 passed, 2 skipped | 336 passed, 2 skipped |

Every quality metric is identical. **No accuracy improvement is claimed from this phase.** With no learned data, perception role accuracy stays 0.404. The phase adds the machinery to learn from user corrections and to refuse harmful changes. Whether it improves results for a given user depends on the corrections that user supplies, and no such improvement has been measured here.

### What the gate does and does not guarantee
- The gate compares perception role accuracy, precision when assigned, detection recall, held-out MRR and nDCG, and tuning MRR for the active and candidate configs, and rejects the candidate if any drops.
- It only guards those metrics on those frozen sets. A change that harms something outside them is not detected.
- It is insensitive to words absent from the frozen sets: a lexicon term that none of those texts contain cannot change the metrics, so the gate passes it as metric-neutral.
- It is not sensitive to priors. Priors do not enter the frozen retrieval metrics, so a prior candidate is reported as "gate not sensitive to this change". The bounded size (within plus or minus 0.1) and the n >= 3 and matching-conditions rules are the only protection for priors.
- A leak guard quarantines terms that appear in the held-out files, so the gate is not trivially satisfied by learning the test vocabulary.

### Correlated sampling
`monte_carlo(..., correlations={(path_a, path_b): rho})` uses a Gaussian copula (stdlib: Cholesky, `math.erf`, closed-form inverse CDFs of the triangular and uniform marginals). It is opt in. The caller or a `ParameterRecord.correlations` field must supply rho, nothing is defaulted, and the roller demo declares none, so the demo still samples K and n independently. Tests (`tests/intelligence/test_phase9_sensitivity.py`) check that default output is unchanged, that the sample Pearson and Spearman correlation of 4000 draws is within 0.08 of rho for rho 0.8 and -0.6, that samples stay inside [low, high], that invalid rho raises, and determinism by seed. The result echoes the correlations used. Sampled correlation is close to rho, not equal to it.

### UNVERIFIED and limits
- The browser UI (Learning page, role-correction control) was never rendered. Only the JS helper tests and server-side asset serving ran.
- FastAPI and SQLAlchemy paths were not run. The learning loop is wired only into the zero-dependency server and CLI.
- The orchestrator applies only the lexicon overlay. Conditional priors are recorded and versioned but only `pipeline.investigate` applies them.
- Remote AI perception ignores the overlay and records no learned version.
- Perception labels, held-out retrieval labels and the tuning set are author written and not independently reviewed. The tuning set has n=7 and overlaps matcher development.
- No real user corrections exist in this repository, so the end to end tests use synthetic words.
- Roller material values remain recalled and unverified. No correlation between K and n has been entered for them.
