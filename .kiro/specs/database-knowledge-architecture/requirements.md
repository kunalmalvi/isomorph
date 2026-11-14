# Database and Knowledge Architecture: Requirements

## Overview
PostgreSQL with pgvector for relational data and embeddings; seed knowledge base of domains, systems and mechanisms.

## Requirements
1. All tables in docs/database-design.md
2. Alembic migrations, one forward and one reversible per change
3. Embeddings table with vector column and index
4. Seed loader with validation script
5. Version history and activity logs

## User stories
- As a developer, I want to apply migrations from empty, so that I get a working schema.
- As a data steward, I want to validate seed data, so that bad knowledge cannot enter.
- As a auditor, I want to see version history, so that changes are traceable.

## Acceptance criteria
1. Every table has id, created_at and, where mutable, updated_at
2. Foreign keys are enforced with explicit ON DELETE behavior
3. Every knowledge row has a source and provenance
4. scripts/validate_seed_data.py exits non-zero on invalid data
5. Migrations are reversible

## Dependencies
- None (foundation)

## Edge cases
- pgvector extension missing
- Dimension mismatch for embeddings
- Orphaned rows after delete
- Concurrent migration

## Test cases
- Seed validation passes on good data and fails on injected bad data
- Migration up/down (needs Postgres, unverified in sandbox)
- Foreign key integrity tests
