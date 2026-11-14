"""Seed table unique constraints and the source link tables.

UNVERIFIED in the authoring sandbox (Alembic, SQLAlchemy and PostgreSQL are not installable there).

Adds the natural key unique constraints that the idempotent seed (`python -m database.seed`) relies on, and the
`domain_system_sources` and `mechanism_sources` tables so every citation of a system or mechanism is linked
(`source_id` on the parent row stays the first citation). Existing duplicate rows would make the constraint step
fail; the seed never creates duplicates, so only hand inserted data can trigger that. Constraints are added with
batch mode so SQLite can run the migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_seed_constraints"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

UNIQUES = [
    ("sources", "uq_sources_citation", ["citation"]),
    ("domain_systems", "uq_domain_systems_domain_id_name", ["domain_id", "name"]),
    ("mechanisms", "uq_mechanisms_domain_system_id_name", ["domain_system_id", "name"]),
    ("system_entities", "uq_system_entities_domain_system_id_name", ["domain_system_id", "name"]),
    ("system_relationships", "uq_system_relationships_natural_key",
     ["domain_system_id", "source_entity_id", "target_entity_id", "relation_type"]),
]
LINKS = [
    ("domain_system_sources", "domain_system_id", "domain_systems", "uq_domain_system_sources_domain_system_id_source_id"),
    ("mechanism_sources", "mechanism_id", "mechanisms", "uq_mechanism_sources_mechanism_id_source_id"),
]


def upgrade() -> None:
    for table, name, cols in UNIQUES:
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(name, cols)
    for table, owner_col, owner_table, uq in LINKS:
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(owner_col, sa.Uuid(), sa.ForeignKey(owner_table + ".id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(owner_col, "source_id", name=uq),
        )


def downgrade() -> None:
    for table, *_ in reversed(LINKS):
        op.drop_table(table)
    for table, name, _ in reversed(UNIQUES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="unique")
