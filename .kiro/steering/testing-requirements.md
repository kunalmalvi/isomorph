# Testing Requirements
- Engine, experiments and knowledge base tests use only the standard library and must run with `cd backend && python3 -m pytest tests -q`.
- Tests needing fastapi, sqlalchemy, pydantic, numpy or networkx use pytest.importorskip and are reported as unverified when skipped.
- Every feature ships with tests for the happy path, validation failure and at least one edge case.
- Determinism tests: same seed and input give identical output.
- No time or network dependent tests.
- Report honestly which tests ran and which were skipped. Do not claim verification that did not run.
- Label anything that did not run as UNVERIFIED in docs/verification-status.md. Phase 2 items that could not run: API tests, vitest, Playwright, Docker builds, PostgreSQL migration.

## Concrete rules from the code (phase 3)
- Run order for a full check: `python3 -m compileall -q backend scripts`, `python3 scripts/validate_seed_data.py`, `cd backend && python3 -m pytest tests -q`, `python3 scripts/run_demo.py`, `python3 scripts/evaluate_benchmarks.py` (MRR 0.9286 at the end of phase 3 work).
- Tests are grouped in backend/tests/intelligence (engine, seed data, demo) and backend/tests/platform (security, uploads, rate limit, providers, orchestrator, API, migration schema, phase follow ups).
- tests/platform/test_api.py is skipped without FastAPI. Do not cite it as evidence that the API works.
- Provider tests use a mocked transport. No test may open a socket or sleep for real time.
- Every bug fix adds a test named for the behavior, for example `test_pdf_is_stored_and_flagged_not_interpreted`.
- When a count changes, update docs/verification-status.md in the same commit.
