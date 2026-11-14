# Architecture Rules
- Layers: frontend -> api routers -> services -> intelligence engine and repositories -> database.
- Routers contain no business logic. Services orchestrate. The engine is pure Python with no web or database imports.
- Engine modules: perception, structural_model, graph_engine, domain_engine, analogy_engine, mapping_engine, transformation_engine, hypothesis_engine, constraint_engine, validation_engine, learning_engine. Each has schemas and a service entry point.
- Engine and experiments use the standard library only so they run anywhere. Optional adapters (NetworkX, NumPy) must be isolated and never required.
- AI providers sit behind backend/ai_providers. The local deterministic provider is the default.
- Dependencies point inward: engine must not import from api or database.
