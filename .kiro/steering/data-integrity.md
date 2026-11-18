# Data Integrity Rules
- Every knowledge row (domain, system, mechanism) has a source reference and a provenance value.
- Seed data must pass scripts/validate_seed_data.py before commit.
- Foreign keys enforced, ON DELETE behavior explicit.
- Migrations are reversible and reviewed. No manual edits to applied migrations.
- Version history records changes to structural models, hypotheses and mappings.
- Experiment results store seed, configuration hash and code version.
- Never fabricate citations. Unknown source means the row is rejected.

## Concrete rules from the code (phase 3)
- Every source of a system or mechanism is linked, not just the first (tables `domain_system_sources`, `mechanism_sources`, migration 0002). Tested in tests/platform/test_phase3_followups.py.
- Seed tables carry unique constraints. The SQL seed sink must tolerate conflicts so reseeding is idempotent. This is UNVERIFIED until it runs on PostgreSQL.
- Uploads: allowed extensions and a size cap (`MAX_UPLOAD_BYTES`, 5 MiB default) are checked, file names are sanitized, and kinds that are not read (pdf, png, jpeg, json) are flagged `interpreted=false` with a note.
- Template experiments are `illustrative` and cannot produce `supported`; validation caps them at `inconclusive` with a caveat.
- Roller parameters are labelled ParameterRecords with ranges and `verification: unverified_no_network`. Some are still assumptions. Describe them that way, never as verified or as measured.
- Orphaned annotation files must not outlive their project. Cleanup only touches files that match the annotation naming pattern.
- Run `python3 scripts/validate_seed_data.py` and `python3 scripts/evaluate_benchmarks.py` after any seed or perception change.
