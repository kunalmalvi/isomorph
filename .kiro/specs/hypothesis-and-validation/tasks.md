# Hypothesis and Validation: Tasks

- [ ] T1. Implement: Hypothesis with statement, prediction, falsifier, provenance
- [ ] T2. Implement: Experiment configuration and seeded runs
- [ ] T3. Implement: Result records with metrics and seed
- [ ] T4. Implement: Validation record states: untested, supported, refuted, inconclusive
- [ ] T5. Test: Seed reproducibility
- [ ] T6. Test: Falsifier presence
- [ ] T7. Test: Caveat labelling
- [ ] T8. Test: Result state transitions
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1-T8 done (hypothesis_engine, validation_engine, experiments/), plus server side decisions and notes in phase 2.
- Executed: tests/intelligence/test_reasoning.py, test_review_fixes.py and the end to end test in test_phase2_platform.py. Template experiments are labelled illustrative and capped at inconclusive.
- Checkboxes above are the original plan. Treat this section as the current state.

## Status (phase 3)
- Phase 3: no engine change. The roller model's material parameters are placeholders; see docs/benchmark-notes.md.
- Requirement to test mapping is in requirements.md.
