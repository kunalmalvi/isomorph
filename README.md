# ISOMORPH

ISOMORPH is a cross-domain structural reasoning platform. You describe a problem in plain language. The platform extracts its structure (components, relations, feedback, constraints), searches a curated knowledge base for systems in other domains with a similar structure, maps mechanisms across, derives candidate transformations and writes testable hypotheses. Hypotheses can be checked with seeded simulations.

Everything it produces is a hypothesis from structural analogy. Nothing is proven, and simulation outcomes are not real world evidence. Every claim carries a provenance label: `source`, `computation`, `user` or `ai_hypothesis`.

Default mode is deterministic and offline. No API key and no network are needed. Remote AI providers are optional and only used for the perception stage.

## Quick start (Python 3.9+ only)
```bash
git clone https://github.com/kunalmalvi/isomorph.git && cd isomorph
python3 ./isomorph serve
```
The app opens in your browser at http://localhost:8765. It needs no install, no Docker, no Node and no Postgres. Data is kept in `~/.isomorph` (set `ISOMORPH_HOME` to move it). On a fresh start, click "Load the roller demo" to see a full run in seconds.

Run it from a checkout. A plain `pip install .` (wheel) ships the code but not the `data/` knowledge files, so `serve` and `doctor` report an error; use `pip install -e .` (what `./install.sh` does) or set `ISOMORPH_DATA_DIR`. `restore` and `reset` refuse to run while a server uses the same data directory; stop the server first. Without a token the server only answers requests addressed to localhost and rejects cross-origin and non-JSON writes.

Optional: `./install.sh` creates `.venv` and installs an `isomorph` command (`.venv/bin/isomorph serve`). `make run`, `make test`, `make doctor` and `make backup` are shortcuts. `python3 ./isomorph doctor` checks your setup, `backup` and `restore` manage the database, and `analyze "your problem text"` prints a report without the UI.

> **Read the status section first.** The zero-dependency app (stdlib HTTP server, SQLite, bundled web UI, CLI) is tested by running it. The browser UI has been syntax checked and served over HTTP but never rendered in a real browser, because the authoring sandbox had none. The older FastAPI, Next.js and Postgres stack below is optional and still unverified. See [What is complete, incomplete and unverified](#status).

## Honest limits
- Perception is keyword and sentence-pattern based. Unusual wording can be missed, so check the extracted structure in the Progress tab and edit it.
- Uploads: .txt, .md, .csv and text PDFs (best effort, stdlib extractor tested only on generated PDFs) are read. JSON, scanned or encrypted PDFs and images are stored but reported as not interpreted. Remote vision is UNVERIFIED.
- Perception of unfamiliar words is better but weak: on a 25 problem held-out set written by the author, role coverage went from 0.22 to 0.44 and accuracy from 0.12 to 0.40, and about 1 in 7 assigned roles is wrong. See `docs/benchmark-notes.md`.
- Benchmarks: the 7 pair tuning set was seen during matcher development. A separate 20 query held-out set exists with graded labels, a labelling guide and a review template (`docs/labelling-guide.md`, `docs/label-review-template.md`). All labels are author-written and no independent review has happened, and the author also wrote the matcher, so the held-out set is not independent. Run `python3 scripts/evaluate_heldout.py`. Citations in the knowledge base are unverified. See `docs/benchmark-notes.md`.
- The roller demo scores about 37.5 out of 100 against its best analog (VAV zone control, with 36.5 second), which is a weak match. Its material parameters are recalled and unverified (no source was checked, silver is a low confidence estimate), so its simulations are capped at inconclusive and its uncertainty ranges are conceptual, not verified or certified engineering analysis.
- Runs execute in the server process (thread pool). A restart marks interrupted runs failed and you can resume them.
- Single user, local mode. Binding a non-local address requires `ISOMORPH_TOKEN`; put a TLS proxy in front if you expose it.

## Repository layout
| Path | Contents |
|---|---|
| `backend/intelligence`, `backend/experiments`, `backend/knowledge_base` | Pure standard library engine, seeded experiments, knowledge loader |
| `backend/isomorph_app` | Zero-dependency server, CLI and bundled web UI (`static/`) |
| `backend/api`, `backend/services`, `backend/database`, `backend/migrations` | FastAPI app, orchestrator and job runner, SQLAlchemy models, Alembic |
| `backend/ai_providers` | Local deterministic provider plus OpenAI, Gemini and Anthropic adapters |
| `frontend/` | Optional Next.js App Router, TypeScript strict, Tailwind |
| `data/` | Seed domains, systems, mechanisms, benchmark problems, demo input and output |
| `docs/` | Architecture, API contracts, schemas, database design, deployment, demo script, verification status |
| `.kiro/` | Specs, steering and hooks used to build the project |

## Developer quick start: engine scripts and tests
```bash
python3 scripts/validate_seed_data.py
python3 scripts/run_demo.py          # the flagship roller scenario, end to end, prints results
cd backend && python3 -m pytest tests -q -rs
```

## Optional advanced path: full stack with Docker (UNVERIFIED)
For a multi-user deployment with PostgreSQL. Most people want the quick start above. A single-container variant with SQLite is `docker compose -f docker-compose.simple.yml up --build` (also UNVERIFIED).

```bash
cp .env.example .env                 # set POSTGRES_PASSWORD and ISOMORPH_SECRET_KEY
docker compose up --build
```
Open http://localhost:3000, register an account, and start with New Discovery. API docs are at http://localhost:8000/api/v1/docs. The backend container runs `alembic upgrade head` before starting. `NEXT_PUBLIC_API_URL` is baked into the frontend image at build time and must be reachable from your browser.

## Optional advanced path: full stack without Docker (UNVERIFIED)
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
| Everything runnable (engine, SQLite app, HTTP server, CLI, UI assets) | `cd backend && python3 -m pytest tests -q -rs` | 208 passed, 2 skipped (FastAPI and SQLAlchemy missing) |
| UI helper functions | `node backend/tests/platform/ui_helpers.test.mjs` (also run by pytest) | Passing |
| Backend API with FastAPI | same command, after installing `requirements-dev.txt` | Skipped in the sandbox, never run |
| Frontend unit (vitest) | `cd frontend && npm test` | Written, never run |
| Frontend type check and lint | `npm run typecheck`, `npm run lint` | Never run |
| End to end (Playwright) | start the stack, then `cd frontend && npx playwright install chromium && npm run test:e2e` | Written, never run |

E2E specs register a fresh user per test, so they can run against an empty database. Override `E2E_BASE_URL` if the frontend is not on port 3000.

## Flagship demo
The demo scenario reduces copper or silver strip thickness with rolls. Walkthrough: [docs/demo-script.md](docs/demo-script.md). Sample report: [docs/sample-discovery-report.md](docs/sample-discovery-report.md). The demo material model is a clearly labelled demo only scenario with labelled but unverified parameters (see docs/verification-status.md, Phase 7). It omits roll flattening, tension, temperature, roll deflection and edge effects, and was not compared with measured mill data.

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
- Frontend: all 11 sections, command palette, API client, SSE client, vitest and Playwright specs. `npm install` was blocked, so nothing was built, type checked against real React and Next types, linted or rendered. A partial TypeScript pass without the React and Next type packages showed only errors caused by those missing packages. Phase 2 backend result: 169 passed, 2 skipped. Pure logic modules (universe layout, formatting, CSV, SSE parsing, graph layout, comparison limit) were executed under Node and behaved as expected.
- `docker-compose.yml`, `frontend/Dockerfile`, `backend/Dockerfile`: never built.

**Known gaps (by design in this version)**
- In the FastAPI stack, PDF and image uploads are validated but not interpreted. The zero-dependency app reads text PDFs (best effort) and reports scans and images as not interpreted (no OCR).
- The 3D Discovery Universe view is a dependency free SVG projection and is UNVERIFIED (never rendered). Its layout math ran under Node.
- Hypothesis decisions and notes are saved server side through phase 2 endpoints (UNVERIFIED, API not runnable here), with browser storage as fallback.
- Saved default weights are used by the Advanced form and are not applied by the server on its own.
- The auth token is kept in `localStorage`, so an XSS bug would expose it. Content Security Policy and cookie based sessions are not done.
- The job runner is in process. Startup recovery marks interrupted runs failed (single process assumed, also for the JSON annotation store). The rate limiter is in memory.
- Seed data is served from `data/` JSON. An idempotent seeding function exists but is not run automatically and is UNVERIFIED against a database.
- No `package-lock.json` (npm install blocked here).
- Seed knowledge is a curated starting set, not a complete reference. Domain distance and scores are heuristics.

More detail: [docs/verification-status.md](docs/verification-status.md).
