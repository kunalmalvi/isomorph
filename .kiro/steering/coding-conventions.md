# Coding Conventions
- Python 3.12 target (3.11 compatible), full type hints, dataclasses or pydantic models at boundaries.
- Format with ruff format, lint with ruff, type check with mypy where installed.
- TypeScript strict mode. No any without a comment.
- Names: snake_case Python, camelCase TS variables, PascalCase components and classes.
- Errors: raise typed exceptions in the engine; map them to the error envelope in the API layer.
- No em dashes in docs or comments. No secrets in code. Config via environment.
- Small functions, explicit return types, no global mutable state.
- Randomness only through a seeded random.Random instance passed in.
