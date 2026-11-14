# Product Requirements: Requirements

## Overview
ISOMORPH finds structural analogies between a user's problem and solved systems in other domains, maps them, transforms the solution, and proposes testable hypotheses.

## Requirements
1. Users, organizations, projects and role-based membership
2. Problem intake with entities, relationships, constraints, variables, assumptions and evidence
3. Discovery sessions that run the engine and persist results
4. Reports and archive of past work

## User stories
- As a researcher, I want to submit a problem in plain text and structured form, so that I can get a structural model of it.
- As a researcher, I want to see ranked cross-domain matches with a score breakdown, so that I can judge why a match was proposed.
- As a engineer, I want to see a mapping with unmapped elements and violated constraints, so that I know where an analogy breaks.
- As a reviewer, I want to see the provenance of every claim, so that I can separate sourced facts from AI hypotheses.
- As a org admin, I want to manage members and roles, so that access to projects stays controlled.

## Acceptance criteria
1. A problem can be created with at least one entity and one goal; otherwise the API returns 422 with field errors
2. Every displayed claim carries provenance in {source, computation, user, ai_hypothesis}
3. Match score is the weighted sum 25/25/20/15/10/5 and the breakdown is visible
4. Running with no LLM configured works in deterministic local mode
5. No UI control exists without a working backend action

## Dependencies
- Backend API and database
- Intelligence engine
- Seed knowledge base

## Edge cases
- Empty problem text
- Problem with entities but no relationships
- Duplicate project names inside an organization
- User removed from a project mid-session
- Zero matches above threshold: show honest empty state, not filler

## Test cases
- Create problem happy path and validation failures
- Project membership authorization matrix
- Provenance field present on all returned claims
- Empty-match response shape
