"""Core dataclass schemas for the ISOMORPH engine (stdlib only).

Every schema offers to_dict / from_dict and validate(). Controlled vocabularies
(roles, relations, dynamics tags, constraint tags) live here so that every
module shares one definition.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1


class Provenance(str, enum.Enum):
    SOURCE = "source"
    COMPUTATION = "computation"
    USER = "user"
    AI_HYPOTHESIS = "ai_hypothesis"


# ---------------------------------------------------------------- vocabularies
ROLES: Tuple[str, ...] = (
    "source", "producer", "sink", "consumer", "load", "dissipater", "buffer",
    "conduit", "junction", "medium", "regulator", "controller", "switch",
    "sensor", "actuator", "transformer",
)
ROLE_FAMILIES: Dict[str, str] = {
    "source": "supply", "producer": "supply",
    "sink": "demand", "consumer": "demand", "load": "demand", "dissipater": "demand",
    "buffer": "storage",
    "conduit": "transport", "junction": "transport", "medium": "transport",
    "regulator": "control", "controller": "control", "switch": "control",
    "sensor": "sensing",
    "actuator": "actuation", "transformer": "actuation",
}
# relation -> sign of influence of source on target (used for loop polarity)
RELATIONS: Dict[str, int] = {
    "flows_to": 1, "transmits": 1, "produces": 1, "activates": 1, "controls": 1,
    "observed_by": 1, "signals": 1, "stores_in": 1, "converts": 1, "supports": 1,
    "couples_to": 1,
    "consumes": -1, "inhibits": -1, "constrains": -1, "dissipates_to": -1,
    "competes_with": -1,
}
UNCLASSIFIED = "unclassified"
DYNAMICS_TAGS: Tuple[str, ...] = (
    "negative_feedback", "positive_feedback", "oscillation", "saturation",
    "threshold", "delay", "accumulation", "decay", "equilibrium", "queueing",
    "load_sharing", "cascade", "damping", "adaptation",
)
CONSTRAINT_TAGS: Tuple[str, ...] = (
    "capacity_limit", "conservation", "hard_limit", "stability_margin",
    "resource_scarcity", "safety_bound", "rate_limit", "non_negativity",
    "delay_bound", "equilibrium_condition",
)
BEHAVIOUR_TAGS: Tuple[str, ...] = (
    "regulate", "distribute", "buffer", "amplify", "dissipate", "convert",
    "transport", "sense", "oscillate", "allocate", "synchronize", "filter",
    "compete", "store", "protect", "reduce_variation",
)


class SchemaError(ValueError):
    pass


def _prov(v: Any) -> Provenance:
    try:
        return Provenance(v)
    except ValueError:
        raise SchemaError(f"invalid provenance: {v!r}")


@dataclass
class Node:
    id: str
    label: str
    kind: str = "entity"
    role: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = Provenance.SOURCE
    span: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(id=d["id"], label=d.get("label", d["id"]), kind=d.get("kind", "entity"),
                   role=d.get("role"), attrs=dict(d.get("attrs", {})),
                   provenance=_prov(d.get("provenance", "source")), span=d.get("span"),
                   confidence=float(d.get("confidence", 1.0)))


@dataclass
class Edge:
    id: str
    source: str
    target: str
    relation: str
    weight: float = 1.0
    provenance: Provenance = Provenance.SOURCE
    span: Optional[str] = None
    confidence: float = 1.0
    flags: List[str] = field(default_factory=list)

    @property
    def sign(self) -> int:
        return RELATIONS.get(self.relation, 1)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(id=d["id"], source=d["source"], target=d["target"], relation=d["relation"],
                   weight=float(d.get("weight", 1.0)),
                   provenance=_prov(d.get("provenance", "source")), span=d.get("span"),
                   confidence=float(d.get("confidence", 1.0)), flags=list(d.get("flags", [])))


@dataclass
class Graph:
    """Typed directed multigraph (parallel edges and self loops allowed)."""
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def node(self, nid: str) -> Optional[Node]:
        for n in self.nodes:
            if n.id == nid:
                return n
        return None

    def node_ids(self) -> List[str]:
        return [n.id for n in self.nodes]

    def add_node(self, node: Node) -> Node:
        if self.node(node.id) is not None:
            raise SchemaError(f"duplicate node id {node.id}")
        self.nodes.append(node)
        return node

    def add_edge(self, source: str, target: str, relation: str, weight: float = 1.0,
                 provenance: Provenance = Provenance.SOURCE, eid: Optional[str] = None,
                 **kw) -> Edge:
        flags = list(kw.pop("flags", []))
        if relation not in RELATIONS:
            flags.append(f"unclassified_relation:{relation}")
            relation = UNCLASSIFIED
        eid = eid or f"e{len(self.edges) + 1}"
        e = Edge(eid, source, target, relation, weight, provenance, flags=flags, **kw)
        self.edges.append(e)
        return e

    def out_edges(self, nid: str) -> List[Edge]:
        return [e for e in self.edges if e.source == nid]

    def in_edges(self, nid: str) -> List[Edge]:
        return [e for e in self.edges if e.target == nid]

    def validate(self) -> List[str]:
        """Return a list of problems (empty if valid)."""
        problems: List[str] = []
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            problems.append("duplicate node ids")
        eids = [e.id for e in self.edges]
        if len(set(eids)) != len(eids):
            problems.append("duplicate edge ids")
        idset = set(ids)
        for e in self.edges:
            if e.source not in idset or e.target not in idset:
                problems.append(f"edge {e.id} references unknown node")
            if e.relation not in RELATIONS and e.relation != UNCLASSIFIED:
                problems.append(f"edge {e.id} has unknown relation {e.relation}")
            if e.weight < 0:
                problems.append(f"edge {e.id} has negative weight")
        for n in self.nodes:
            if n.role is not None and n.role not in ROLES:
                problems.append(f"node {n.id} has unknown role {n.role}")
        return problems

    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes], "edges": [e.to_dict() for e in self.edges]}

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        return cls([Node.from_dict(n) for n in d.get("nodes", [])],
                   [Edge.from_dict(e) for e in d.get("edges", [])])


@dataclass
class Constraint:
    id: str
    description: str
    kind: str = "hard"  # hard | soft
    expression: Optional[dict] = None
    provenance: Provenance = Provenance.SOURCE
    tags: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        out = []
        if self.kind not in ("hard", "soft"):
            out.append(f"constraint {self.id}: kind must be hard or soft")
        for t in self.tags:
            if t not in CONSTRAINT_TAGS:
                out.append(f"constraint {self.id}: unknown tag {t}")
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Constraint":
        return cls(id=d["id"], description=d.get("description", ""), kind=d.get("kind", "hard"),
                   expression=d.get("expression"), provenance=_prov(d.get("provenance", "source")),
                   tags=list(d.get("tags", [])))


@dataclass
class Variable:
    name: str
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    role: str = "parameter"
    value: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Variable":
        return cls(**{k: d.get(k) for k in ("name", "unit", "min", "max", "role", "value")
                      if k in d or k == "name"})


@dataclass
class Problem:
    id: str
    title: str
    statement: str
    goal: str = ""
    graph: Graph = field(default_factory=Graph)
    constraints: List[Constraint] = field(default_factory=list)
    variables: List[Variable] = field(default_factory=list)

    def values(self) -> Dict[str, float]:
        return {v.name: v.value for v in self.variables if v.value is not None}

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "statement": self.statement, "goal": self.goal,
                "graph": self.graph.to_dict(), "constraints": [c.to_dict() for c in self.constraints],
                "variables": [v.to_dict() for v in self.variables]}

    @classmethod
    def from_dict(cls, d: dict) -> "Problem":
        return cls(id=d["id"], title=d.get("title", d["id"]), statement=d.get("statement", ""),
                   goal=d.get("goal", ""), graph=Graph.from_dict(d.get("graph", {})),
                   constraints=[Constraint.from_dict(c) for c in d.get("constraints", [])],
                   variables=[Variable.from_dict(v) for v in d.get("variables", [])])


@dataclass
class SourceRef:
    citation: str
    kind: str = "textbook"  # textbook | standard | paper | encyclopedia
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class System:
    """A knowledge-base entry: a system or mechanism with structure and behaviour."""
    id: str
    name: str
    domain: str
    summary: str
    graph: Graph
    kind: str = "system"  # system | mechanism
    behaviours: List[str] = field(default_factory=list)
    dynamics: List[str] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    sources: List[dict] = field(default_factory=list)
    confidence: str = "medium"  # low | medium | high
    limitations: str = ""

    def validate(self) -> List[str]:
        p = [f"{self.id}: {x}" for x in self.graph.validate()]
        if self.kind not in ("system", "mechanism"):
            p.append(f"{self.id}: bad kind")
        if self.confidence not in ("low", "medium", "high"):
            p.append(f"{self.id}: bad confidence")
        for b in self.behaviours:
            if b not in BEHAVIOUR_TAGS:
                p.append(f"{self.id}: unknown behaviour {b}")
        for t in self.dynamics:
            if t not in DYNAMICS_TAGS:
                p.append(f"{self.id}: unknown dynamics tag {t}")
        for c in self.constraints:
            p += c.validate()
        if not self.sources:
            p.append(f"{self.id}: no sources")
        if len(self.graph.nodes) < 3:
            p.append(f"{self.id}: fewer than 3 entities")
        if not self.graph.edges:
            p.append(f"{self.id}: no relationships")
        if any(n.role is None for n in self.graph.nodes):
            p.append(f"{self.id}: node without functional role")
        return p

    def text(self) -> str:
        parts = [self.name, self.summary] + [n.label for n in self.graph.nodes] + self.behaviours
        parts += [c.description for c in self.constraints]
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "domain": self.domain, "kind": self.kind,
                "summary": self.summary, "graph": self.graph.to_dict(), "behaviours": self.behaviours,
                "dynamics": self.dynamics, "constraints": [c.to_dict() for c in self.constraints],
                "sources": self.sources, "confidence": self.confidence, "limitations": self.limitations}

    @classmethod
    def from_dict(cls, d: dict) -> "System":
        return cls(id=d["id"], name=d["name"], domain=d["domain"], summary=d.get("summary", ""),
                   graph=Graph.from_dict(d.get("graph", {})), kind=d.get("kind", "system"),
                   behaviours=list(d.get("behaviours", [])), dynamics=list(d.get("dynamics", [])),
                   constraints=[Constraint.from_dict(c) for c in d.get("constraints", [])],
                   sources=list(d.get("sources", [])), confidence=d.get("confidence", "medium"),
                   limitations=d.get("limitations", ""))


@dataclass
class Fingerprint:
    schema_version: int
    functional: List[float]
    relational: List[float]
    topological: List[float]
    dynamic: List[float]
    constraint: List[float]
    semantic: List[float]
    hash: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        return cls(**d)


@dataclass
class ScoreWeights:
    functional: float = 25
    relationship: float = 25
    topological: float = 20
    dynamic: float = 15
    constraint: float = 10
    semantic: float = 5

    def validate(self) -> None:
        vals = asdict(self)
        if any(v < 0 for v in vals.values()):
            raise SchemaError("weights must be non-negative")
        if abs(sum(vals.values()) - 100.0) > 1e-9:
            raise SchemaError(f"weights must sum to 100, got {sum(vals.values())}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hypothesis:
    id: str
    statement: str
    prediction: str
    falsifier: str
    category: str = "efficiency"
    provenance: Provenance = Provenance.COMPUTATION
    status: str = "untested"
    experiment: Optional[dict] = None
    based_on: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        return d


@dataclass
class ExperimentRun:
    seed: int
    config_hash: str
    code_version: str
    metrics: Dict[str, Any]
    kind: str = ""
    limitations: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Validation:
    hypothesis_id: str
    outcome: str  # untested | supported | refuted | inconclusive
    caveats: str
    method: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
