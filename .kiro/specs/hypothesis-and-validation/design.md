# Hypothesis and Validation: Design

## Approach
backend/intelligence/hypothesis_engine, validation_engine, backend/experiments.

## Components
- Hypothesis with statement, prediction, falsifier, provenance
- Experiment configuration and seeded runs
- Result records with metrics and seed
- Validation record states: untested, supported, refuted, inconclusive

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- Mapping and transformation

## Edge cases and failure handling
- Non-deterministic provider output
- Experiment timeout
- Conflicting results across runs
- Missing baseline

## Testing strategy
- Seed reproducibility
- Falsifier presence
- Caveat labelling
- Result state transitions

## Acceptance criteria traceability
- AC1: Each hypothesis states a prediction and a falsifier
- AC2: Experiment runs record seed, config hash and code version
- AC3: Same seed and config give identical results
- AC4: Validation never reports 'supported' from simulation alone without a labelled caveat
- AC5: Hypotheses from AI providers are tagged ai_hypothesis
