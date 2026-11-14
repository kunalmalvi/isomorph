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

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 stdlib suite | cd backend && python3 -m pytest tests -q (177 passed, 2 skipped at the start of FEAT-002) |
| AC2 skips listed | docs/verification-status.md section Skipped tests and reasons |
| AC3 compose healthchecks | Written, never run. UNVERIFIED |
| AC4 secrets in env | platform/test_rate_limit_uploads.py::test_settings_defaults_and_validation; platform/test_ai_providers.py::test_provider_status_has_no_key_material |
| AC5 honest docs | docs/verification-status.md |
| Demo and benchmark | python3 scripts/run_demo.py; python3 scripts/evaluate_benchmarks.py; python3 scripts/validate_seed_data.py |
| Provider adapters on mocked transport | platform/test_ai_providers.py::test_openai_request_shape_and_structured_output, test_anthropic_adapter, test_gemini_adapter_and_empty_response, test_retry_on_429_then_success_and_backoff |

## Edge case status (phase 3)
- Network in tests: None; the provider tests use a mocked transport.
- Docker: Docker is broken in the sandbox, builds are UNVERIFIED.
- Package install: pip and npm return 403 here.
