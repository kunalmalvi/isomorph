# Testing Requirements
- Engine, experiments and knowledge base tests use only the standard library and must run with `cd backend && python3 -m pytest tests -q`.
- Tests needing fastapi, sqlalchemy, pydantic, numpy or networkx use pytest.importorskip and are reported as unverified when skipped.
- Every feature ships with tests for the happy path, validation failure and at least one edge case.
- Determinism tests: same seed and input give identical output.
- No time or network dependent tests.
- Report honestly which tests ran and which were skipped. Do not claim verification that did not run.
