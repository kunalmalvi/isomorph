# Frontend and Design System: Tasks

- [ ] T1. Implement: Screens: dashboard, projects, problem intake, discovery, structural model, matches, mapping, transformation, hypotheses, experiments, validation, archive, reports, settings
- [ ] T2. Implement: Shared components: Card, Table, ScoreBar, ProvenanceBadge, GraphView, EmptyState, ErrorState, LoadingState
- [ ] T3. Implement: Typed API client generated from docs/api-contracts.md
- [ ] T4. Implement: Accessible, keyboard navigable, responsive layout
- [ ] T5. Test: Component render tests (vitest, not runnable in sandbox)
- [ ] T6. Test: Playwright flow: create project, run discovery (not runnable in sandbox)
- [ ] T7. Test: Accessibility audit checklist
- [ ] T8. Handle edge cases listed in design.md
- [ ] T9. Update docs and record verification status

## Status (phase 2)
- T1-T4 written under frontend/, including the phase 2 3D Discovery Universe view (frontend/components/graph/universe-3d.tsx, pure layout in frontend/lib/universe-layout.ts).
- UNVERIFIED: npm install is blocked. Only pure lib modules ran under Node type stripping. T5 and T6 are written, never run. T7 not done.
- Checkboxes above are the original plan. Treat this section as the current state.

## Status (phase 3)
- Phase 3: no frontend code changed. All frontend items remain UNVERIFIED (no npm, tsc or vitest).
- Requirement to test mapping is in requirements.md.
