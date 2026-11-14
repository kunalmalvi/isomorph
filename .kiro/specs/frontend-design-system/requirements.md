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
