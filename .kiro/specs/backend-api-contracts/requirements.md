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
