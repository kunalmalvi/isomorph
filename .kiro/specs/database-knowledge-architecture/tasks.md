# Database and Knowledge Architecture: Tasks

- [ ] T1. Implement: All tables in docs/database-design.md
- [ ] T2. Implement: Alembic migrations, one forward and one reversible per change
- [ ] T3. Implement: Embeddings table with vector column and index
- [ ] T4. Implement: Seed loader with validation script
- [ ] T5. Implement: Version history and activity logs
- [ ] T6. Test: Seed validation passes on good data and fails on injected bad data
- [ ] T7. Test: Migration up/down (needs Postgres, unverified in sandbox)
- [ ] T8. Test: Foreign key integrity tests
- [ ] T9. Handle edge cases listed in design.md
- [ ] T10. Update docs and record verification status

## Status (phase 2)
- T1, T2, T3, T5 written as models and migration 0001. T4: scripts/validate_seed_data.py runs, and the phase 2 seeding function loads data/ JSON idempotently (not run automatically).
- UNVERIFIED: T7 and T8 need PostgreSQL. The migration is checked against docs/database-design.md by test_migration_schema.py (executed); the ORM comparison test is skipped without SQLAlchemy.
- Checkboxes above are the original plan. Treat this section as the current state.

## Status (phase 3)
- Phase 3: migration 0002 added. It and the model changes are UNVERIFIED.
- Requirement to test mapping is in requirements.md.
