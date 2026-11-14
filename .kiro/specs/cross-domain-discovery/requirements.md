# Cross-Domain Discovery: Requirements

## Overview
Searches the knowledge base of domains, systems and mechanisms for structurally similar candidates and ranks them.

## Requirements
1. Candidate retrieval by fingerprint similarity
2. Scoring with weights 25 functional, 25 relationship, 20 topological, 15 dynamic, 10 constraint, 5 semantic (configurable, must sum to 100)
3. Domain distance bonus is reported, never hidden in the score
4. Per-component explanations

## User stories
- As a researcher, I want to see top-N matches from distant domains, so that I get non-obvious ideas.
- As a researcher, I want to adjust weights, so that I can explore sensitivity.
- As a reviewer, I want to see the component breakdown, so that I can audit a score.

## Acceptance criteria
1. Score equals the weighted sum of components, each in [0,1], total in [0,100]
2. Weights that do not sum to 100 are rejected
3. Same-domain matches are labelled as such
4. Results are sorted by score then by id for stable ordering
5. Matches below threshold are excluded and the threshold is shown

## Dependencies
- Structural DNA engine
- Seed knowledge (spec 8)

## Edge cases
- Empty knowledge base
- Ties in score
- Candidate with missing dynamics data (component scored 0 and flagged)
- Very large candidate set (top-k pruning)

## Test cases
- Weighted sum correctness
- Weight validation
- Stable ordering on ties
- Roller scenario retrieves a cross-domain candidate
