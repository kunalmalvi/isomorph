# Implementation Plan

## Scope
Build ISOMORPH: Next.js frontend, FastAPI backend, PostgreSQL with pgvector, and a pure-Python deterministic intelligence engine.

## Milestones
| # | Milestone | Content | Verifiable in sandbox |
|---|---|---|---|
| M1 | Planning artifacts | docs, 9 specs, 7 steering docs, 6 hooks | Yes (file checks, JSON parse) |
| M2 | Engine foundation | graph, perception, structural model, fingerprint, seed data and validator | Yes (pytest, stdlib) |
| M3 | Engine reasoning | analogy, mapping, transformation, constraint, hypothesis, validation, experiments, learning, demo script (roller scenario) | Yes (pytest, run_demo.py) |
| M4 | API, database, frontend, deployment | FastAPI routers, SQLAlchemy models, Alembic, Next.js app, docker-compose, README | Syntax only (compileall) |

## Dependency map
- M2 has no dependencies. M3 depends on M2. M4 depends on the schemas from M2 and M3 and on docs/api-contracts.md.
- Spec dependencies: structural-dna-engine -> cross-domain-discovery -> mapping-and-transformation -> hypothesis-and-validation. database-knowledge-architecture feeds discovery. backend-api-contracts wraps the engine. frontend-design-system consumes the API contracts. testing-and-deployment spans all.

## Sandbox limits (honest statement)
- Network to PyPI and npm returns HTTP 403. No packages can be installed.
- Installed: Python 3.11, pytest, Node 22, npm. Not installed: fastapi, pydantic, sqlalchemy, alembic, numpy, scipy, networkx, sympy, scikit-learn, Postgres.
- Docker CLI exists but does not function (no conmon), so `docker build` and `docker compose` cannot run.
- Consequences:
  - The engine is written with the standard library only and is the part that is actually tested.
  - FastAPI, SQLAlchemy, Alembic and Next.js code is written to spec and only syntax-checked. It is UNVERIFIED at runtime and must be labelled so.
  - Frontend build, type check, vitest and Playwright specs cannot run here.
  - Migrations have not been applied to any database.
  - Python 3.11 is used here; the target is 3.12 or newer.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| API and ORM code has runtime errors undetected in sandbox | High | Keep layers thin, label UNVERIFIED, tests with importorskip for first real run |
| Contract drift between docs and routers | Medium | api-contract-validation hook, single source in docs/api-contracts.md |
| Seed knowledge inaccurate or unsourced | High | Source required per row, validate_seed_data.py, no fabricated citations |
| Analogy scores look authoritative but are heuristic | High | Show breakdown, caveats, domain distance, honest empty states |
| Simulation mistaken for real-world proof | High | Validation caveat labelling, never auto-mark supported from simulation alone |
| pgvector dimension or extension mismatch | Medium | Embeddings optional; lexical fallback in local mode |
| Nondeterminism | Medium | Seeded RNG, determinism tests |

## Definition of done per feature
Build (`python3 -m compileall -q backend scripts`), tests (`cd backend && python3 -m pytest tests -q`), seed validation, and a commit. Skipped tests are reported.
