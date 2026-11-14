# Structural DNA Engine: Requirements

## Overview
Converts a problem or a known system into a structural model (typed graph) and a structural fingerprint used for matching.

## Requirements
1. Perception: extract entities, relations, constraints, variables from text and structured input
2. Structural model: typed directed graph with roles and dynamics
3. Fingerprint: functional, relational, topological, dynamic, constraint and semantic feature vectors
4. Deterministic: same input gives same fingerprint

## User stories
- As a researcher, I want to get a structural model from my description, so that I see the abstract skeleton of my problem.
- As a engine, I want to compute a stable fingerprint, so that matching is reproducible.
- As a reviewer, I want to see which text spans produced each element, so that I can verify extraction.

## Acceptance criteria
1. Fingerprint is identical across runs for identical input
2. Each node and edge records provenance and source span when from text
3. Unknown relation types are kept as 'unclassified' and flagged, not dropped
4. Graph with a single node yields a valid fingerprint with topology features zeroed
5. Fingerprint schema is versioned

## Dependencies
- None (foundation)

## Edge cases
- Disconnected graphs
- Self loops and parallel edges
- Cycles
- Empty input
- Non-English text: reported as low confidence

## Test cases
- Fingerprint determinism
- Graph metric correctness on known graphs
- Extraction of roller scenario entities
- Unclassified relation handling

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 deterministic fingerprint | intelligence/test_perception_fingerprint.py::test_fingerprint_deterministic_versioned_fixed_length, test_determinism_of_perception |
| AC2 provenance and spans | test_perception_fingerprint.py::test_roller_entities_relations_variables_and_constraint, test_facts_inferences_assumptions_unknowns_are_separated |
| AC3 unclassified relation flagged | test_schemas_graph.py::test_unknown_relation_is_kept_as_unclassified_and_flagged |
| AC4 single node | test_perception_fingerprint.py::test_single_node_graph_has_zero_topology |
| AC5 versioned schema | test_fingerprint_deterministic_versioned_fixed_length |
| Structure sensitivity | test_fingerprint_changes_when_structure_changes |
| Graph metrics | test_schemas_graph.py::test_degrees_scc_cycles_depth, test_feedback_loop_polarity, test_max_flow_clrs_example, test_centrality_on_path_and_pagerank, test_motifs_feed_forward_and_empty_graph |
| Embedding | test_perception_fingerprint.py::test_semantic_embedding_is_lexical_unit_norm_and_deterministic |

## Edge case status (phase 3)
- Decimals in text: Not split into sentences (test_decimal_numbers_not_split_into_sentences).
- Self loops, parallel edges, disconnected graphs: test_self_loop_and_parallel_edges, test_disconnected_graph_metrics.
- CSV input: test_csv_perception_and_hooks_unavailable.
