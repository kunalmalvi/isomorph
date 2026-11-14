# Coding Conventions
- Python 3.12 target (3.11 compatible), full type hints, dataclasses or pydantic models at boundaries.
- Format with ruff format, lint with ruff, type check with mypy where installed.
- TypeScript strict mode. No any without a comment.
- Names: snake_case Python, camelCase TS variables, PascalCase components and classes.
- Errors: raise typed exceptions in the engine; map them to the error envelope in the API layer.
- No em dashes in docs or comments. No secrets in code. Config via environment.
- Small functions, explicit return types, no global mutable state.
- Randomness only through a seeded random.Random instance passed in.

## Concrete rules from the code (phase 3)
- Every module starts with `from __future__ import annotations`, uses a short docstring and type hints.
- Errors cross the API as `{"error": {"code", "message", "details"}}` built in backend/core/errors.py. Do not hand-build other error shapes.
- Settings come from `load_settings()` reading environment variables; `ISOMORPH_SECRET_KEY` needs at least 32 characters and an explicit value in production.
- Seeded `random.Random` only. Experiments record seed, config hash and code version.
- Unknown input is kept and flagged (for example unclassified relations), not dropped or repaired. User wording is preserved in labels even when normalization maps it to a known role.
- Perception normalization lives in one place (the SYNONYMS table and singular forms in backend/intelligence/perception/service.py). Add synonyms there instead of special cases in callers.
- Do not tune results to look better. The roller demo's best cross-domain score of about 36.5/100 is reported as it is.
- Run `python3 -m compileall -q backend scripts` before committing.
- Scripts under scripts/ write demo output under data/demo; a demo run can change data/demo/sample_investigation.json. Commit that change only when it is intended.
