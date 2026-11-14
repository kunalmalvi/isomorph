# Testing and Deployment: Design

## Approach
CI pipeline: compileall, validate_seed_data, pytest, then (where available) frontend build and Playwright.

## Components
- pytest suites for engine, experiments, knowledge base (stdlib only)
- Optional-dependency tests guarded with importorskip
- Frontend vitest and Playwright specs
- docker-compose with db, backend, frontend
- scripts/run_demo.py end to end demo

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- All other specs

## Edge cases and failure handling
- CI without network
- Postgres unavailable
- Port conflicts
- Flaky time-dependent tests (forbidden; use seeded clocks)

## Testing strategy
- Demo script exit code 0
- Skip reporting
- Compose config lint (not runnable in sandbox)

## Acceptance criteria traceability
- AC1: cd backend && python3 -m pytest tests -q passes in a stdlib-only environment
- AC2: Tests needing absent packages are skipped and listed as unverified
- AC3: Compose file defines healthchecks
- AC4: Secrets come from environment, .env.example has placeholders only
- AC5: Docs state what was and was not verified
