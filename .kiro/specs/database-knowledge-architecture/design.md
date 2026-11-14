# Database and Knowledge Architecture: Design

## Approach
backend/database (models, migrations), backend/knowledge_base (loaders), data/ (seed JSON).

## Components
- All tables in docs/database-design.md
- Alembic migrations, one forward and one reversible per change
- Embeddings table with vector column and index
- Seed loader with validation script
- Version history and activity logs

## Constraints
- Deterministic by default; no hidden randomness (seeded RNG only).
- Provenance on every claim: source, computation, user, ai_hypothesis.
- Verification status is recorded honestly; code that could not run in the sandbox is labelled UNVERIFIED.

## Dependencies
- None (foundation)

## Edge cases and failure handling
- pgvector extension missing
- Dimension mismatch for embeddings
- Orphaned rows after delete
- Concurrent migration

## Testing strategy
- Seed validation passes on good data and fails on injected bad data
- Migration up/down (needs Postgres, unverified in sandbox)
- Foreign key integrity tests

## Acceptance criteria traceability
- AC1: Every table has id, created_at and, where mutable, updated_at
- AC2: Foreign keys are enforced with explicit ON DELETE behavior
- AC3: Every knowledge row has a source and provenance
- AC4: scripts/validate_seed_data.py exits non-zero on invalid data
- AC5: Migrations are reversible
