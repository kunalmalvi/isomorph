"""Transformation concepts: adapt structure found in an analog to the problem.

Every concept is derived from analog structure that has no counterpart in the problem (unmapped target
elements) or from analog dynamics missing in the problem. Concepts are de-duplicated by concept type so the
list contains distinct ideas, each citing the mapping pairs it relies on. Steps carry preconditions and
expected effects. Constraint checks come from the constraint engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from ..schemas import Problem, System
from ..structural_model import StructuralModel
from ..mapping_engine import Mapping
from ..constraint_engine import check_all, ConstraintReport

CONCEPT_TYPES = ("close_feedback_loop", "add_buffer", "add_overload_protection", "add_dissipation_path",
                 "distribute_load", "add_sensing", "allocate_resources")


@dataclass
class Concept:
    id: str
    concept_type: str
    name: str
    analog_id: str
    analog_name: str
    analog_score: float
    rationale: str
    steps: List[dict]
    relies_on: List[list]
    constraint_report: dict
    status: str
    preconditions: List[str] = field(default_factory=list)
    expected_effect: str = ""
    caveats: List[str] = field(default_factory=list)
    parameter_overrides: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _label(model: StructuralModel, nid: str) -> str:
    n = model.graph.node(nid)
    return n.label if n else nid


def _anchor_pairs(mapping: Mapping, tgt_model: StructuralModel, tgt_nodes: Sequence[str]) -> List[list]:
    """Mapped (problem node, analog node) pairs adjacent to the given analog nodes."""
    inv = {t: (s, sc) for s, t, sc in mapping.node_pairs}
    out = []
    want = set(tgt_nodes)
    for e in tgt_model.graph.edges:
        for a, b in ((e.source, e.target), (e.target, e.source)):
            if a in want and b in inv:
                s, sc = inv[b]
                p = [s, b, round(sc, 3)]
                if p not in out:
                    out.append(p)
    return sorted(out)


def derive_concepts(problem: Problem, pmodel: StructuralModel, analog: System, amodel: StructuralModel,
                    mapping: Mapping, analog_score: float,
                    overrides: Optional[Dict[str, Dict[str, float]]] = None) -> List[Concept]:
    """Concepts proposed by one analog (at most one per concept type)."""
    overrides = overrides or {}
    unm = set(mapping.unmapped_target)
    by_role: Dict[str, List[str]] = {}
    for n in amodel.graph.nodes:
        if n.id in unm and n.role:
            by_role.setdefault(n.role, []).append(n.id)
    q_roles = set(pmodel.role_counts)
    found: List[tuple] = []  # (type, name, anchor nodes, rationale, steps text list, effect)

    def add(ctype, name, nodes, why, steps, effect, pre):
        found.append((ctype, name, nodes, why, steps, effect, pre))

    qn = pmodel.metrics["negative_loops"]
    an = amodel.metrics["negative_loops"]
    if an > 0 and (qn == 0 or not ({"sensor", "controller"} <= q_roles)):
        roles_needed = [r for r in ("sensor", "controller", "regulator", "actuator", "switch") if r in amodel.role_counts]
        nodes = [n.id for n in amodel.graph.nodes if n.role in roles_needed]
        add("close_feedback_loop", "Close a measurement and correction loop",
            nodes, f"{analog.name} holds its variable steady with a negative feedback loop that the problem lacks or only partly has",
            ["Identify the variable that must stay near a target", "Measure it continuously or per cycle",
             "Compare with the target and compute a correction", "Apply the correction through an adjustable element"],
            "Disturbances are partly cancelled, lowering variation around the target",
            ["a measurable output", "an adjustable input", "loop delay shorter than disturbance time scale"])
    if "buffer" not in q_roles and by_role.get("buffer"):
        add("add_buffer", "Introduce a buffer between supply and demand", by_role["buffer"],
            f"{analog.name} uses a buffer element that absorbs mismatch between inflow and outflow",
            ["Locate the point where inflow and outflow rates differ in time", "Insert a store with finite capacity there",
             "Size the store to the largest expected mismatch"],
            "Short bursts are absorbed instead of propagating, at the cost of added storage and delay",
            ["inflow and outflow vary over time", "space or capacity for storage"])
    prot = by_role.get("regulator", []) + by_role.get("switch", [])
    if prot and ("threshold" in amodel.dynamics or "saturation" in amodel.dynamics or "protect" in amodel.behaviours):
        add("add_overload_protection", "Add a threshold relief or limiting element", prot,
            f"{analog.name} includes a threshold element that limits the stressed quantity",
            ["Identify the quantity with a hard limit", "Add an element that opens, limits or diverts above a threshold",
             "Set the threshold below the hard limit with margin"],
            "The stressed quantity is bounded; excess is diverted or refused",
            ["a quantity with a known limit", "a place to divert or refuse excess"])
    if by_role.get("dissipater") and ("damping" in amodel.dynamics or "dissipate" in amodel.behaviours):
        add("add_dissipation_path", "Add a controlled dissipation path", by_role.get("dissipater", []),
            f"{analog.name} removes excess energy or activity through a dedicated dissipating element",
            ["Find the energy or activity that causes overshoot or oscillation", "Add a path that removes a share in proportion to it",
             "Tune the share so response stays fast but does not ring"],
            "Overshoot and oscillation decay faster", ["a quantity that can be bled off without breaking the goal"])
    a_mo, q_mo = amodel.metrics["motifs"], pmodel.metrics["motifs"]
    parallel = a_mo["bi_fan"] >= 1 or "load_sharing" in amodel.declared_dynamics
    if parallel and "load_sharing" not in pmodel.dynamics and q_mo["bi_fan"] == 0:
        add("distribute_load", "Split the load over parallel paths", [n.id for n in amodel.graph.nodes if n.role in ("junction", "conduit")] or list(unm),
            f"{analog.name} divides flow or load over parallel paths and recombines them",
            ["Identify the single path that carries the whole load", "Create two or more parallel paths of similar capacity",
             "Split the load between them and recombine downstream"],
            "Peak load on any one path falls roughly in proportion to the number of paths",
            ["the load can be divided", "parallel paths can be built"])
    if by_role.get("sensor") and "sensor" not in q_roles:
        add("add_sensing", "Add an upstream measurement for anticipation", by_role["sensor"],
            f"{analog.name} senses its state before acting on it",
            ["Choose a measurable upstream indicator of the disturbance", "Feed it forward to adjust the process before the effect arrives"],
            "Disturbances are partly compensated before they reach the output", ["an upstream variable correlated with the disturbance"])
    if "allocate" in amodel.behaviours and "allocate" not in pmodel.behaviours:
        add("allocate_resources", "Allocate the limited resource by marginal value", [n.id for n in amodel.graph.nodes if n.role in ("regulator", "controller")] or list(unm),
            f"{analog.name} divides a limited supply among competing uses by a rule",
            ["List competing uses and their diminishing returns", "Give each increment to the use with the highest marginal gain"],
            "Total benefit from the same resource rises compared with an equal split", ["competing uses", "measurable benefit per use"])

    concepts = []
    values = problem.values()
    for ctype, name, nodes, why, steps_txt, effect, pre in found:
        pairs = _anchor_pairs(mapping, amodel, nodes)
        if not pairs:
            continue  # a concept must be anchored to mapped elements, otherwise it is not grounded in the mapping
        steps = []
        for i, t in enumerate(steps_txt, 1):
            steps.append({"order": i, "action": t, "relies_on": pairs, "expected_effect": effect if i == len(steps_txt) else "",
                          "preconditions": pre if i == 1 else []})
        vals = dict(values)
        ov = overrides.get(ctype, {})
        vals.update(ov)
        report: ConstraintReport = check_all(problem.constraints, vals)
        caveats = ["Concept is an analogy transfer. Feasibility in the problem's domain is not established.",
                   f"Based on analog entry confidence {analog.confidence}."]
        if not pairs:
            caveats.append("No mapped anchor elements: the insertion point in the problem must be chosen by a human.")
        concepts.append(Concept(id=f"{ctype}:{analog.id}", concept_type=ctype, name=name, analog_id=analog.id,
                                analog_name=analog.name, analog_score=analog_score, rationale=why, steps=steps,
                                relies_on=pairs, constraint_report=report.to_dict(), status=report.status,
                                preconditions=pre, expected_effect=effect, caveats=caveats, parameter_overrides=ov))
    return concepts


def select_distinct(all_concepts: Sequence[Concept], limit: int = 8) -> List[Concept]:
    """Best concept per type (highest analog score, then id), ordered by score."""
    best: Dict[str, Concept] = {}
    for c in sorted(all_concepts, key=lambda c: (-round(c.analog_score, 9), c.id)):
        if c.concept_type not in best:
            best[c.concept_type] = c
    return sorted(best.values(), key=lambda c: (-round(c.analog_score, 9), c.id))[:limit]
