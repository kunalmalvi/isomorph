"""SQLAlchemy 2.x models for every table in docs/database-design.md plus pipeline_stages, reports and user_settings.

UNVERIFIED in the authoring sandbox (SQLAlchemy is not installable there). Enums are stored as VARCHAR with a CHECK
constraint (native_enum=False) so SQLite and PostgreSQL behave the same. Soft deleted rows have deleted_at set.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, EmbeddingVector, IdMixin, JSONType, SoftDeleteMixin, TimestampMixin


def _enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


PROVENANCE_VALUES = ('source', 'computation', 'user', 'ai_hypothesis')
MEMBER_ROLE_VALUES = ('owner', 'editor', 'viewer')
PROBLEM_STATUS_VALUES = ('draft', 'modeled', 'archived')
CONSTRAINT_KIND_VALUES = ('hard', 'soft')
VARIABLE_ROLE_VALUES = ('input', 'output', 'state', 'parameter')
SOURCE_TYPE_VALUES = ('paper', 'book', 'standard', 'dataset', 'internal')
SESSION_STATUS_VALUES = ('queued', 'running', 'done', 'failed', 'cancelled')
TRANSFORMATION_STATUS_VALUES = ('ok', 'blocked')
HYPOTHESIS_STATUS_VALUES = ('untested', 'supported', 'refuted', 'inconclusive')


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = 'organizations'
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True)


class Project(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'projects'
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectMember(IdMixin, TimestampMixin, Base):
    __tablename__ = 'project_members'
    __table_args__ = (UniqueConstraint('project_id', 'user_id', name='uq_project_members_project_id_user_id'),)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role: Mapped[str] = mapped_column(_enum('member_role', *MEMBER_ROLE_VALUES), nullable=False)


class Problem(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'problems'
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(_enum('problem_status', *PROBLEM_STATUS_VALUES), nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)


class ProblemEntity(IdMixin, TimestampMixin, Base):
    __tablename__ = 'problem_entities'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)
    source_span: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class ProblemRelationship(IdMixin, TimestampMixin, Base):
    __tablename__ = 'problem_relationships'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problem_entities.id', ondelete='CASCADE'), nullable=False, index=True)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problem_entities.id', ondelete='CASCADE'), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class Constraint(IdMixin, TimestampMixin, Base):
    __tablename__ = 'constraints'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(_enum('constraint_kind', *CONSTRAINT_KIND_VALUES), nullable=False)
    expression: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class Variable(IdMixin, TimestampMixin, Base):
    __tablename__ = 'variables'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    min_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    role: Mapped[str] = mapped_column(_enum('variable_role', *VARIABLE_ROLE_VALUES), nullable=False)


class Assumption(IdMixin, TimestampMixin, Base):
    __tablename__ = 'assumptions'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = 'sources'
    __table_args__ = (UniqueConstraint('citation', name='uq_sources_citation'),)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(_enum('source_type', *SOURCE_TYPE_VALUES), nullable=False)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = 'evidence'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('sources.id', ondelete='RESTRICT'), nullable=True, index=True)
    strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class Domain(IdMixin, TimestampMixin, Base):
    __tablename__ = 'domains'
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_domain_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('domains.id', ondelete='SET NULL'), nullable=True, index=True)


class DomainSystem(IdMixin, TimestampMixin, Base):
    __tablename__ = 'domain_systems'
    __table_args__ = (UniqueConstraint('domain_id', 'name', name='uq_domain_systems_domain_id_name'),)
    domain_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('domains.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False, index=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class Mechanism(IdMixin, TimestampMixin, Base):
    __tablename__ = 'mechanisms'
    __table_args__ = (UniqueConstraint('domain_system_id', 'name', name='uq_mechanisms_domain_system_id_name'),)
    domain_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('domain_systems.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    function_tag: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False, index=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class SystemEntity(IdMixin, TimestampMixin, Base):
    __tablename__ = 'system_entities'
    __table_args__ = (UniqueConstraint('domain_system_id', 'name', name='uq_system_entities_domain_system_id_name'),)
    domain_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('domain_systems.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SystemRelationship(IdMixin, TimestampMixin, Base):
    __tablename__ = 'system_relationships'
    __table_args__ = (UniqueConstraint('domain_system_id', 'source_entity_id', 'target_entity_id', 'relation_type', name='uq_system_relationships_natural_key'),)
    domain_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('domain_systems.id', ondelete='CASCADE'), nullable=False, index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('system_entities.id', ondelete='CASCADE'), nullable=False, index=True)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('system_entities.id', ondelete='CASCADE'), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class DomainSystemSource(IdMixin, TimestampMixin, Base):
    """Every citation of a domain system. `domain_systems.source_id` stays the primary (first) one."""
    __tablename__ = 'domain_system_sources'
    __table_args__ = (UniqueConstraint('domain_system_id', 'source_id', name='uq_domain_system_sources_domain_system_id_source_id'),)
    domain_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('domain_systems.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False, index=True)


class MechanismSource(IdMixin, TimestampMixin, Base):
    """Every citation of a mechanism. `mechanisms.source_id` stays the primary (first) one."""
    __tablename__ = 'mechanism_sources'
    __table_args__ = (UniqueConstraint('mechanism_id', 'source_id', name='uq_mechanism_sources_mechanism_id_source_id'),)
    mechanism_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('mechanisms.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('sources.id', ondelete='RESTRICT'), nullable=False, index=True)


class Embedding(IdMixin, TimestampMixin, Base):
    __tablename__ = 'embeddings'
    __table_args__ = (Index('ix_embeddings_owner_type_owner_id', 'owner_type', 'owner_id'),)
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list] = mapped_column(EmbeddingVector, nullable=False)


class DiscoverySession(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'discovery_sessions'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(_enum('session_status', *SESSION_STATUS_VALUES), nullable=False)
    input: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PipelineStage(IdMixin, TimestampMixin, Base):
    __tablename__ = 'pipeline_stages'
    __table_args__ = (UniqueConstraint('discovery_session_id', 'name', name='uq_pipeline_stages_discovery_session_id_name'),)
    discovery_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('discovery_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StructuralModel(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'structural_models'
    problem_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('problems.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    discovery_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('discovery_sessions.id', ondelete='SET NULL'), nullable=True, index=True)
    graph: Mapped[dict] = mapped_column(JSONType, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)


class StructuralFingerprint(IdMixin, TimestampMixin, Base):
    __tablename__ = 'structural_fingerprints'
    structural_model_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('structural_models.id', ondelete='CASCADE'), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    functional: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    relational: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    topological: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    dynamic: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    constraint: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    semantic: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    hash: Mapped[str] = mapped_column(Text, nullable=False)


class CandidateMatch(IdMixin, TimestampMixin, Base):
    __tablename__ = 'candidate_matches'
    __table_args__ = (Index('ix_candidate_matches_discovery_session_id_rank', 'discovery_session_id', 'rank'),)
    discovery_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('discovery_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    domain_system_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('domain_systems.id', ondelete='SET NULL'), nullable=True, index=True)
    system_key: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONType, nullable=False)
    domain_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


class StructuralMapping(IdMixin, TimestampMixin, Base):
    __tablename__ = 'structural_mappings'
    candidate_match_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('candidate_matches.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    node_pairs: Mapped[dict] = mapped_column(JSONType, nullable=False)
    edge_pairs: Mapped[dict] = mapped_column(JSONType, nullable=False)
    unmapped_source: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    unmapped_target: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Transformation(IdMixin, TimestampMixin, Base):
    __tablename__ = 'transformations'
    structural_mapping_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('structural_mappings.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    concept: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    steps: Mapped[dict] = mapped_column(JSONType, nullable=False)
    constraint_report: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(_enum('transformation_status', *TRANSFORMATION_STATUS_VALUES), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Hypothesis(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'hypotheses'
    transformation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('transformations.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    prediction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    falsifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    experiment: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    provenance: Mapped[str] = mapped_column(_enum('provenance', *PROVENANCE_VALUES), nullable=False)
    status: Mapped[str] = mapped_column(_enum('hypothesis_status', *HYPOTHESIS_STATUS_VALUES), nullable=False)


class Experiment(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'experiments'
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('hypotheses.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ExperimentConfiguration(IdMixin, TimestampMixin, Base):
    __tablename__ = 'experiment_configurations'
    experiment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False, index=True)
    parameters: Mapped[dict] = mapped_column(JSONType, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ExperimentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = 'experiment_runs'
    experiment_configuration_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('experiment_configurations.id', ondelete='CASCADE'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    code_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentResult(IdMixin, TimestampMixin, Base):
    __tablename__ = 'experiment_results'
    experiment_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('experiment_runs.id', ondelete='CASCADE'), nullable=False, index=True)
    metrics: Mapped[dict] = mapped_column(JSONType, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ValidationRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = 'validation_records'
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('hypotheses.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(_enum('hypothesis_status', *HYPOTHESIS_STATUS_VALUES), nullable=False)
    caveats: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DiscoveryMemory(IdMixin, TimestampMixin, Base):
    __tablename__ = 'discovery_memory'
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class StrategyPerformance(IdMixin, TimestampMixin, Base):
    __tablename__ = 'strategy_performance'
    strategy_name: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    trials: Mapped[int] = mapped_column(Integer, nullable=False)
    successes: Mapped[int] = mapped_column(Integer, nullable=False)


class UserFeedback(IdMixin, TimestampMixin, Base):
    __tablename__ = 'user_feedback'
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ActivityLog(IdMixin, TimestampMixin, Base):
    __tablename__ = 'activity_logs'
    __table_args__ = (Index('ix_activity_logs_project_id_created_at', 'project_id', 'created_at'),)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column('metadata', JSONType, nullable=True)


class VersionHistory(IdMixin, TimestampMixin, Base):
    __tablename__ = 'version_history'
    __table_args__ = (UniqueConstraint('entity_type', 'entity_id', 'version', name='uq_version_history_entity_type_entity_id_version'),)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    diff: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)


class Report(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = 'reports'
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    discovery_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('discovery_sessions.id', ondelete='SET NULL'), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)


class UserSettings(IdMixin, TimestampMixin, Base):
    __tablename__ = 'user_settings'
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
