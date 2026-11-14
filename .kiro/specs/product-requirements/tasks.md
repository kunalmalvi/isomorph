# Product Requirements: Tasks

- [ ] T1. Implement: Users, organizations, projects and role-based membership
- [ ] T2. Implement: Problem intake with entities, relationships, constraints, variables, assumptions and evidence
- [ ] T3. Implement: Discovery sessions that run the engine and persist results
- [ ] T4. Implement: Reports and archive of past work
- [ ] T5. Test: Create problem happy path and validation failures
- [ ] T6. Test: Project membership authorization matrix
- [ ] T7. Test: Provenance field present on all returned claims
- [ ] T8. Test: Empty-match response shape
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1-T4 written in backend/api, backend/services and backend/database. T5-T8 tests are in tests/platform/test_api.py.
- UNVERIFIED: the API tests are skipped without FastAPI. The orchestrator, run stores and reports are executed by stdlib tests.
- Checkboxes above are the original plan. Treat this section as the current state.
