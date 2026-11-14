# API Contracts

Base path: `/api/v1`. JSON only. Status: DESIGN, to be implemented with FastAPI. The authoring sandbox cannot install FastAPI, so the server code is UNVERIFIED there. 66 endpoints across 17 groups.

## Conventions
- Auth: `Authorization: Bearer <token>`. 401 when missing or invalid, 403 when the role is insufficient, 404 when absent.
- Pagination: `limit` (default 20, max 100) and `offset`. Responses: `{"items": [...], "total": n, "limit": n, "offset": n}`.
- Error envelope: `{"error": {"code": "validation_error", "message": "...", "details": [...]}}`.
- Status codes: 200 read, 201 create, 202 accepted async run, 204 delete, 413 too large, 422 validation.
- Every claim object includes `provenance` in source, computation, user, ai_hypothesis.
- Weights in score requests must sum to 100 (default 25, 25, 20, 15, 10, 5); otherwise 422.

## Endpoints
### /api/v1/projects
- `GET /projects`
- `POST /projects`
- `GET /projects/{id}`
- `PATCH /projects/{id}`
- `DELETE /projects/{id}`
- `GET /projects/{id}/members`
- `POST /projects/{id}/members`
- `DELETE /projects/{id}/members/{user_id}`

### /api/v1/problems
- `GET /problems`
- `POST /problems`
- `GET /problems/{id}`
- `PATCH /problems/{id}`
- `DELETE /problems/{id}`
- `POST /problems/{id}/entities`
- `POST /problems/{id}/relationships`
- `POST /problems/{id}/constraints`
- `POST /problems/{id}/variables`
- `POST /problems/{id}/assumptions`
- `POST /problems/{id}/evidence`

### /api/v1/discoveries
- `POST /discoveries`
- `GET /discoveries`
- `GET /discoveries/{id}`
- `GET /discoveries/{id}/matches`
- `POST /discoveries/{id}/cancel`

### /api/v1/structural-models
- `POST /structural-models`
- `GET /structural-models/{id}`
- `GET /structural-models/{id}/graph`

### /api/v1/structural-dna
- `GET /structural-dna/{model_id}`
- `POST /structural-dna/compare`

### /api/v1/domains
- `GET /domains`
- `GET /domains/{id}`
- `GET /domains/{id}/systems`

### /api/v1/knowledge-systems
- `GET /knowledge-systems`
- `GET /knowledge-systems/{id}`
- `GET /knowledge-systems/{id}/graph`

### /api/v1/mechanisms
- `GET /mechanisms`
- `GET /mechanisms/{id}`

### /api/v1/matches
- `GET /matches`
- `GET /matches/{id}`
- `GET /matches/{id}/breakdown`

### /api/v1/mappings
- `POST /mappings`
- `GET /mappings/{id}`

### /api/v1/transformations
- `POST /transformations`
- `GET /transformations/{id}`

### /api/v1/hypotheses
- `GET /hypotheses`
- `POST /hypotheses`
- `GET /hypotheses/{id}`
- `PATCH /hypotheses/{id}`

### /api/v1/experiments
- `POST /experiments`
- `GET /experiments/{id}`
- `POST /experiments/{id}/runs`
- `GET /experiments/{id}/runs/{run_id}`

### /api/v1/validation
- `POST /validation`
- `GET /validation/{id}`
- `GET /validation?hypothesis_id=`

### /api/v1/archive
- `GET /archive`
- `POST /archive/{project_id}`
- `POST /archive/{project_id}/restore`

### /api/v1/reports
- `GET /reports`
- `POST /reports`
- `GET /reports/{id}`
- `GET /reports/{id}/export?format=md|json`

### /api/v1/settings
- `GET /settings`
- `PATCH /settings`
- `GET /settings/providers`
- `PATCH /settings/weights`

## Additional endpoints (implemented beyond the 66 listed)
- `GET /health` liveness.
- `POST /auth/register`, `POST /auth/login` return `{access_token, token_type, expires_in}` (both are rate limited per client address). `GET /auth/me`.
- `POST /problems/{id}/uploads` multipart. Validates size (413), extension and content signature (422). Text and CSV files return a proposed structure and store nothing.
- Stage inspection for a discovery: `GET /discoveries/{id}/stages`, `GET /discoveries/{id}/stages/{stage}`, `PUT /discoveries/{id}/stages/{stage}` (replace output, later stages become `stale`), `POST /discoveries/{id}/stages/{stage}/rerun?mode=downstream|from` (202).
- `GET /discoveries/{id}/events` Server-Sent Events. Event `progress` carries `{run_id, status, completed, total, stages:[{name,status,version,source}]}` on every change. Event `end` carries the final status.
- Stage names: perception, structural_extraction, structural_dna, cross_domain_search, structural_matching, mechanism_mapping, transformation, hypothesis_generation, validation.
- Resources of another user's project answer 404. A project member with too low a role gets 403 (viewer reads, editor writes, owner manages members, archive and delete).

## Key request and response shapes
- `POST /discoveries` body: `{"problem_id": uuid, "weights": {...} | null, "threshold": float | null, "top_k": int}`. Returns 202 with a session `{id, status}`.
- `GET /matches/{id}/breakdown` returns `{"total": float, "components": {"functional": {"score": 0..1, "weight": 25, "explanation": str}, ...}, "domain_distance": float}`.
- `POST /mappings` body: `{"match_id": uuid}`. Returns node pairs, edge pairs, `unmapped_source`, `unmapped_target`, `confidence`.
- `POST /transformations` body: `{"mapping_id": uuid}`. Returns steps, `constraint_report`, `status` in ok or blocked.
- `POST /experiments/{id}/runs` body: `{"seed": int}`. Identical seed and configuration yield identical results.
