# Product Requirements: Design

## Approach
Frontend (Next.js) -> API (FastAPI) -> services -> intelligence engine and PostgreSQL. See docs/architecture.md.

## Components
- Users, organizations, projects and role-based membership
- Problem intake with entities, relationships, constraints, variables, assumptions and evidence
- Discovery sessions that run the engine and persist results
- Reports and archive of past work

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Backend API and database
- Intelligence engine
- Seed knowledge base

## Edge cases and failure handling
- Empty problem text
- Problem with entities but no relationships
- Duplicate project names inside an organization
- User removed from a project mid-session
- Zero matches above threshold: show honest empty state, not filler

## Testing strategy
- Create problem happy path and validation failures
- Project membership authorization matrix
- Provenance field present on all returned claims
- Empty-match response shape

## Acceptance criteria traceability
- AC1: A problem can be created with at least one entity and one goal; otherwise the API returns 422 with field errors
- AC2: Every displayed claim carries provenance in {source, computation, user, ai_hypothesis}
- AC3: Match score is the weighted sum 25/25/20/15/10/5 and the breakdown is visible
- AC4: Running with no LLM configured works in deterministic local mode
- AC5: No UI control exists without a working backend action
