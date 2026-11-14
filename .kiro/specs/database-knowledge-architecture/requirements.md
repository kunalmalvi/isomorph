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

## Traceability to tests (phase 3)
Paths are relative to backend/tests unless stated. "Skipped without FastAPI" means the test exists but did not run in this sandbox.

| Item | Test or check |
|---|---|
| AC1 id and timestamps | platform/test_migration_schema.py::test_every_documented_table_and_column_is_in_the_migration |
| AC2 foreign keys | test_migration_schema.py::test_extra_tables_are_documented_and_foreign_keys_resolve_in_order |
| Enums | test_migration_schema.py::test_enums_cover_documented_values |
| Project isolation column | test_migration_schema.py::test_every_table_with_project_data_has_isolation_column |
| ORM matches migration | test_migration_schema.py::test_models_match_migration_when_sqlalchemy_available (skipped without SQLAlchemy) |
| AC3 source on every knowledge row | intelligence/test_seed_data.py::test_seed_data_is_valid_and_broad; test_schemas_graph.py::test_system_validation_requires_sources_and_roles |
| AC4 validator exit code | python3 scripts/validate_seed_data.py (exit 0 on current data) |
| Seeding idempotent | platform/test_phase2_platform.py::test_seed_is_idempotent, test_seed_plan_covers_data_and_is_deterministic, test_seed_relationships_reference_existing_entities, test_seed_dry_run_cli (fake store) |
| AC5 reversible migrations | Written, never run against PostgreSQL. UNVERIFIED |

## Edge case status (phase 3)
- Orphaned rows after delete: Annotation files are purged on project delete and cleaned at startup (test_phase3_followups.py::test_purge_and_orphan_cleanup, test_cleanup_removes_files_and_ignores_foreign_files). The router wiring is UNVERIFIED.
- Duplicate seed rows: Phase 3 added unique constraints and migration 0002 (link tables domain_system_sources and mechanism_sources). The SQL sink tolerates conflicts via savepoints. UNVERIFIED, no SQLAlchemy or PostgreSQL.
- pgvector missing, dimension mismatch, concurrent migration: Not tested. USE_PGVECTOR=false is the documented fallback.
