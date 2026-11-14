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

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 problem needs entity and goal | platform/test_api.py::test_problem_children_validation (skipped without FastAPI); platform/test_orchestrator.py::test_create_run_input_validation (runs) |
| AC2 provenance on claims | intelligence/test_schemas_graph.py::test_roundtrip_and_provenance_enum; platform/test_derivation_reports.py::test_report_has_provenance_disclaimer_and_marks_missing_stages |
| AC3 25/25/20/15/10/5 breakdown | intelligence/test_matching.py::test_score_is_weighted_sum_of_bounded_components |
| AC4 no LLM needed | platform/test_ai_providers.py::test_local_default_no_key_and_deterministic, test_local_refuses_unsupported_task_instead_of_fabricating; platform/test_orchestrator.py::test_full_run_all_stages_inspectable |
| AC5 no dead UI | Review only. UNVERIFIED |
| Roles and membership | platform/test_api.py::test_rbac_viewer_editor_owner, test_last_owner_cannot_be_removed (skipped without FastAPI) |
| Archive and reports | test_api.py::test_archive_and_restore (skipped); test_derivation_reports.py (runs) |
| Whole pipeline | test_generality_and_demo.py::test_unrelated_text_problem_runs_through_whole_pipeline; python3 scripts/run_demo.py (exit 0) |

## Edge case status (phase 3)
- Non-English or empty input: test_perception_fingerprint.py::test_empty_and_non_english_input.
- Unfamiliar phrasing: Phase 3 normalization and SYNONYMS table in backend/intelligence/perception/service.py; test_synonyms_map_unfamiliar_words_to_roles_and_keep_user_wording, test_plurals_and_case_are_normalised, test_unknown_word_still_has_no_role.
- PDF and image problem uploads: Stored, not read, flagged interpreted=false.
