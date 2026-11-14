# Architecture

```
Next.js frontend
      |  HTTPS JSON
FastAPI routers (/api/v1)   no business logic
      |
Services                    orchestration, authorization, transactions
   |            |
Intelligence engine   Repositories (SQLAlchemy)
(pure Python)               |
      |               PostgreSQL + pgvector
Knowledge base loaders, experiments, AI providers (local deterministic default)
```

## Engine pipeline
perception -> structural_model -> graph_engine (metrics) -> fingerprint -> domain_engine and analogy_engine (retrieve and score) -> mapping_engine -> transformation_engine with constraint_engine -> hypothesis_engine -> validation_engine -> learning_engine (records strategy performance and feedback).

## Boundaries
- The engine imports nothing from api, database or web libraries.
- Experiments use a seeded `random.Random` and record seed, config hash and code version.
- AI providers implement one interface; the local provider is deterministic and needs no network.

## Directories
`frontend/`, `backend/{api,core,intelligence,ai_providers,database,experiments,knowledge_base,services,workers,tests}`, `data/`, `docs/`, `scripts/`, `.kiro/`.

## Provenance model
Each claim carries one of source, computation, user, ai_hypothesis. AI output never occupies source or computation.

## Verification status
Engine, experiments and knowledge base are stdlib and testable in the sandbox. API, database and frontend code is written to spec and only syntax-checked there (UNVERIFIED at runtime).
