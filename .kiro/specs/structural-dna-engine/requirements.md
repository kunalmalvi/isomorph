# Structural DNA Engine: Requirements

## Overview
Converts a problem or a known system into a structural model (typed graph) and a structural fingerprint used for matching.

## Requirements
1. Perception: extract entities, relations, constraints, variables from text and structured input
2. Structural model: typed directed graph with roles and dynamics
3. Fingerprint: functional, relational, topological, dynamic, constraint and semantic feature vectors
4. Deterministic: same input gives same fingerprint

## User stories
- As a researcher, I want to get a structural model from my description, so that I see the abstract skeleton of my problem.
- As a engine, I want to compute a stable fingerprint, so that matching is reproducible.
- As a reviewer, I want to see which text spans produced each element, so that I can verify extraction.

## Acceptance criteria
1. Fingerprint is identical across runs for identical input
2. Each node and edge records provenance and source span when from text
3. Unknown relation types are kept as 'unclassified' and flagged, not dropped
4. Graph with a single node yields a valid fingerprint with topology features zeroed
5. Fingerprint schema is versioned

## Dependencies
- None (foundation)

## Edge cases
- Disconnected graphs
- Self loops and parallel edges
- Cycles
- Empty input
- Non-English text: reported as low confidence

## Test cases
- Fingerprint determinism
- Graph metric correctness on known graphs
- Extraction of roller scenario entities
- Unclassified relation handling
