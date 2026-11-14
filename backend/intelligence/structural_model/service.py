"""Structural model: a graph plus derived functional, dynamic and constraint descriptors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Union

from ..schemas import (Graph, Problem, System, CONSTRAINT_TAGS, DYNAMICS_TAGS, BEHAVIOUR_TAGS)
from ..graph_engine import metrics as graph_metrics

# Keyword cues (stem match) used to tag text with dynamics / constraint / behaviour tags.
DYNAMICS_CUES = {
    "negative_feedback": ["feedback", "regulat", "setpoint", "set point", "homeosta", "self-correct", "stabili"],
    "positive_feedback": ["runaway", "reinforc", "autocatal", "snowball", "avalanche", "amplif"],
    "oscillation": ["oscillat", "cycl", "periodic", "vibrat", "chatter", "wave"],
    "saturation": ["saturat", "plateau", "limit", "capacity", "clip"],
    "threshold": ["threshold", "trigger", "onset", "yield", "buckl", "breakdown"],
    "delay": ["delay", "lag", "latency", "dead time", "transport time"],
    "accumulation": ["accumulat", "buildup", "build-up", "inventory", "stock", "queue", "backlog"],
    "decay": ["decay", "attenuat", "dissipat", "wear", "fade", "relax"],
    "equilibrium": ["equilibri", "steady state", "steady-state", "balance"],
    "queueing": ["queue", "waiting", "congest", "backlog"],
    "load_sharing": ["load shar", "distribut", "parallel", "redundan", "spread"],
    "cascade": ["cascad", "propagat", "domino", "chain reaction"],
    "damping": ["damp", "absorb", "cushion", "dissipat"],
    "adaptation": ["adapt", "learn", "evolv", "tuning", "adjust"],
}
CONSTRAINT_CUES = {
    "capacity_limit": ["capacity", "maximum", "max ", "at most", "no more than", "upper limit"],
    "conservation": ["conserv", "mass balance", "balance of", "volume constancy", "constant volume"],
    "hard_limit": ["must not", "never exceed", "cannot exceed", "hard limit", "must stay"],
    "stability_margin": ["stability", "stable", "margin"],
    "resource_scarcity": ["scarce", "limited supply", "budget", "limited resource", "finite"],
    "safety_bound": ["safety", "safe ", "fracture", "failure", "rupture", "damage", "overload", "tolerance"],
    "rate_limit": ["rate limit", "per second", "per hour", "throughput", "speed limit", "slew"],
    "non_negativity": ["non-negative", "cannot be negative", "nonnegative"],
    "delay_bound": ["deadline", "latency", "response time", "time limit"],
    "equilibrium_condition": ["equilibrium", "steady state"],
}
BEHAVIOUR_CUES = {
    "regulate": ["regulat", "control", "maintain", "keep", "stabili"],
    "distribute": ["distribut", "spread", "share", "allocat"],
    "buffer": ["buffer", "reservoir", "cushion", "inventory"],
    "amplify": ["amplif", "gain", "multiply"],
    "dissipate": ["dissipat", "damp", "absorb"],
    "convert": ["convert", "transform", "reduce thickness", "roll", "shape"],
    "transport": ["transport", "carry", "move", "deliver", "convey"],
    "sense": ["sense", "measure", "monitor", "detect"],
    "oscillate": ["oscillat", "cycle", "vibrat"],
    "allocate": ["allocat", "schedule", "assign"],
    "filter": ["filter", "select"],
    "compete": ["compet", "contend"],
    "store": ["store", "storage", "hold"],
    "protect": ["protect", "prevent", "safe", "overload"],
    "reduce_variation": ["variation", "variance", "uniform", "consisten", "smooth", "tolerance"],
}


def tags_from_text(text: str, cues: Dict[str, List[str]]) -> List[str]:
    t = " " + text.lower() + " "
    return sorted(k for k, words in cues.items() if any(w in t for w in words))


@dataclass
class StructuralModel:
    id: str
    name: str
    domain: str
    graph: Graph
    text: str
    behaviours: List[str] = field(default_factory=list)
    dynamics: List[str] = field(default_factory=list)
    constraint_tags: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    role_counts: Dict[str, int] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    dynamics_declared: bool = False
    declared_dynamics: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "domain": self.domain, "graph": self.graph.to_dict(),
                "behaviours": self.behaviours, "dynamics": self.dynamics,
                "constraint_tags": self.constraint_tags, "metrics": self.metrics,
                "role_counts": self.role_counts, "flags": self.flags}


def derive_dynamics(graph: Graph, metrics: dict) -> List[str]:
    out = set()
    if metrics.get("negative_loops", 0):
        out.add("negative_feedback")
    if metrics.get("positive_loops", 0):
        out.add("positive_feedback")
    roles = {n.role for n in graph.nodes}
    if "buffer" in roles:
        out.add("accumulation")
    if metrics["motifs"].get("fan_out", 0) and metrics["motifs"].get("fan_in", 0) and "junction" in roles:
        out.add("load_sharing")
    return sorted(out)


def build_model(obj: Union[System, Problem], domain: str = "unknown") -> StructuralModel:
    """Build a structural model from a System (declared tags) or Problem (derived and cue tags)."""
    g = obj.graph
    m = graph_metrics(g)
    flags: List[str] = []
    roles: Dict[str, int] = {}
    for n in g.nodes:
        if n.role is None:
            flags.append(f"node {n.id} has no role")
        else:
            roles[n.role] = roles.get(n.role, 0) + 1
    if isinstance(obj, System):
        text = obj.text()
        declared = set(obj.dynamics)
        # Feedback tags are checkable on the graph: a claimed loop with no loop of that polarity is dropped and flagged.
        for tag, key in (("negative_feedback", "negative_loops"), ("positive_feedback", "positive_loops")):
            if tag in declared and m.get(key, 0) == 0:
                declared.discard(tag)
                flags.append(f"declared {tag} but graph has no such loop; tag ignored")
        dyn = sorted(declared | set(derive_dynamics(g, m)))
        cons = sorted({t for c in obj.constraints for t in c.tags})
        beh = sorted(obj.behaviours)
        return StructuralModel(obj.id, obj.name, obj.domain, g, text, beh, dyn, cons, m, roles, flags, True, sorted(declared))
    text = " ".join([obj.title, obj.statement, obj.goal] + [c.description for c in obj.constraints])
    dyn = sorted(set(derive_dynamics(g, m)) | set(tags_from_text(text, DYNAMICS_CUES)))
    cons = sorted({t for c in obj.constraints for t in c.tags} |
                  set(tags_from_text(" ".join(c.description for c in obj.constraints), CONSTRAINT_CUES)))
    beh = tags_from_text(obj.statement + " " + obj.goal, BEHAVIOUR_CUES)
    return StructuralModel(obj.id, obj.title, domain, g, text, beh, dyn, cons, m, roles, flags, False)
