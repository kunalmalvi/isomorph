# Mapping and Transformation: Requirements

## Overview
Aligns source and target structures element by element and adapts the source solution to the target under constraints.

## Requirements
1. Node and edge mapping with confidence per pair
2. Unmapped and conflicting elements listed explicitly
3. Transformation steps with preconditions and expected effects
4. Constraint check on the transformed solution

## User stories
- As a engineer, I want to see which parts map and which do not, so that I know the limits of the analogy.
- As a engineer, I want to get an ordered list of adaptation steps, so that I can act on them.
- As a reviewer, I want to see constraints violated by a transformation, so that I can reject unsafe ideas.

## Acceptance criteria
1. Mapping is injective on mapped nodes
2. Every unmapped element appears in the output
3. Each transformation step cites the mapping pairs it relies on
4. Violated hard constraints mark the transformation 'blocked'
5. Confidence is computed, with the formula documented

## Dependencies
- Cross-domain discovery

## Edge cases
- No valid mapping exists
- Multiple equally good mappings (all returned up to k)
- Type mismatch between mapped nodes
- Conflicting constraints

## Test cases
- Injectivity property test
- Unmapped reporting
- Constraint blocking
- Deterministic tie-breaking

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 injective | intelligence/test_matching.py::test_mapping_is_injective_and_reports_every_unmapped_element |
| AC2 unmapped listed | test_matching.py::test_mapping_is_injective_and_reports_every_unmapped_element, test_no_valid_mapping_when_roles_disjoint |
| AC3 steps cite pairs | test_reasoning.py and test_generality_and_demo.py::test_demo_end_to_end_distinct_concepts_and_baseline_vs_proposed |
| AC4 blocked on hard constraint | test_reasoning.py::test_constraint_outcomes_and_status, test_bite_condition_validator; test_generality_and_demo.py::test_demo_reduction_is_configurable_and_constraints_block |
| AC5 confidence | test_matching.py::test_identical_graph_maps_fully_and_is_deterministic, test_mapping_distinguishes_rewired_graph |
| Compound constraints | test_reasoning.py::test_compound_expressions_between_and_custom_validator |
| Load distribution | test_reasoning.py::test_load_distribution_conserves_flow_and_splits_by_conductance |

## Edge case status (phase 3)
- Disjoint roles: Returns no valid mapping instead of a forced one.
- Identical graph: Maps fully, deterministic.
