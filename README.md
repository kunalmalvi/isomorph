# ISOMORPH

ISOMORPH is a cross-domain structural reasoning platform. You describe a problem in plain language. The platform extracts its structure (components, relations, feedback, constraints), searches a curated knowledge base for systems in other domains with a similar structure, maps mechanisms across, derives candidate transformations and writes testable hypotheses. Hypotheses can be checked with seeded simulations.

Everything it produces is a hypothesis from structural analogy. Nothing is proven, and simulation outcomes are not real world evidence. Every claim carries a provenance label: `source`, `computation`, `user` or `ai_hypothesis`.

Default mode is deterministic and offline. No API key and no network are needed. Remote AI providers are optional and only used for the perception stage.

> **Read the status section first.** The intelligence engine and its tests run and pass. The API, database layer, migrations, frontend and Docker setup were written to specification in a sandbox that could not install their dependencies, so they have never run. See [What is complete, incomplete and unverified](#status).

## Repository layout
| Path | Contents |
|---|---|
| `backend/intelligence`, `backend/experiments`, `backend/knowledge_base` | Pure standard library engine, seeded experiments, knowledge loader |
| `backend/api`, `backend/services`, `backend/database`, `backend/migrations` | FastAPI app, orchestrator and job runner, SQLAlchemy models, Alembic |
| `backend/ai_providers` | Local deterministic provider plus OpenAI, Gemini and Anthropic adapters |
| `frontend/` | Next.js App Router, TypeScript strict, Tailwind |
| `data/` | Seed domains, systems, mechanisms, benchmark problems, demo input and output |
| `docs/` | Architecture, API contracts, schemas, database design, deployment, demo script, verification status |
| `.kiro/` | Specs, steering and hooks used to build the project |

## Quick start: engine only (works with plain Python 3.11+)
```bash
python3 scripts/validate_seed_data.py
python3 scripts/run_demo.py          # the flagship roller scenario, end to end, prints results
cd backend && python3 -m pytest tests -q -rs
```

## Run the full stack with Docker
```bash
cp .env.example .env                 # set POSTGRES_PASSWORD and ISOMORPH_SECRET_KEY
docker compose up --build
```
Open http://localhost:3000, register an account, and start with New Discovery. API docs are at http://localhost:8000/api/v1/docs. The backend container runs `alembic upgrade head` before starting. `NEXT_PUBLIC_API_URL` is baked into the frontend image at build time and must be reachable from your browser.

## Run without Docker
Backend (Python 3.12 recommended, PostgreSQL 16 with pgvector recommended):
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://isomorph:change-me@localhost:5432/isomorph
export ISOMORPH_DATA_DIR=$PWD/data
cd backend
alembic upgrade head                 # set USE_PGVECTOR=false if the extension is not installed
uvicorn api.main:create_app --factory --reload
```
Frontend (Node 20 or newer):
```bash
cd frontend
npm ci            # or npm install if no lock file exists yet
npm run dev       # http://localhost:3000, expects the API at http://localhost:8000/api/v1
```
Set `NEXT_PUBLIC_API_URL` to point the frontend at a different API. Set `CORS_ORIGINS` on the backend to the frontend origin.

## AI provider configuration
Set these on the backend (see `.env.example`).
| Variable | Meaning |
|---|---|
| `AI_PROVIDER` | `local` (default), `openai`, `gemini` or `anthropic` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | Key for the chosen provider. Keys are read from the environment only and never returned by the API |

Behavior to know about:
- Only the perception stage (turning text into a structural draft) can use a remote provider. All other stages are deterministic engine code.
- Output from a remote provider is labelled `ai_hypothesis` and is validated against a schema. Invalid output fails the stage. It is never replaced with invented data.
- Selecting a remote provider without a key fails the run with a visible error. There is no silent fallback to local.
- The adapters follow the public API shapes and were tested only against a mocked transport. They have never called a real endpoint.
- Settings shows which providers are configured (never the key values).

## Tests
| Suite | Command | Status |
|---|---|---|
| Backend engine and platform helpers | `cd backend && python3 -m pytest tests -q -rs` | Run and passing in the sandbox |
| Backend API with FastAPI | same command, after installing `requirements-dev.txt` | Skipped in the sandbox, never run |
| Frontend unit (vitest) | `cd frontend && npm test` | Written, never run |
| Frontend type check and lint | `npm run typecheck`, `npm run lint` | Never run |
| End to end (Playwright) | start the stack, then `cd frontend && npx playwright install chromium && npm run test:e2e` | Written, never run |

E2E specs register a fresh user per test, so they can run against an empty database. Override `E2E_BASE_URL` if the frontend is not on port 3000.

## Flagship demo
The demo scenario reduces copper or silver strip thickness with rolls. Walkthrough: [docs/demo-script.md](docs/demo-script.md). Sample report: [docs/sample-discovery-report.md](docs/sample-discovery-report.md). The demo material model is a clearly labelled demo only scenario with assumed placeholder parameters.

## Deploy
See [docs/deployment.md](docs/deployment.md) for configuration, security notes and a pre-flight checklist.

<a id="status"></a>
## What is complete, incomplete and unverified
**Complete and tested (stdlib, runs in the sandbox)**
- Structural engine: schemas, perception heuristics, graph engine, fingerprints, multi-stage matching with configurable weights, mapping, transformation with hard constraint checks, hypotheses, seeded validation, learning memory, benchmarks.
- Seed knowledge with sources and a validator script.
- Security helpers, rate limiter, upload validator, AI provider abstraction (mocked transport), nine stage orchestrator with edit and rerun, job runner, report builder.
- Migration versus design document check (all documented tables and columns).

**Written to specification, never executed (UNVERIFIED)**
- `backend/api`, `backend/database`, `backend/migrations`: need FastAPI, SQLAlchemy and PostgreSQL to run. The 13 API tests exist and are skipped here.
- Frontend: all 11 sections, command palette, API client, SSE client, vitest and Playwright specs. `npm install` was blocked, so nothing was built, type checked against real React and Next types, linted or rendered. A partial TypeScript pass without the React and Next type packages showed only errors caused by those missing packages. Phase 2 backend result: 167 passed, 2 skipped. Pure logic modules (universe layout, formatting, CSV, SSE parsing, graph layout, comparison limit) were executed under Node and behaved as expected.
- `docker-compose.yml`, `frontend/Dockerfile`, `backend/Dockerfile`: never built.

**Known gaps (by design in this version)**
- PDF and image uploads are validated but not interpreted (no OCR or vision dependency). The UI says so.
- The 3D Discovery Universe view is a dependency free SVG projection and is UNVERIFIED (never rendered). Its layout math ran under Node.
- Hypothesis decisions and notes are saved server side through phase 2 endpoints (UNVERIFIED, API not runnable here), with browser storage as fallback.
- Saved default weights are used by the Advanced form and are not applied by the server on its own.
- The auth token is kept in `localStorage`, so an XSS bug would expose it. Content Security Policy and cookie based sessions are not done.
- The job runner is in process. Startup recovery marks interrupted runs failed (single process assumed). The rate limiter is in memory.
- Seed data is served from `data/` JSON. An idempotent seeding function exists but is not run automatically and is UNVERIFIED against a database.
- No `package-lock.json` (npm install blocked here).
- Seed knowledge is a curated starting set, not a complete reference. Domain distance and scores are heuristics.

More detail: [docs/verification-status.md](docs/verification-status.md).
