"""Falsifiable hypotheses from transformation concepts, with an experiment specification when a credible
simulation exists. Hypotheses without a credible experiment stay 'untested' and say so."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..schemas import Hypothesis, Problem, Provenance
from ..transformation_engine import Concept

CATEGORIES = ("performance", "robustness", "efficiency", "safety", "scalability", "stability")
CONCEPT_CATEGORY = {
    "close_feedback_loop": "robustness", "add_sensing": "robustness", "add_buffer": "scalability",
    "add_overload_protection": "safety", "add_dissipation_path": "stability", "distribute_load": "performance",
    "allocate_resources": "efficiency",
}
DEFAULT_MIN_EFFECT = 0.05


def is_rolling_context(problem: Problem) -> bool:
    vals = {v.name: v.value for v in problem.variables}
    # all three variables must exist and carry a numeric value, otherwise rolling_params cannot be built
    return all(isinstance(vals.get(n), (int, float)) for n in ("reduction", "thickness", "width"))


def rolling_params(problem: Problem, context: Optional[dict] = None) -> dict:
    ctx = dict(context or {})
    vals = {v.name: v for v in problem.variables}
    red = vals["reduction"].value
    if vals["reduction"].unit in ("%", "percent") or (red is not None and red > 1.0):
        red = red / 100.0
    p = {"reduction": red, "thickness_mm": vals["thickness"].value, "width_mm": vals["width"].value}
    for k in ("material", "friction", "roll_radius_mm", "mill_modulus_kn_per_mm", "tolerance_mm", "coils"):
        if k in ctx:
            p[k] = ctx[k]
    return p


def experiment_for(concept_type: str, problem: Problem, context: Optional[dict] = None) -> Optional[dict]:
    rolling = is_rolling_context(problem)
    if rolling:
        base = rolling_params(problem, context)
        if concept_type == "close_feedback_loop":
            return {"kind": "strip_rolling_gauge", "baseline": dict(base, mode="open"), "proposed": dict(base, mode="feedback"),
                    "metric": "rms_dev_mm", "direction": "lower", "min_effect": DEFAULT_MIN_EFFECT,
                    "notes": ["Fixed screw setting vs integral gauge feedback with 2 coil delay.",
                              "Disturbance, drift and mill modulus values are assumptions, see runner limitations."]}
        if concept_type == "distribute_load":
            return {"kind": "strip_rolling_passes", "baseline": dict(base, passes=1), "proposed": dict(base, passes=2),
                    "metric": "peak_roll_force_kn", "direction": "lower", "min_effect": DEFAULT_MIN_EFFECT,
                    "notes": ["Splits the reduction into two equal true-strain passes. Total energy is not reduced."],
                    "deterministic": True}
        return None
    g1 = {"nodes": [{"id": "s", "label": "s", "role": "source"}, {"id": "t", "label": "t", "role": "sink"}],
          "edges": [{"id": "e1", "source": "s", "target": "t", "relation": "flows_to", "weight": 1.0}]}
    g2 = {"nodes": g1["nodes"], "edges": g1["edges"] + [{"id": "e2", "source": "s", "target": "t", "relation": "flows_to", "weight": 1.0}]}
    notes = ["Illustrative default parameters, not fitted to the problem. Replace with measured values."]
    table = {
        "close_feedback_loop": {"kind": "feedback_regulation", "baseline": {"mode": "open_loop"}, "proposed": {"mode": "feedback"},
                                "metric": "rms_error", "direction": "lower"},
        "add_sensing": {"kind": "feedback_regulation", "baseline": {"mode": "open_loop"}, "proposed": {"mode": "feedforward"},
                        "metric": "rms_error", "direction": "lower"},
        "add_buffer": {"kind": "queueing", "baseline": {"arrival_rate": 0.9, "service_rate": 1.0, "servers": 1, "capacity": 3},
                       "proposed": {"arrival_rate": 0.9, "service_rate": 1.0, "servers": 1, "capacity": 12},
                       "metric": "loss_fraction", "direction": "lower"},
        "distribute_load": {"kind": "load_distribution", "baseline": {"graph": g1, "source": "s", "sink": "t"},
                            "proposed": {"graph": g2, "source": "s", "sink": "t"}, "metric": "max_edge_flow", "direction": "lower",
                            "deterministic": True},
        "allocate_resources": {"kind": "resource_allocation", "baseline": {"policy": "equal"}, "proposed": {"policy": "marginal"},
                               "metric": "total_utility", "direction": "higher"},
        "add_dissipation_path": {"kind": "damped_oscillator", "baseline": {"damping": 0.1}, "proposed": {"damping": 1.0},
                                 "metric": "settling_time", "direction": "lower"},
    }
    spec = table.get(concept_type)
    if spec is None:
        return None
    spec = dict(spec, min_effect=DEFAULT_MIN_EFFECT, notes=notes, illustrative=True)
    return spec


def generate(concepts: Sequence[Concept], problem: Problem, context: Optional[dict] = None,
             provenance: Provenance = Provenance.COMPUTATION) -> List[Hypothesis]:
    out = []
    for i, c in enumerate(concepts, 1):
        cat = CONCEPT_CATEGORY.get(c.concept_type, "performance")
        spec = experiment_for(c.concept_type, problem, context)
        metric = spec["metric"] if spec else "the relevant outcome metric"
        direction = ("lower" if spec is None or spec["direction"] == "lower" else "higher")
        eff = int(DEFAULT_MIN_EFFECT * 100)
        if spec:
            statement = (f"If the design applies '{c.name}' (transferred from {c.analog_name}), then {metric} will be "
                         f"{direction} than in the current design.")
        else:
            statement = (f"If the design applies '{c.name}' (transferred from {c.analog_name}), the problem's key outcome "
                         f"will improve compared with the current design. No simulation model is available for this idea, so the "
                         f"outcome metric still has to be defined by the user.")
        prediction = (f"{metric} is {direction} by at least {eff}% on average and in at least 90% of seeded runs "
                      f"compared with the baseline arm.") if spec else \
            f"{metric} improves; no quantitative prediction is possible without an applicable model."
        falsifier = (f"The hypothesis is falsified if the mean improvement in {metric} is below {eff}% or the proposed arm "
                     f"wins in fewer than 90% of seeded runs, or if any hard constraint is violated.")
        out.append(Hypothesis(id=f"H{i}-{c.concept_type}", statement=statement, prediction=prediction, falsifier=falsifier,
                              category=cat, provenance=provenance, status="untested", experiment=spec,
                              based_on=[c.id]))
    return out
