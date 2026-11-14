# Structural DNA Engine: Tasks

- [ ] T1. Implement: Perception: extract entities, relations, constraints, variables from text and structured input
- [ ] T2. Implement: Structural model: typed directed graph with roles and dynamics
- [ ] T3. Implement: Fingerprint: functional, relational, topological, dynamic, constraint and semantic feature vectors
- [ ] T4. Implement: Deterministic: same input gives same fingerprint
- [ ] T5. Test: Fingerprint determinism
- [ ] T6. Test: Graph metric correctness on known graphs
- [ ] T7. Test: Extraction of roller scenario entities
- [ ] T8. Test: Unclassified relation handling
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1-T8 done (perception, structural_model, graph_engine, fingerprint).
- Executed: tests/intelligence/test_perception_fingerprint.py and test_schemas_graph.py.
- Checkboxes above are the original plan. Treat this section as the current state.

## Status (phase 3)
- Phase 3: perception gained lowercase and singular normalization and a synonym table. Node labels keep the user's wording. The semantic embedding is lexical, not a learned model.
- Requirement to test mapping is in requirements.md.
