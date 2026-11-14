from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

EMBEDDING_DIM = 384

try:  # pgvector is optional. Without it (or with USE_PGVECTOR=false) embeddings are stored as JSON arrays.
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None


def use_pgvector() -> bool:
    return Vector is not None and os.environ.get("USE_PGVECTOR", "true").lower() not in ("0", "false", "no")


class EmbeddingVector(TypeDecorator):
    """vector(384) on PostgreSQL with pgvector, JSON array everywhere else (documented fallback)."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and use_pgvector():
            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())


JSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
