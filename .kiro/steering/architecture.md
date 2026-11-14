# Architecture Rules
- Layers: frontend -> api routers -> services -> intelligence engine and repositories -> database.
- Routers contain no business logic. Services orchestrate. The engine is pure Python with no web or database imports.
- Engine modules: perception, structural_model, graph_engine, domain_engine, analogy_engine, mapping_engine, transformation_engine, hypothesis_engine, constraint_engine, validation_engine, learning_engine. Each has schemas and a service entry point.
- Engine and experiments use the standard library only so they run anywhere. Optional adapters (NetworkX, NumPy) must be isolated and never required.
- AI providers sit behind backend/ai_providers. The local deterministic provider is the default.
- Dependencies point inward: engine must not import from api or database.

## Concrete layout (phase 3)
- Engine: backend/intelligence/{perception, structural_model, graph_engine, fingerprint, domain_engine, analogy_engine, mapping_engine, transformation_engine, hypothesis_engine, constraint_engine, validation_engine, learning_engine, schemas} plus pipeline.py. Experiments live in backend/experiments (linear_solver, runners, common).
- Platform: backend/api (routers, deps, schemas, db_store), backend/core (config, errors, rate_limit, security, sse, uploads), backend/database (models, session, seed), backend/ai_providers.
- backend/core modules are stdlib only so they can be tested without FastAPI. Keep new shared logic there when it needs no web framework.
- The pipeline runs stages in order and keeps each stage output. Editing a stage marks downstream stages stale; rerun recomputes them. Run state is stored through a store interface with an in-memory, JSON file and SQL implementation. Only the first two have executed tests.
- Runs execute in an in process thread pool. On startup, runs left `queued` or `running` are marked failed with `interrupted by restart`. This assumes a single API process.
- Hypothesis decisions and notes are stored as annotations in a separate store and never change engine output. Annotation files for deleted projects are purged on delete and at startup (wiring UNVERIFIED).
- SSE streams are bounded by `SSE_MAX_SECONDS` (default 15, range 1 to 600). Each stream holds one worker thread, so size `worker_threads` and the server threadpool for the expected number of open streams. Clients reconnect with `Last-Event-ID`.
- The rate limiter is in memory and per process. `X-Forwarded-For` is trusted only from peers listed in `TRUSTED_PROXIES`.
