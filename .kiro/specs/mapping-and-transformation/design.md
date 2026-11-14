# Mapping and Transformation: Design

## Approach
backend/intelligence/mapping_engine, transformation_engine, constraint_engine.

## Components
- Node and edge mapping with confidence per pair
- Unmapped and conflicting elements listed explicitly
- Transformation steps with preconditions and expected effects
- Constraint check on the transformed solution

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Cross-domain discovery

## Edge cases and failure handling
- No valid mapping exists
- Multiple equally good mappings (all returned up to k)
- Type mismatch between mapped nodes
- Conflicting constraints

## Testing strategy
- Injectivity property test
- Unmapped reporting
- Constraint blocking
- Deterministic tie-breaking

## Acceptance criteria traceability
- AC1: Mapping is injective on mapped nodes
- AC2: Every unmapped element appears in the output
- AC3: Each transformation step cites the mapping pairs it relies on
- AC4: Violated hard constraints mark the transformation 'blocked'
- AC5: Confidence is computed, with the formula documented
