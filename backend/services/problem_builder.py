"""Builds an engine Problem from stored problem parts (entities, relationships, constraints, variables). Stdlib only."""
from __future__ import annotations

from typing import List, Optional

from intelligence.schemas import (ROLES, RELATIONS, Constraint, Edge, Graph, Node, Problem, Provenance, SchemaError, Variable)


def _prov(v: Optional[str]) -> Provenance:
    try:
        return Provenance(v or "user")
    except ValueError:
        raise SchemaError(f"invalid provenance {v!r}")


def build_problem(problem_id: str, title: str, statement: str, goal: str, entities: List[dict], relationships: List[dict],
                  constraints: List[dict], variables: List[dict]) -> Problem:
    """Dict inputs use the API field names. `kind` of an entity is used as the role when it is a known role."""
    g = Graph()
    for e in entities:
        role = e.get("role") or (e.get("kind") if e.get("kind") in ROLES else None)
        g.add_node(Node(id=str(e["id"]), label=e.get("name") or str(e["id"]), kind=e.get("kind") or "entity", role=role,
                        provenance=_prov(e.get("provenance")), span=(e.get("source_span") or {}).get("text") if isinstance(e.get("source_span"), dict) else None))
    for i, r in enumerate(relationships, 1):
        rel = r.get("relation_type")
        if rel not in RELATIONS:
            raise SchemaError(f"unknown relation type {rel!r}")
        g.add_edge(str(r["source_entity_id"]), str(r["target_entity_id"]), rel, float(r.get("weight") or 1.0),
                   _prov(r.get("provenance")))
    errs = g.validate()
    if errs:
        raise SchemaError("; ".join(errs))
    cons = [Constraint(id=str(c["id"]), description=c.get("description", ""), kind=c.get("kind", "hard"),
                       expression=c.get("expression"), provenance=_prov(c.get("provenance"))) for c in constraints]
    vs = [Variable(name=v["name"], unit=v.get("unit"), min=v.get("min_value"), max=v.get("max_value"),
                   role=v.get("role") or "parameter", value=v.get("value")) for v in variables]
    return Problem(id=problem_id, title=title, statement=statement, goal=goal or "", graph=g, constraints=cons, variables=vs)
