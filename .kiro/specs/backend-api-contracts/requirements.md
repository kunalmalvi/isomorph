# Backend and API Contracts: Requirements

## Overview
FastAPI service under /api/v1 exposing projects, problems, discoveries, structural models, structural DNA, domains, knowledge systems, mechanisms, matches, mappings, transformations, hypotheses, experiments, validation, archive, reports and settings.

## Requirements
1. Pydantic request and response schemas
2. Consistent error envelope {error:{code,message,details}}
3. Pagination via limit/offset
4. Auth with bearer tokens and project-scoped authorization
5. Idempotent discovery run creation

## User stories
- As a API client, I want to get consistent error responses, so that I can handle failures generically.
- As a API client, I want to paginate list endpoints, so that large collections stay fast.
- As a admin, I want to restrict access by project role, so that data is protected.
- As a developer, I want to read OpenAPI docs, so that I can integrate quickly.

## Acceptance criteria
1. All endpoints are under /api/v1
2. Validation errors return 422 with the error envelope
3. Unauthorized returns 401, forbidden 403, missing 404
4. List endpoints accept limit (max 100) and offset
5. Contract in docs/api-contracts.md matches OpenAPI output

## Dependencies
- Database schema (spec 8)
- Intelligence engine

## Edge cases
- Concurrent discovery runs on one problem
- Large payloads over limit return 413
- Unknown enum values
- Soft-deleted parents
- Expired tokens

## Test cases
- Contract tests per endpoint (need fastapi, unverified in sandbox)
- Authorization matrix tests
- Error envelope shape test
- Pagination bounds test

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 under /api/v1 | platform/test_api.py::test_auth_required_and_error_envelope (skipped without FastAPI) |
| AC2 422 with envelope | test_api.py::test_register_login_and_validation; platform/test_rate_limit_uploads.py::test_error_envelope_shape (runs) |
| AC3 401, 403, 404 | test_api.py::test_rbac_viewer_editor_owner, test_project_isolation_between_users, test_lists_hide_deleted_projects_and_non_members_get_404_before_validation |
| AC4 limit and offset | test_api.py::test_pagination_bounds |
| AC5 contract matches OpenAPI | No test. Needs a running app. UNVERIFIED |
| Auth tokens | platform/test_security.py::test_token_roundtrip_expiry_and_tamper, test_alg_none_and_garbage_rejected, test_role_ordering (run) |
| Uploads 413 and type checks | platform/test_rate_limit_uploads.py::test_upload_rejects, test_upload_too_large (run); test_api.py::test_upload_validation |
| Rate limit and trusted proxy | test_rate_limit_uploads.py::test_rate_limiter_window_and_keys; test_phase2_platform.py::test_forwarded_for_ignored_without_trusted_proxy (run) |
| SSE | test_rate_limit_uploads.py::test_sse_format_and_stream; test_phase2_platform.py::test_sse_retry_hint_and_bounded_connection (run) |
| Upload interpretation flag | test_phase3_followups.py::test_interpretation_flag, test_pdf_is_stored_and_flagged_not_interpreted (run) |

## Edge case status (phase 3)
- Concurrent discovery runs on one problem: Job runner rejects a duplicate submission (test_orchestrator.py::test_job_runner_rejects_duplicate_submission, run).
- Large payloads: Upload size limit MAX_UPLOAD_BYTES (5 MiB default) enforced in backend/core/uploads.py, tested.
- Expired tokens: Covered by test_token_roundtrip_expiry_and_tamper.
- Unknown enum values and soft-deleted parents: Written in routers and schemas; only API tests cover them, which are skipped here (UNVERIFIED).
