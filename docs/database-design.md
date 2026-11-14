# Database Design

PostgreSQL 16 with the pgvector extension. Status: DESIGN. No Postgres is available in the authoring sandbox, so nothing here has been run against a database (UNVERIFIED).

## Conventions
- Primary keys are uuid. Timestamps are timestamptz in UTC.
- `provenance` is an enum: source, computation, user, ai_hypothesis.
- Foreign keys use ON DELETE CASCADE for owned children (for example problem to entities) and RESTRICT for shared references (for example sources).
- Migrations are managed with Alembic and must be reversible.
- Every row in domains, domain_systems and mechanisms must reference a source.

## Tables (35)
### `users`
Columns: id uuid pk, email text unique not null, display_name text, password_hash text not null, is_active bool, created_at timestamptz, updated_at timestamptz.

### `organizations`
Columns: id uuid pk, name text not null, slug text unique, created_at timestamptz, updated_at timestamptz.

### `projects`
Columns: id uuid pk, organization_id fk organizations, name text, description text, created_by fk users, archived_at timestamptz, created_at timestamptz, updated_at timestamptz.

### `project_members`
Columns: id uuid pk, project_id fk, user_id fk, role enum(owner,editor,viewer), unique(project_id,user_id), created_at timestamptz, updated_at timestamptz.

### `problems`
Columns: id uuid pk, project_id fk, title text, statement text, goal text, status enum(draft,modeled,archived), created_at timestamptz, updated_at timestamptz.

### `problem_entities`
Columns: id uuid pk, problem_id fk, name, kind, description, provenance enum, source_span jsonb, created_at timestamptz, updated_at timestamptz.

### `problem_relationships`
Columns: id uuid pk, problem_id fk, source_entity_id fk, target_entity_id fk, relation_type, weight float, provenance, created_at timestamptz, updated_at timestamptz.

### `constraints`
Columns: id uuid pk, problem_id fk, description, kind enum(hard,soft), expression jsonb, provenance, created_at timestamptz, updated_at timestamptz.

### `variables`
Columns: id uuid pk, problem_id fk, name, unit, min_value, max_value, role enum(input,output,state,parameter), created_at timestamptz, updated_at timestamptz.

### `assumptions`
Columns: id uuid pk, problem_id fk, statement, confidence float, provenance, created_at timestamptz, updated_at timestamptz.

### `evidence`
Columns: id uuid pk, problem_id fk, statement, source_id fk sources null, strength float, provenance, created_at timestamptz, updated_at timestamptz.

### `domains`
Columns: id uuid pk, name unique, description, parent_domain_id fk domains null, created_at timestamptz, updated_at timestamptz.

### `domain_systems`
Columns: id uuid pk, domain_id fk, name, description, source_id fk sources, provenance, created_at timestamptz, updated_at timestamptz.

### `mechanisms`
Columns: id uuid pk, domain_system_id fk, name, description, function_tag, source_id fk sources, provenance, created_at timestamptz, updated_at timestamptz.

### `system_entities`
Columns: id uuid pk, domain_system_id fk, name, kind, role, created_at timestamptz, updated_at timestamptz.

### `system_relationships`
Columns: id uuid pk, domain_system_id fk, source_entity_id fk, target_entity_id fk, relation_type, weight, created_at timestamptz, updated_at timestamptz.

### `sources`
Columns: id uuid pk, title, citation, url null, source_type enum(paper,book,standard,dataset,internal), retrieved_at, created_at timestamptz, updated_at timestamptz.

### `embeddings`
Columns: id uuid pk, owner_type text, owner_id uuid, model text, dimension int, vector vector(384), index hnsw cosine, created_at timestamptz, updated_at timestamptz.

### `discovery_sessions`
Columns: id uuid pk, problem_id fk, status enum(queued,running,done,failed), weights jsonb, threshold float, started_at, finished_at, error text, created_at timestamptz, updated_at timestamptz.

### `structural_models`
Columns: id uuid pk, problem_id fk, discovery_session_id fk null, graph jsonb, version int, provenance, created_at timestamptz, updated_at timestamptz.

### `structural_fingerprints`
Columns: id uuid pk, structural_model_id fk, schema_version int, functional jsonb, relational jsonb, topological jsonb, dynamic jsonb, constraint jsonb, semantic jsonb, hash text, created_at timestamptz, updated_at timestamptz.

### `candidate_matches`
Columns: id uuid pk, discovery_session_id fk, domain_system_id fk, score float, breakdown jsonb, domain_distance float, rank int, created_at timestamptz, updated_at timestamptz.

### `structural_mappings`
Columns: id uuid pk, candidate_match_id fk, node_pairs jsonb, edge_pairs jsonb, unmapped_source jsonb, unmapped_target jsonb, confidence float, created_at timestamptz, updated_at timestamptz.

### `transformations`
Columns: id uuid pk, structural_mapping_id fk, steps jsonb, constraint_report jsonb, status enum(ok,blocked), confidence float, created_at timestamptz, updated_at timestamptz.

### `hypotheses`
Columns: id uuid pk, transformation_id fk, statement, prediction, falsifier, provenance, status enum(untested,supported,refuted,inconclusive), created_at timestamptz, updated_at timestamptz.

### `experiments`
Columns: id uuid pk, hypothesis_id fk, name, description, created_at timestamptz, updated_at timestamptz.

### `experiment_configurations`
Columns: id uuid pk, experiment_id fk, parameters jsonb, config_hash text, seed int, created_at timestamptz, updated_at timestamptz.

### `experiment_runs`
Columns: id uuid pk, experiment_configuration_id fk, status, code_version, started_at, finished_at, created_at timestamptz, updated_at timestamptz.

### `experiment_results`
Columns: id uuid pk, experiment_run_id fk, metrics jsonb, notes text, created_at timestamptz, updated_at timestamptz.

### `validation_records`
Columns: id uuid pk, hypothesis_id fk, outcome enum, caveats text, validated_by fk users null, method, created_at timestamptz, updated_at timestamptz.

### `discovery_memory`
Columns: id uuid pk, user_id fk null, project_id fk null, key text, value jsonb, weight float, created_at timestamptz, updated_at timestamptz.

### `strategy_performance`
Columns: id uuid pk, strategy_name, context jsonb, trials int, successes int, updated_at, created_at timestamptz, updated_at timestamptz.

### `user_feedback`
Columns: id uuid pk, user_id fk, target_type, target_id, rating int, comment text, created_at timestamptz, updated_at timestamptz.

### `activity_logs`
Columns: id uuid pk, user_id fk null, project_id fk null, action, target_type, target_id, metadata jsonb, created_at timestamptz, updated_at timestamptz.

### `version_history`
Columns: id uuid pk, entity_type, entity_id, version int, diff jsonb, changed_by fk users null, created_at timestamptz, updated_at timestamptz.

## Additions made during implementation
The implemented schema (backend/database/models.py, backend/migrations/versions/0001_initial.py) adds the following to the 35 tables above.
- New tables: `pipeline_stages` (persisted, inspectable output of each orchestrator stage per discovery session), `reports` (generated report documents), `user_settings` (per user weights and preferences).
- `discovery_sessions`: added `project_id`, `created_by`, `input jsonb`, `config jsonb`; status also allows `cancelled`.
- `problems`: added `created_by`. `variables`: added `value`.
- Denormalised ownership: `project_id` (fk projects, indexed) on `structural_models`, `candidate_matches`, `structural_mappings`, `transformations`, `hypotheses`, `experiments`, `validation_records`. It is copied from the parent on insert so every authorization check is a single lookup.
- `candidate_matches`: added `system_key` (seed knowledge system id). `domain_system_id` is nullable because seed knowledge is served from `data/` in local mode.
- `transformations`: added `concept jsonb`. `hypotheses`: added `experiment jsonb`.
- Soft delete: `deleted_at timestamptz` (indexed) on projects, problems, discovery_sessions, structural_models, hypotheses, experiments and reports. Soft deleted rows are hidden by the API.
- Enums are stored as VARCHAR with a CHECK constraint (not native PostgreSQL enums) so migrations are reversible and SQLite works for tests.
- `embeddings.vector` is `vector(384)` with an HNSW cosine index when the pgvector extension and Python package are available. Otherwise it is a JSON float array without an ANN index (set `USE_PGVECTOR=false`).

## Indexes
- Foreign key columns are indexed.
- `embeddings`: HNSW index on vector with cosine ops; btree on (owner_type, owner_id).
- `candidate_matches`: (discovery_session_id, rank).
- `activity_logs`: (project_id, created_at desc).
- `version_history`: unique (entity_type, entity_id, version).

## Embeddings note
The deterministic local mode does not require embeddings. The semantic component (weight 5) uses a lexical fallback until an embedding provider is configured.
