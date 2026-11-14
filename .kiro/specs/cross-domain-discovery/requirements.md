# Cross-Domain Discovery: Requirements

## Overview
Searches the knowledge base of domains, systems and mechanisms for structurally similar candidates and ranks them.

## Requirements
1. Candidate retrieval by fingerprint similarity
2. Scoring with weights 25 functional, 25 relationship, 20 topological, 15 dynamic, 10 constraint, 5 semantic (configurable, must sum to 100)
3. Domain distance bonus is reported, never hidden in the score
4. Per-component explanations

## User stories
- As a researcher, I want to see top-N matches from distant domains, so that I get non-obvious ideas.
- As a researcher, I want to adjust weights, so that I can explore sensitivity.
- As a reviewer, I want to see the component breakdown, so that I can audit a score.

## Acceptance criteria
1. Score equals the weighted sum of components, each in [0,1], total in [0,100]
2. Weights that do not sum to 100 are rejected
3. Same-domain matches are labelled as such
4. Results are sorted by score then by id for stable ordering
5. Matches below threshold are excluded and the threshold is shown

## Dependencies
- Structural DNA engine
- Seed knowledge (spec 8)

## Edge cases
- Empty knowledge base
- Ties in score
- Candidate with missing dynamics data (component scored 0 and flagged)
- Very large candidate set (top-k pruning)

## Test cases
- Weighted sum correctness
- Weight validation
- Stable ordering on ties
- Roller scenario retrieves a cross-domain candidate

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 weighted sum | intelligence/test_matching.py::test_score_is_weighted_sum_of_bounded_components, test_custom_weights_change_score |
| AC2 weights sum to 100 | test_matching.py::test_weights_must_sum_to_100; test_schemas_graph.py::test_weights_validation; test_orchestrator.py::test_config_validation |
| AC3 same-domain labelled | test_matching.py::test_cross_domain_filter_threshold_and_stable_order |
| AC4 stable order | test_matching.py::test_cross_domain_filter_threshold_and_stable_order |
| AC5 threshold | test_matching.py::test_cross_domain_filter_threshold_and_stable_order |
| Domain distance reported not scored | test_matching.py::test_domain_distance_reported_not_scored |
| Empty knowledge base | test_matching.py::test_empty_knowledge_base_returns_empty_report |
| Missing dynamics flagged | test_matching.py::test_missing_dynamics_flagged |
| Benchmark quality | test_matching.py::test_negative_lookalikes_score_below_positives_on_benchmark; python3 scripts/evaluate_benchmarks.py (MRR 0.9286) |

## Edge case status (phase 3)
- Candidate set size: Top-k pruning is not implemented; the seed set is small. Not tested.
- Declared feedback without a loop: Ignored and flagged (test_declared_feedback_without_a_loop_is_ignored_and_flagged).
