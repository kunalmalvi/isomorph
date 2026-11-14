# Testing and Deployment: Tasks

- [ ] T1. Implement: pytest suites for engine, experiments, knowledge base (stdlib only)
- [ ] T2. Implement: Optional-dependency tests guarded with importorskip
- [ ] T3. Implement: Frontend vitest and Playwright specs
- [ ] T4. Implement: docker-compose with db, backend, frontend
- [ ] T5. Implement: scripts/run_demo.py end to end demo
- [ ] T6. Test: Demo script exit code 0
- [ ] T7. Test: Skip reporting
- [ ] T8. Test: Compose config lint (not runnable in sandbox)
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1, T2, T5, T6, T7 done. T3 and T4 written.
- Backend suite: 167 passed, 2 skipped after phase 2. UNVERIFIED: vitest, Playwright, docker-compose and Dockerfiles never ran. T8 (compose lint) not done. No package-lock.json exists.
- Checkboxes above are the original plan. Treat this section as the current state.
