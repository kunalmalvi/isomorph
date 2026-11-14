# Verification status

This file states what was executed in the authoring sandbox and what was only written to specification. The sandbox has Python 3.11 and pytest. It has no FastAPI, Pydantic, SQLAlchemy, Alembic, httpx, NumPy, NetworkX or PostgreSQL, and no package index access.

Command run: `cd backend && python3 -m pytest tests -q -rs`

Result when this was written: 138 passed, 2 skipped. `python3 -m compileall -q backend scripts` passes.

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
- Seed knowledge (domains, systems, mechanisms) is served from `data/` JSON. The `domains`, `domain_systems`, `mechanisms` and `sources` tables exist and are migrated, but no seeding script populates them yet.
- The OpenAI, Gemini and Anthropic adapters follow the public API shapes and were tested only against a mocked transport. They have never called a real endpoint.
- The job runner is in process (thread pool). Runs in a process that dies stay `queued` or `running`. There is no restart recovery and no external queue.
- The rate limiter is in memory and per process.
- Only the perception stage can use a remote provider. Other stages are deterministic engine code.
