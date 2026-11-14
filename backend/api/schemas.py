"""Pydantic v2 request and response schemas. They mirror the engine dataclasses in backend/intelligence/schemas.

UNVERIFIED in the authoring sandbox (pydantic is not installable there).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Provenance = Literal["source", "computation", "user", "ai_hypothesis"]
MemberRole = Literal["owner", "editor", "viewer"]
T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: List[Any] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=256)
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None


# ------------------------------------------------------------------ projects and problems
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_by: uuid.UUID
    archived_at: Optional[datetime] = None
    created_at: datetime
    role: Optional[str] = None


class MemberIn(BaseModel):
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = Field(default=None, max_length=254)
    role: MemberRole = "viewer"

    @model_validator(mode="after")
    def _one_identifier(self):
        if (self.user_id is None) == (self.email is None):
            raise ValueError("provide exactly one of user_id or email")
        return self


class MemberOut(ORM):
    user_id: uuid.UUID
    project_id: uuid.UUID
    role: str


class ProblemIn(BaseModel):
    project_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    statement: str = Field(min_length=1, max_length=20000)
    goal: Optional[str] = Field(default=None, max_length=5000)


class ProblemPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    statement: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    goal: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[Literal["draft", "modeled", "archived"]] = None


class ProblemOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    statement: str
    goal: Optional[str] = None
    status: str
    created_at: datetime


class EntityIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=2000)
    provenance: Provenance = "user"
    source_span: Optional[Dict[str, Any]] = None


class RelationshipIn(BaseModel):
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relation_type: str = Field(max_length=50)
    weight: float = Field(default=1.0, ge=0)
    provenance: Provenance = "user"


class ConstraintIn(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    kind: Literal["hard", "soft"] = "hard"
    expression: Optional[Dict[str, Any]] = None
    provenance: Provenance = "user"


class VariableIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: Optional[str] = Field(default=None, max_length=30)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    value: Optional[float] = None
    role: Literal["input", "output", "state", "parameter"] = "parameter"

    @model_validator(mode="after")
    def _range(self):
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must not exceed max_value")
        return self


class AssumptionIn(BaseModel):
    statement: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    provenance: Provenance = "user"


class EvidenceIn(BaseModel):
    statement: str = Field(min_length=1, max_length=2000)
    source_id: Optional[uuid.UUID] = None
    strength: float = Field(default=0.5, ge=0, le=1)
    provenance: Provenance = "user"


# ------------------------------------------------------------------ engine mirrors
class ScoreWeightsSchema(BaseModel):
    """Mirrors intelligence.schemas.ScoreWeights. Weights must sum to 100."""
    functional: float = Field(default=25, ge=0)
    relationship: float = Field(default=25, ge=0)
    topological: float = Field(default=20, ge=0)
    dynamic: float = Field(default=15, ge=0)
    constraint: float = Field(default=10, ge=0)
    semantic: float = Field(default=5, ge=0)

    @model_validator(mode="after")
    def _sum(self):
        total = sum(self.model_dump().values())
        if abs(total - 100.0) > 1e-9:
            raise ValueError(f"weights must sum to 100, got {total}")
        return self


class DiscoveryIn(BaseModel):
    problem_id: uuid.UUID
    weights: Optional[ScoreWeightsSchema] = None
    threshold: Optional[float] = Field(default=None, ge=0, le=100)
    top_k: int = Field(default=10, ge=1, le=100)
    provider: Optional[Literal["local", "openai", "gemini", "anthropic"]] = None


class DiscoveryOut(ORM):
    id: uuid.UUID
    problem_id: uuid.UUID
    status: str
    threshold: Optional[float] = None
    weights: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime


class AcceptedOut(BaseModel):
    id: uuid.UUID
    status: str


class StageEditIn(BaseModel):
    output: Dict[str, Any]


class MatchComponentOut(BaseModel):
    score: float = Field(ge=0, le=1)
    weight: float
    contribution: float
    explanation: str


class MatchBreakdownOut(BaseModel):
    total: float
    components: Dict[str, MatchComponentOut]
    domain_distance: float
    differences: List[str] = []
    limitations: List[str] = []


class MatchOut(ORM):
    id: uuid.UUID
    discovery_session_id: uuid.UUID
    system_key: str
    score: float
    domain_distance: Optional[float] = None
    rank: int


class StructuralModelIn(BaseModel):
    problem_id: uuid.UUID


class CompareIn(BaseModel):
    model_id_a: uuid.UUID
    model_id_b: uuid.UUID


class MappingIn(BaseModel):
    match_id: uuid.UUID


class TransformationIn(BaseModel):
    mapping_id: uuid.UUID
    concept_type: Optional[str] = Field(default=None, max_length=60)


class HypothesisIn(BaseModel):
    transformation_id: uuid.UUID


class HypothesisPatch(BaseModel):
    statement: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    prediction: Optional[str] = Field(default=None, max_length=5000)
    falsifier: Optional[str] = Field(default=None, max_length=5000)


class ExperimentIn(BaseModel):
    hypothesis_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    seed: int = Field(default=0, ge=0, le=2 ** 31 - 1)


class RunIn(BaseModel):
    seed: int = Field(default=0, ge=0, le=2 ** 31 - 1)


class ValidationIn(BaseModel):
    hypothesis_id: uuid.UUID
    seeds: int = Field(default=20, ge=1, le=200)


class ReportIn(BaseModel):
    project_id: uuid.UUID
    discovery_session_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)


class SettingsPatch(BaseModel):
    preferences: Optional[Dict[str, Any]] = None


class WeightsPatch(BaseModel):
    weights: ScoreWeightsSchema
