# Testing and Deployment: Requirements

## Overview
Test strategy, CI checks, and Docker Compose deployment.

## Requirements
1. pytest suites for engine, experiments, knowledge base (stdlib only)
2. Optional-dependency tests guarded with importorskip
3. Frontend vitest and Playwright specs
4. docker-compose with db, backend, frontend
5. scripts/run_demo.py end to end demo

## User stories
- As a developer, I want to run the stdlib test suite anywhere, so that I get quick feedback.
- As a ops, I want to start the stack with one command, so that deployment is repeatable.
- As a reviewer, I want to see which tests actually ran, so that verification claims are honest.

## Acceptance criteria
1. cd backend && python3 -m pytest tests -q passes in a stdlib-only environment
2. Tests needing absent packages are skipped and listed as unverified
3. Compose file defines healthchecks
4. Secrets come from environment, .env.example has placeholders only
5. Docs state what was and was not verified

## Dependencies
- All other specs

## Edge cases
- CI without network
- Postgres unavailable
- Port conflicts
- Flaky time-dependent tests (forbidden; use seeded clocks)

## Test cases
- Demo script exit code 0
- Skip reporting
- Compose config lint (not runnable in sandbox)
