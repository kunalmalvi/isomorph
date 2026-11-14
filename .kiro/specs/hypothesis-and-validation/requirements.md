# Hypothesis and Validation: Requirements

## Overview
Generates falsifiable hypotheses from transformations and validates them with deterministic simulation and evidence checks.

## Requirements
1. Hypothesis with statement, prediction, falsifier, provenance
2. Experiment configuration and seeded runs
3. Result records with metrics and seed
4. Validation record states: untested, supported, refuted, inconclusive

## User stories
- As a researcher, I want to get a falsifiable hypothesis, so that I can test it.
- As a researcher, I want to re-run an experiment with the same seed, so that I get identical results.
- As a reviewer, I want to see that simulations are models, not real-world proof, so that claims stay honest.

## Acceptance criteria
1. Each hypothesis states a prediction and a falsifier
2. Experiment runs record seed, config hash and code version
3. Same seed and config give identical results
4. Validation never reports 'supported' from simulation alone without a labelled caveat
5. Hypotheses from AI providers are tagged ai_hypothesis

## Dependencies
- Mapping and transformation

## Edge cases
- Non-deterministic provider output
- Experiment timeout
- Conflicting results across runs
- Missing baseline

## Test cases
- Seed reproducibility
- Falsifier presence
- Caveat labelling
- Result state transitions

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 prediction and falsifier | intelligence/test_reasoning.py::test_hypotheses_have_prediction_falsifier_and_six_categories |
| AC2 metadata recorded | test_reasoning.py::test_experiments_are_reproducible_and_record_metadata |
| AC3 same seed same result | test_reasoning.py::test_experiments_are_reproducible_and_record_metadata, test_validation_reproducible_and_caveat_labelled; platform/test_derivation_reports.py::test_run_arms_deterministic_and_rejects_missing_model |
| AC4 caveat, no supported from templates | test_reasoning.py::test_validation_reproducible_and_caveat_labelled; test_review_fixes.py::test_template_experiments_never_reach_supported, test_rolling_experiments_keep_full_outcome_range |
| AC5 ai_hypothesis tag | platform/test_orchestrator.py::test_ai_output_is_labelled_ai_hypothesis |
| Validation states | test_reasoning.py::test_validation_untested_refuted_and_inconclusive_states; test_derivation_reports.py::test_validate_hypothesis_untested_without_experiment |
| Physics sanity | test_reasoning.py::test_strip_rolling_model_physics_sanity, test_queueing_bigger_buffer_loses_less, test_gaussian_and_cg_agree |

## Edge case status (phase 3)
- Unknown concept: No experiment is produced (test_unknown_concept_has_no_experiment).
- Unset rolling variable: Falls back to capped templates (test_rolling_with_unset_value_falls_back_instead_of_raising).
- Edited hypothesis keeps old experiment: PATCH clears the experiment. Code only, API test skipped (UNVERIFIED).
