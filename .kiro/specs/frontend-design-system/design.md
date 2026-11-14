# Frontend and Design System: Design

## Approach
Design tokens in a single theme file, components under frontend/components, pages under frontend/app, API client under frontend/lib/api.

## Components
- Screens: dashboard, projects, problem intake, discovery, structural model, matches, mapping, transformation, hypotheses, experiments, validation, archive, reports, settings
- Shared components: Card, Table, ScoreBar, ProvenanceBadge, GraphView, EmptyState, ErrorState, LoadingState
- Typed API client generated from docs/api-contracts.md
- Accessible, keyboard navigable, responsive layout

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Backend API contracts (spec 3)

## Edge cases and failure handling
- API timeout
- 401 mid-session redirects to sign-in
- Very large graphs: cap rendered nodes and show a notice
- Long text overflow
- Locale with long strings

## Testing strategy
- Component render tests (vitest, not runnable in sandbox)
- Playwright flow: create project, run discovery (not runnable in sandbox)
- Accessibility audit checklist

## Acceptance criteria traceability
- AC1: Every button and form calls a real API endpoint
- AC2: Every list view has loading, empty and error states
- AC3: Color is never the sole carrier of meaning (score bars show numbers)
- AC4: Contrast meets WCAG AA
- AC5: Provenance badge present on every claim card
