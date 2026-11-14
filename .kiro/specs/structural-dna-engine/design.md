# Structural DNA Engine: Design

## Approach
backend/intelligence/perception, structural_model, graph_engine. Pure stdlib graph implementation; optional NetworkX adapter later.

## Components
- Perception: extract entities, relations, constraints, variables from text and structured input
- Structural model: typed directed graph with roles and dynamics
- Fingerprint: functional, relational, topological, dynamic, constraint and semantic feature vectors
- Deterministic: same input gives same fingerprint

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- None (foundation)

## Edge cases and failure handling
- Disconnected graphs
- Self loops and parallel edges
- Cycles
- Empty input
- Non-English text: reported as low confidence

## Testing strategy
- Fingerprint determinism
- Graph metric correctness on known graphs
- Extraction of roller scenario entities
- Unclassified relation handling

## Acceptance criteria traceability
- AC1: Fingerprint is identical across runs for identical input
- AC2: Each node and edge records provenance and source span when from text
- AC3: Unknown relation types are kept as 'unclassified' and flagged, not dropped
- AC4: Graph with a single node yields a valid fingerprint with topology features zeroed
- AC5: Fingerprint schema is versioned
