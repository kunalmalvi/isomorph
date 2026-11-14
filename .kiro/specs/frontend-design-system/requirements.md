# Frontend and Design System: Requirements

## Overview
Next.js (App Router, TypeScript) frontend with a consistent design system covering all workflow screens.

## Requirements
1. Screens: dashboard, projects, problem intake, discovery, structural model, matches, mapping, transformation, hypotheses, experiments, validation, archive, reports, settings
2. Shared components: Card, Table, ScoreBar, ProvenanceBadge, GraphView, EmptyState, ErrorState, LoadingState
3. Typed API client generated from docs/api-contracts.md
4. Accessible, keyboard navigable, responsive layout

## User stories
- As a user, I want to navigate every workflow stage from a project, so that I can follow the pipeline in order.
- As a user, I want to see loading, empty and error states, so that I always know the system state.
- As a user, I want to see a provenance badge on each claim, so that I know how much to trust it.
- As a keyboard user, I want to operate all controls without a mouse, so that the app is accessible.

## Acceptance criteria
1. Every button and form calls a real API endpoint
2. Every list view has loading, empty and error states
3. Color is never the sole carrier of meaning (score bars show numbers)
4. Contrast meets WCAG AA
5. Provenance badge present on every claim card

## Dependencies
- Backend API contracts (spec 3)

## Edge cases
- API timeout
- 401 mid-session redirects to sign-in
- Very large graphs: cap rendered nodes and show a notice
- Long text overflow
- Locale with long strings

## Test cases
- Component render tests (vitest, not runnable in sandbox)
- Playwright flow: create project, run discovery (not runnable in sandbox)
- Accessibility audit checklist

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 controls call real endpoints | Manual review only. No executed test |
| AC2 loading, empty, error states | frontend/tests (vitest) written, never run. UNVERIFIED |
| AC3 score bars show numbers | Review only. UNVERIFIED |
| AC4 WCAG AA contrast | Not measured. UNVERIFIED |
| AC5 provenance badge | Review only. UNVERIFIED |
| Layout math for graph and universe | node frontend/tests/universe-check.mts (executed in phase 2); frontend/tests/unit/universe.test.ts (vitest, never run) |
| Playwright flow | frontend/e2e, never run. UNVERIFIED |

## Edge case status (phase 3)
- Very large graphs: A node cap with a notice is required by the design; rendering is UNVERIFIED.
- SSE reconnect: frontend/services/sse.ts reconnects without a fixed limit and stops after 10 consecutive failures. UNVERIFIED.
- Package lock: npm install --package-lock-only returns 403 in this sandbox, so frontend/package-lock.json does not exist.
