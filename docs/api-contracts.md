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
  A connection lasts at most `SSE_MAX_SECONDS` (default 15) and polls the run about once per second. The stream starts with `retry: 2000`. When the limit is reached the server sends event `timeout` (`{reconnect: true}`) and closes. The client reconnects with the `Last-Event-ID` header, ids continue from that value, and the first event of the new connection is the current snapshot. Event `error` is sent when the run no longer exists.
  Sizing: the stream is a synchronous generator, so each open connection holds one thread of the server's request thread pool (Starlette default 40) for up to `SSE_MAX_SECONDS`. One process therefore serves roughly 40 concurrent watchers, minus threads used by ordinary requests. A shorter limit frees threads sooner but makes every watcher reconnect more often: 15 seconds means about one extra request per watcher every 15 seconds (4 per minute), each with a database read of the run. Each connection polls once per second. Raise `SSE_MAX_SECONDS` only if reconnect load matters more than thread availability. UNVERIFIED under load (no load test was run).
- Hypothesis decisions and notes, scoped to a discovery and keyed by the generated hypothesis id (for example `H1-close_feedback_loop`):
  - `GET /discoveries/{id}/annotations` returns `{items: {<hypothesis_id>: {hypothesis_id, decision, note, provenance: "user", updated_at}}}` (viewer).
  - `PUT /discoveries/{id}/annotations/{hypothesis_id}` with `{decision: none|saved|rejected|promoted, note: string up to 5000}` (editor). 404 when the id is not a hypothesis of this run, 422 on an invalid decision.
  - `DELETE /discoveries/{id}/annotations/{hypothesis_id}` returns 204 (editor).
  - Annotations never change the hypothesis text or its validation outcome. They are stored as JSON files under `ISOMORPH_STATE_DIR/annotations`, or in memory (lost on restart) when that variable is empty. There is no SQL table for them because `docs/database-design.md` has none that fits.
- Rate limit client key: the direct peer address. `X-Forwarded-For` is used only when the peer matches an entry of `TRUSTED_PROXIES` (comma separated IPs or CIDR networks). The header is read from the right, skipping trusted proxies, so values a client prepends are ignored.
- Restart recovery: at API startup every run left `queued` or `running` is set to `failed` with error `interrupted by restart`, and its running stage is failed with the same reason. Completed stage outputs are kept, so `rerun` resumes. This assumes a single API process owns the database.
- Seeding: `python -m database.seed [--dry-run]` loads `data/` into domains, sources, domain_systems, system_entities, system_relationships and mechanisms. It is idempotent and is never run at startup.
- Stage names: perception, structural_extraction, structural_dna, cross_domain_search, structural_matching, mechanism_mapping, transformation, hypothesis_generation, validation.
- Resources of another user's project answer 404. A project member with too low a role gets 403 (viewer reads, editor writes, owner manages members, archive and delete).

## Key request and response shapes
- `POST /discoveries` body: `{"problem_id": uuid, "weights": {...} | null, "threshold": float | null, "top_k": int}`. Returns 202 with a session `{id, status}`.
- `GET /matches/{id}/breakdown` returns `{"total": float, "components": {"functional": {"score": 0..1, "weight": 25, "explanation": str}, ...}, "domain_distance": float}`.
- `POST /mappings` body: `{"match_id": uuid}`. Returns node pairs, edge pairs, `unmapped_source`, `unmapped_target`, `confidence`.
- `POST /transformations` body: `{"mapping_id": uuid}`. Returns steps, `constraint_report`, `status` in ok or blocked.
- `POST /experiments/{id}/runs` body: `{"seed": int}`. Identical seed and configuration yield identical results.
