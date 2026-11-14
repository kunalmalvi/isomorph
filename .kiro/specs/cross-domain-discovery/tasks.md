# Cross-Domain Discovery: Tasks

- [ ] T1. Implement: Candidate retrieval by fingerprint similarity
- [ ] T2. Implement: Scoring with weights 25 functional, 25 relationship, 20 topological, 15 dynamic, 10 constraint, 5 semantic (configurable, must sum to 100)
- [ ] T3. Implement: Domain distance bonus is reported, never hidden in the score
- [ ] T4. Implement: Per-component explanations
- [ ] T5. Test: Weighted sum correctness
- [ ] T6. Test: Weight validation
- [ ] T7. Test: Stable ordering on ties
- [ ] T8. Test: Roller scenario retrieves a cross-domain candidate
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1-T8 done in backend/intelligence/analogy_engine and tests/intelligence/test_matching.py.
- Executed: stdlib tests pass. The roller demo top score is about 36.5 out of 100, see docs/benchmark-notes.md for why.
- Checkboxes above are the original plan. Treat this section as the current state.
