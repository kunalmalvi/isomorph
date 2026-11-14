# Backend and API Contracts: Tasks

- [ ] T1. Implement: Pydantic request and response schemas
- [ ] T2. Implement: Consistent error envelope {error:{code,message,details}}
- [ ] T3. Implement: Pagination via limit/offset
- [ ] T4. Implement: Auth with bearer tokens and project-scoped authorization
- [ ] T5. Implement: Idempotent discovery run creation
- [ ] T6. Test: Contract tests per endpoint (need fastapi, unverified in sandbox)
- [ ] T7. Test: Authorization matrix tests
- [ ] T8. Test: Error envelope shape test
- [ ] T9. Test: Pagination bounds test
- [ ] T10. Handle edge cases listed in design.md
- [ ] T11. Update docs and record verification status

## Status (phase 2)
- T1-T5, T10 written (backend/api); phase 2 added annotations, trusted proxy rate limit key, bounded SSE and restart recovery. T6-T9 tests exist in tests/platform/test_api.py.
- UNVERIFIED: FastAPI and Pydantic are not installable here, so the API never ran. Stdlib parts (rate limiter, error envelope helper, SSE framing, recovery, annotation store) are tested in tests/platform.
- Checkboxes above are the original plan. Treat this section as the current state.

## Status (phase 3)
- Phase 3: uploads for PDF and images are stored and returned with interpreted=false and a note. Default SSE stream duration is 15 s (SSE_MAX_SECONDS, valid range 1 to 600); sizing is in docs/api-contracts.md. Startup annotation cleanup and project delete purge are UNVERIFIED (api/main.py, api/routers/projects.py).
- Requirement to test mapping is in requirements.md.
