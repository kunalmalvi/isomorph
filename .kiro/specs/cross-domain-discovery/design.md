# Cross-Domain Discovery: Design

## Approach
backend/intelligence/analogy_engine and domain_engine over backend/knowledge_base.

## Components
- Candidate retrieval by fingerprint similarity
- Scoring with weights 25 functional, 25 relationship, 20 topological, 15 dynamic, 10 constraint, 5 semantic (configurable, must sum to 100)
- Domain distance bonus is reported, never hidden in the score
- Per-component explanations

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Structural DNA engine
- Seed knowledge (spec 8)

## Edge cases and failure handling
- Empty knowledge base
- Ties in score
- Candidate with missing dynamics data (component scored 0 and flagged)
- Very large candidate set (top-k pruning)

## Testing strategy
- Weighted sum correctness
- Weight validation
- Stable ordering on ties
- Roller scenario retrieves a cross-domain candidate

## Acceptance criteria traceability
- AC1: Score equals the weighted sum of components, each in [0,1], total in [0,100]
- AC2: Weights that do not sum to 100 are rejected
- AC3: Same-domain matches are labelled as such
- AC4: Results are sorted by score then by id for stable ordering
- AC5: Matches below threshold are excluded and the threshold is shown
