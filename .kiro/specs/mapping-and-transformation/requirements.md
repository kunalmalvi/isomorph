# Mapping and Transformation: Requirements

## Overview
Aligns source and target structures element by element and adapts the source solution to the target under constraints.

## Requirements
1. Node and edge mapping with confidence per pair
2. Unmapped and conflicting elements listed explicitly
3. Transformation steps with preconditions and expected effects
4. Constraint check on the transformed solution

## User stories
- As a engineer, I want to see which parts map and which do not, so that I know the limits of the analogy.
- As a engineer, I want to get an ordered list of adaptation steps, so that I can act on them.
- As a reviewer, I want to see constraints violated by a transformation, so that I can reject unsafe ideas.

## Acceptance criteria
1. Mapping is injective on mapped nodes
2. Every unmapped element appears in the output
3. Each transformation step cites the mapping pairs it relies on
4. Violated hard constraints mark the transformation 'blocked'
5. Confidence is computed, with the formula documented

## Dependencies
- Cross-domain discovery

## Edge cases
- No valid mapping exists
- Multiple equally good mappings (all returned up to k)
- Type mismatch between mapped nodes
- Conflicting constraints

## Test cases
- Injectivity property test
- Unmapped reporting
- Constraint blocking
- Deterministic tie-breaking
