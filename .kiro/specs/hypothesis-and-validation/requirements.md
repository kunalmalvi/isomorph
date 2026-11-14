# Hypothesis and Validation: Requirements

## Overview
Generates falsifiable hypotheses from transformations and validates them with deterministic simulation and evidence checks.

## Requirements
1. Hypothesis with statement, prediction, falsifier, provenance
2. Experiment configuration and seeded runs
3. Result records with metrics and seed
4. Validation record states: untested, supported, refuted, inconclusive

## User stories
- As a researcher, I want to get a falsifiable hypothesis, so that I can test it.
- As a researcher, I want to re-run an experiment with the same seed, so that I get identical results.
- As a reviewer, I want to see that simulations are models, not real-world proof, so that claims stay honest.

## Acceptance criteria
1. Each hypothesis states a prediction and a falsifier
2. Experiment runs record seed, config hash and code version
3. Same seed and config give identical results
4. Validation never reports 'supported' from simulation alone without a labelled caveat
5. Hypotheses from AI providers are tagged ai_hypothesis

## Dependencies
- Mapping and transformation

## Edge cases
- Non-deterministic provider output
- Experiment timeout
- Conflicting results across runs
- Missing baseline

## Test cases
- Seed reproducibility
- Falsifier presence
- Caveat labelling
- Result state transitions
