# Backend and API Contracts: Design

## Approach
Routers in backend/api, services in backend/services, repositories in backend/database. Routers hold no business logic.

## Components
- Pydantic request and response schemas
- Consistent error envelope {error:{code,message,details}}
- Pagination via limit/offset
- Auth with bearer tokens and project-scoped authorization
- Idempotent discovery run creation

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Database schema (spec 8)
- Intelligence engine

## Edge cases and failure handling
- Concurrent discovery runs on one problem
- Large payloads over limit return 413
- Unknown enum values
- Soft-deleted parents
- Expired tokens

## Testing strategy
- Contract tests per endpoint (need fastapi, unverified in sandbox)
- Authorization matrix tests
- Error envelope shape test
- Pagination bounds test

## Acceptance criteria traceability
- AC1: All endpoints are under /api/v1
- AC2: Validation errors return 422 with the error envelope
- AC3: Unauthorized returns 401, forbidden 403, missing 404
- AC4: List endpoints accept limit (max 100) and offset
- AC5: Contract in docs/api-contracts.md matches OpenAPI output
