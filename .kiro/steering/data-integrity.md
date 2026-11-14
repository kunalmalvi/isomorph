# Data Integrity Rules
- Every knowledge row (domain, system, mechanism) has a source reference and a provenance value.
- Seed data must pass scripts/validate_seed_data.py before commit.
- Foreign keys enforced, ON DELETE behavior explicit.
- Migrations are reversible and reviewed. No manual edits to applied migrations.
- Version history records changes to structural models, hypotheses and mappings.
- Experiment results store seed, configuration hash and code version.
- Never fabricate citations. Unknown source means the row is rejected.
