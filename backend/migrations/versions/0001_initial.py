"""Initial schema: all tables from docs/database-design.md plus pipeline_stages, reports and user_settings.

UNVERIFIED in the authoring sandbox (Alembic, SQLAlchemy and PostgreSQL are not installable there).

Table definitions are a frozen data list (TABLES) so the migration never imports application code. Each entry is
(table name, soft_delete, columns, unique constraints, extra indexes). Every table also gets id uuid pk,
created_at and updated_at (and deleted_at when soft_delete). A column is (name, type, flags, fk) where fk is
(referenced table, ON DELETE action).

pgvector: on PostgreSQL the migration tries CREATE EXTENSION vector. If the extension is unavailable or
USE_PGVECTOR=false, embeddings.vector is created as JSON (a float array) with no ANN index. The application reads
the same USE_PGVECTOR variable, so set it to false in such environments.
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384

ENUMS = {'constraint_kind': ('hard', 'soft'),
 'hypothesis_status': ('untested', 'supported', 'refuted', 'inconclusive'),
 'member_role': ('owner', 'editor', 'viewer'),
 'problem_status': ('draft', 'modeled', 'archived'),
 'provenance': ('source', 'computation', 'user', 'ai_hypothesis'),
 'session_status': ('queued', 'running', 'done', 'failed', 'cancelled'),
 'source_type': ('paper', 'book', 'standard', 'dataset', 'internal'),
 'transformation_status': ('ok', 'blocked'),
 'variable_role': ('input', 'output', 'state', 'parameter')}

TABLES = [
    ('users', False, [
        ('email', 'text', ('nn', 'uq'), None),
        ('display_name', 'text', (), None),
        ('password_hash', 'text', ('nn',), None),
        ('is_active', 'bool', ('nn',), None),
    ], [], []),
    ('organizations', False, [
        ('name', 'text', ('nn',), None),
        ('slug', 'text', ('uq',), None),
    ], [], []),
    ('projects', True, [
        ('organization_id', 'uuid', ('ix',), ('organizations', 'SET NULL')),
        ('name', 'text', ('nn',), None),
        ('description', 'text', (), None),
        ('created_by', 'uuid', ('nn', 'ix'), ('users', 'RESTRICT')),
        ('archived_at', 'ts', (), None),
    ], [], []),
    ('project_members', False, [
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('user_id', 'uuid', ('nn', 'ix'), ('users', 'CASCADE')),
        ('role', 'enum:member_role', ('nn',), None),
    ], [['project_id', 'user_id']], []),
    ('problems', True, [
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('title', 'text', ('nn',), None),
        ('statement', 'text', ('nn',), None),
        ('goal', 'text', (), None),
        ('status', 'enum:problem_status', ('nn',), None),
        ('created_by', 'uuid', ('ix',), ('users', 'SET NULL')),
    ], [], []),
    ('problem_entities', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('kind', 'text', (), None),
        ('description', 'text', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
        ('source_span', 'json', (), None),
    ], [], []),
    ('problem_relationships', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('source_entity_id', 'uuid', ('nn', 'ix'), ('problem_entities', 'CASCADE')),
        ('target_entity_id', 'uuid', ('nn', 'ix'), ('problem_entities', 'CASCADE')),
        ('relation_type', 'text', ('nn',), None),
        ('weight', 'float', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('constraints', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('description', 'text', ('nn',), None),
        ('kind', 'enum:constraint_kind', ('nn',), None),
        ('expression', 'json', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('variables', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('unit', 'text', (), None),
        ('min_value', 'float', (), None),
        ('max_value', 'float', (), None),
        ('value', 'float', (), None),
        ('role', 'enum:variable_role', ('nn',), None),
    ], [], []),
    ('assumptions', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('statement', 'text', ('nn',), None),
        ('confidence', 'float', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('sources', False, [
        ('title', 'text', ('nn',), None),
        ('citation', 'text', ('nn',), None),
        ('url', 'text', (), None),
        ('source_type', 'enum:source_type', ('nn',), None),
        ('retrieved_at', 'ts', (), None),
    ], [], []),
    ('evidence', False, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('statement', 'text', ('nn',), None),
        ('source_id', 'uuid', ('ix',), ('sources', 'RESTRICT')),
        ('strength', 'float', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('domains', False, [
        ('name', 'text', ('nn', 'uq'), None),
        ('description', 'text', (), None),
        ('parent_domain_id', 'uuid', ('ix',), ('domains', 'SET NULL')),
    ], [], []),
    ('domain_systems', False, [
        ('domain_id', 'uuid', ('nn', 'ix'), ('domains', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('description', 'text', (), None),
        ('source_id', 'uuid', ('nn', 'ix'), ('sources', 'RESTRICT')),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('mechanisms', False, [
        ('domain_system_id', 'uuid', ('nn', 'ix'), ('domain_systems', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('description', 'text', (), None),
        ('function_tag', 'text', (), None),
        ('source_id', 'uuid', ('nn', 'ix'), ('sources', 'RESTRICT')),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('system_entities', False, [
        ('domain_system_id', 'uuid', ('nn', 'ix'), ('domain_systems', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('kind', 'text', (), None),
        ('role', 'text', (), None),
    ], [], []),
    ('system_relationships', False, [
        ('domain_system_id', 'uuid', ('nn', 'ix'), ('domain_systems', 'CASCADE')),
        ('source_entity_id', 'uuid', ('nn', 'ix'), ('system_entities', 'CASCADE')),
        ('target_entity_id', 'uuid', ('nn', 'ix'), ('system_entities', 'CASCADE')),
        ('relation_type', 'text', ('nn',), None),
        ('weight', 'float', (), None),
    ], [], []),
    ('embeddings', False, [
        ('owner_type', 'text', ('nn',), None),
        ('owner_id', 'uuid', ('nn',), None),
        ('model', 'text', ('nn',), None),
        ('dimension', 'int', ('nn',), None),
        ('vector', 'vector', ('nn',), None),
    ], [], [['owner_type', 'owner_id']]),
    ('discovery_sessions', True, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('created_by', 'uuid', ('ix',), ('users', 'SET NULL')),
        ('status', 'enum:session_status', ('nn',), None),
        ('input', 'json', (), None),
        ('config', 'json', (), None),
        ('weights', 'json', (), None),
        ('threshold', 'float', (), None),
        ('started_at', 'ts', (), None),
        ('finished_at', 'ts', (), None),
        ('error', 'text', (), None),
    ], [], []),
    ('pipeline_stages', False, [
        ('discovery_session_id', 'uuid', ('nn', 'ix'), ('discovery_sessions', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('ordinal', 'int', ('nn',), None),
        ('status', 'text', ('nn',), None),
        ('source', 'text', ('nn',), None),
        ('version', 'int', ('nn',), None),
        ('output', 'json', (), None),
        ('error', 'text', (), None),
        ('started_at', 'ts', (), None),
        ('finished_at', 'ts', (), None),
    ], [['discovery_session_id', 'name']], []),
    ('structural_models', True, [
        ('problem_id', 'uuid', ('nn', 'ix'), ('problems', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('discovery_session_id', 'uuid', ('ix',), ('discovery_sessions', 'SET NULL')),
        ('graph', 'json', ('nn',), None),
        ('version', 'int', ('nn',), None),
        ('provenance', 'enum:provenance', ('nn',), None),
    ], [], []),
    ('structural_fingerprints', False, [
        ('structural_model_id', 'uuid', ('nn', 'ix'), ('structural_models', 'CASCADE')),
        ('schema_version', 'int', ('nn',), None),
        ('functional', 'json', (), None),
        ('relational', 'json', (), None),
        ('topological', 'json', (), None),
        ('dynamic', 'json', (), None),
        ('constraint', 'json', (), None),
        ('semantic', 'json', (), None),
        ('hash', 'text', ('nn',), None),
    ], [], []),
    ('candidate_matches', False, [
        ('discovery_session_id', 'uuid', ('nn', 'ix'), ('discovery_sessions', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('domain_system_id', 'uuid', ('ix',), ('domain_systems', 'SET NULL')),
        ('system_key', 'text', ('nn',), None),
        ('score', 'float', ('nn',), None),
        ('breakdown', 'json', ('nn',), None),
        ('domain_distance', 'float', (), None),
        ('rank', 'int', ('nn',), None),
    ], [], [['discovery_session_id', 'rank']]),
    ('structural_mappings', False, [
        ('candidate_match_id', 'uuid', ('nn', 'ix'), ('candidate_matches', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('node_pairs', 'json', ('nn',), None),
        ('edge_pairs', 'json', ('nn',), None),
        ('unmapped_source', 'json', (), None),
        ('unmapped_target', 'json', (), None),
        ('confidence', 'float', (), None),
    ], [], []),
    ('transformations', False, [
        ('structural_mapping_id', 'uuid', ('nn', 'ix'), ('structural_mappings', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('concept', 'json', (), None),
        ('steps', 'json', ('nn',), None),
        ('constraint_report', 'json', (), None),
        ('status', 'enum:transformation_status', ('nn',), None),
        ('confidence', 'float', (), None),
    ], [], []),
    ('hypotheses', True, [
        ('transformation_id', 'uuid', ('nn', 'ix'), ('transformations', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('statement', 'text', ('nn',), None),
        ('prediction', 'text', (), None),
        ('falsifier', 'text', (), None),
        ('experiment', 'json', (), None),
        ('provenance', 'enum:provenance', ('nn',), None),
        ('status', 'enum:hypothesis_status', ('nn',), None),
    ], [], []),
    ('experiments', True, [
        ('hypothesis_id', 'uuid', ('nn', 'ix'), ('hypotheses', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('name', 'text', ('nn',), None),
        ('description', 'text', (), None),
    ], [], []),
    ('experiment_configurations', False, [
        ('experiment_id', 'uuid', ('nn', 'ix'), ('experiments', 'CASCADE')),
        ('parameters', 'json', ('nn',), None),
        ('config_hash', 'text', ('nn',), None),
        ('seed', 'int', (), None),
    ], [], []),
    ('experiment_runs', False, [
        ('experiment_configuration_id', 'uuid', ('nn', 'ix'), ('experiment_configurations', 'CASCADE')),
        ('status', 'text', ('nn',), None),
        ('code_version', 'text', (), None),
        ('started_at', 'ts', (), None),
        ('finished_at', 'ts', (), None),
    ], [], []),
    ('experiment_results', False, [
        ('experiment_run_id', 'uuid', ('nn', 'ix'), ('experiment_runs', 'CASCADE')),
        ('metrics', 'json', ('nn',), None),
        ('notes', 'text', (), None),
    ], [], []),
    ('validation_records', False, [
        ('hypothesis_id', 'uuid', ('nn', 'ix'), ('hypotheses', 'CASCADE')),
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('outcome', 'enum:hypothesis_status', ('nn',), None),
        ('caveats', 'text', (), None),
        ('validated_by', 'uuid', ('ix',), ('users', 'SET NULL')),
        ('method', 'text', (), None),
    ], [], []),
    ('discovery_memory', False, [
        ('user_id', 'uuid', ('ix',), ('users', 'CASCADE')),
        ('project_id', 'uuid', ('ix',), ('projects', 'CASCADE')),
        ('key', 'text', ('nn',), None),
        ('value', 'json', (), None),
        ('weight', 'float', (), None),
    ], [], []),
    ('strategy_performance', False, [
        ('strategy_name', 'text', ('nn',), None),
        ('context', 'json', (), None),
        ('trials', 'int', ('nn',), None),
        ('successes', 'int', ('nn',), None),
    ], [], []),
    ('user_feedback', False, [
        ('user_id', 'uuid', ('nn', 'ix'), ('users', 'CASCADE')),
        ('target_type', 'text', ('nn',), None),
        ('target_id', 'uuid', ('nn',), None),
        ('rating', 'int', (), None),
        ('comment', 'text', (), None),
    ], [], []),
    ('activity_logs', False, [
        ('user_id', 'uuid', ('ix',), ('users', 'SET NULL')),
        ('project_id', 'uuid', ('ix',), ('projects', 'CASCADE')),
        ('action', 'text', ('nn',), None),
        ('target_type', 'text', (), None),
        ('target_id', 'uuid', (), None),
        ('metadata', 'json', (), None),
    ], [], [['project_id', 'created_at']]),
    ('version_history', False, [
        ('entity_type', 'text', ('nn',), None),
        ('entity_id', 'uuid', ('nn',), None),
        ('version', 'int', ('nn',), None),
        ('diff', 'json', (), None),
        ('changed_by', 'uuid', ('ix',), ('users', 'SET NULL')),
    ], [['entity_type', 'entity_id', 'version']], []),
    ('reports', True, [
        ('project_id', 'uuid', ('nn', 'ix'), ('projects', 'CASCADE')),
        ('discovery_session_id', 'uuid', ('ix',), ('discovery_sessions', 'SET NULL')),
        ('title', 'text', ('nn',), None),
        ('content', 'json', ('nn',), None),
        ('created_by', 'uuid', ('ix',), ('users', 'SET NULL')),
    ], [], []),
    ('user_settings', False, [
        ('user_id', 'uuid', ('nn', 'uq'), ('users', 'CASCADE')),
        ('weights', 'json', (), None),
        ('preferences', 'json', (), None),
    ], [], []),
]


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _pgvector_available(bind) -> bool:
    if bind.dialect.name != "postgresql" or os.environ.get("USE_PGVECTOR", "true").lower() in ("0", "false", "no"):
        return False
    try:
        import pgvector  # noqa: F401
    except ImportError:
        return False
    row = bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).first()
    if row is None:
        return False
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    return True


def _column(name, typ, flags, fk, vector_type):
    if typ.startswith("enum:"):
        e = typ[5:]
        t = sa.Enum(*ENUMS[e], name=e, native_enum=False, create_constraint=True, length=32)
    else:
        t = {"uuid": sa.Uuid(), "text": sa.Text(), "int": sa.Integer(), "float": sa.Float(), "bool": sa.Boolean(),
             "ts": sa.DateTime(timezone=True), "json": _json(), "vector": vector_type}[typ]
    args = [name, t]
    if fk:
        args.append(sa.ForeignKey(fk[0] + ".id", ondelete=fk[1]))
    return sa.Column(*args, nullable="nn" not in flags, unique=True if "uq" in flags else None,
                     index=True if "ix" in flags else None)


def upgrade() -> None:
    bind = op.get_bind()
    use_vector = _pgvector_available(bind)
    vector_type = _json()
    if use_vector:
        from pgvector.sqlalchemy import Vector
        vector_type = Vector(EMBEDDING_DIM)
    for name, soft, cols, uniques, indexes in TABLES:
        columns = [sa.Column("id", sa.Uuid(), primary_key=True)]
        columns += [_column(*c, vector_type) for c in cols]
        columns += [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]
        if soft:
            columns.append(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True))
        cons = [sa.UniqueConstraint(*u, name=f"uq_{name}_{'_'.join(u)}") for u in uniques]
        op.create_table(name, *columns, *cons)
        for ix in indexes:
            op.create_index(f"ix_{name}_{'_'.join(ix)}", name, ix)
    if use_vector:
        op.execute("CREATE INDEX ix_embeddings_vector_hnsw ON embeddings USING hnsw (vector vector_cosine_ops)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_embeddings_vector_hnsw")
    for name, *_ in reversed(TABLES):
        op.drop_table(name)
