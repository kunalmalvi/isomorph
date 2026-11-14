# UI Design System
- Tokens: one theme file defines color, spacing, radius, type scale. No hard-coded hex values in components.
- Required states for every data view: loading, empty, error, populated.
- Score bars always show the number. Color is never the only signal.
- Provenance badge on every claim card with four variants: source, computation, user, ai_hypothesis.
- Accessibility: WCAG AA contrast, visible focus, labels on inputs, keyboard operable.
- Layout: left navigation by workflow stage, content area, optional detail panel.
- Large graphs: cap rendered nodes and show a notice.
- Visual views such as the 3D Discovery Universe must keep a table or chart with the same data, and carry an UNVERIFIED label until rendered in a browser.

## Concrete rules from the code (phase 3)
- Frontend pure logic goes in frontend/lib (arena.ts, graph-layout.ts, universe-layout.ts, format.ts) so it can be run under Node without a bundler. Components stay thin.
- Hypothesis decisions and notes are saved to the server; notes saves are debounced and ordered, and a newer local edit wins when merging (`mergeAnnotations` in lib/arena.ts). UNVERIFIED, never run.
- The SSE client in frontend/services/sse.ts reconnects with `Last-Event-ID` and gives up after 10 consecutive failures. The server closes streams after `SSE_MAX_SECONDS` on purpose.
- Uploads UI must show the `interpreted=false` note returned by the API.
- No frontend code has run under npm, tsc, vitest or Playwright in this sandbox. Keep the UNVERIFIED label until it has.
