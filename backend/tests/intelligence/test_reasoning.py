import json
import os

import pytest

from intelligence.schemas import Constraint, Hypothesis, Problem, Variable, Provenance, Graph, Node
from intelligence.constraint_engine import (check_all, evaluate, SATISFIED, VIOLATED, INSUFFICIENT, register_validator)
from intelligence.hypothesis_engine import generate, experiment_for, CATEGORIES, CONCEPT_CATEGORY
from intelligence.validation_engine import validate
from intelligence.learning_engine import MemoryStore
from experiments import run_experiment, available_kinds
from experiments.linear_solver import gaussian_solve, conjugate_gradient
from experiments.runners import solve_load_distribution
from .helpers import load_script


# ------------------------------------------------------------- constraints
def C(id, kind, expr, desc="d"):
    return Constraint(id, desc, kind, expr)


def test_constraint_outcomes_and_status():
    hard = C("h", "hard", {"var": "x", "op": "<=", "value": 10})
    soft = C("s", "soft", {"var": "y", "op": ">=", "value": 5})
    assert evaluate(hard, {"x": 9}).outcome == SATISFIED
    assert evaluate(hard, {"x": 11}).outcome == VIOLATED
    assert evaluate(hard, {}).outcome == INSUFFICIENT
    assert evaluate(C("n", "hard", None), {}).outcome == INSUFFICIENT
    assert check_all([hard, soft], {"x": 9, "y": 1}).status == "ok"  # soft violation is a warning only
    assert check_all([hard, soft], {"x": 9, "y": 1}).warnings
    assert check_all([hard, soft], {"x": 12, "y": 9}).status == "blocked"
    assert check_all([hard], {}).status == "insufficient_information"
    # a violated hard constraint wins over missing information
    assert check_all([hard, C("h2", "hard", {"var": "z", "op": "<", "value": 1})], {"x": 99}).status == "blocked"


def test_compound_expressions_between_and_custom_validator():
    both = C("a", "hard", {"all": [{"var": "x", "op": ">=", "value": 1}, {"var": "x", "op": "<=", "value": 3}]})
    assert evaluate(both, {"x": 2}).outcome == SATISFIED and evaluate(both, {"x": 4}).outcome == VIOLATED
    assert evaluate(C("b", "hard", {"var": "x", "op": "between", "min": 1, "max": 2}), {"x": 1.5}).outcome == SATISFIED
    anyc = C("c", "hard", {"any": [{"var": "x", "op": "<", "value": 0}, {"var": "q", "op": "<", "value": 0}]})
    assert evaluate(anyc, {"x": 1}).outcome == INSUFFICIENT

    @register_validator("even")
    def _even(values, params):
        return (SATISFIED, "even") if values.get("n", 1) % 2 == 0 else (VIOLATED, "odd")
    assert evaluate(C("d", "hard", {"validator": "even"}), {"n": 4}).outcome == SATISFIED
    assert evaluate(C("e", "hard", {"validator": "nope"}), {}).outcome == INSUFFICIENT


def test_bite_condition_validator():
    c = C("bite", "hard", {"validator": "bite_condition"})
    ok = {"thickness_mm": 2.0, "reduction_fraction": 0.2, "roll_radius_mm": 100.0, "friction": 0.12}
    assert evaluate(c, ok).outcome == SATISFIED
    assert evaluate(c, dict(ok, reduction_fraction=0.8)).outcome == VIOLATED
    assert evaluate(c, {"thickness_mm": 2.0}).outcome == INSUFFICIENT


# ------------------------------------------------------------- solvers and experiments
def test_gaussian_and_cg_agree():
    A = [[4.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 2.0]]
    b = [1.0, 2.0, 3.0]
    x1, x2 = gaussian_solve(A, b), conjugate_gradient(A, b)
    assert all(abs(u - v) < 1e-8 for u, v in zip(x1, x2))
    assert all(abs(sum(A[i][j] * x1[j] for j in range(3)) - b[i]) < 1e-9 for i in range(3))
    with pytest.raises(ValueError):
        gaussian_solve([[1, 2], [2, 4]], [1, 2])


def _par_graph(w1=1.0, w2=1.0):
    g = Graph()
    for n in "sat":
        g.add_node(Node(n, n, role="conduit"))
    g.add_edge("s", "a", "flows_to", 1.0)
    g.add_edge("a", "t", "flows_to", w1)
    g.add_edge("a", "t", "flows_to", w2)
    return g


def test_load_distribution_conserves_flow_and_splits_by_conductance():
    r = solve_load_distribution(_par_graph(1.0, 3.0), "s", "t", 4.0)
    f = r["flows"]
    assert abs(f["e1"] - 4.0) < 1e-9
    assert abs(f["e2"] - 1.0) < 1e-9 and abs(f["e3"] - 3.0) < 1e-9
    r2 = solve_load_distribution(_par_graph(1.0, 3.0), "s", "t", 4.0, use_cg=True)
    assert abs(r2["flows"]["e3"] - 3.0) < 1e-6


def test_experiments_are_reproducible_and_record_metadata():
    p = {"arrival_rate": 0.9, "service_rate": 1.0, "servers": 1, "capacity": 5}
    a, b, c = run_experiment("queueing", p, 7), run_experiment("queueing", p, 7), run_experiment("queueing", p, 8)
    assert a.to_dict() == b.to_dict()
    assert a.metrics != c.metrics and a.config_hash != c.config_hash
    assert a.seed == 7 and a.code_version and "Simulation" in a.limitations or "simulation" in a.limitations.lower()
    for k in available_kinds():
        assert k in {"load_distribution", "network_flow", "resource_allocation", "queueing", "feedback_regulation",
                     "damped_oscillator", "strip_rolling_model", "strip_rolling_passes", "strip_rolling_gauge"}


def test_queueing_bigger_buffer_loses_less():
    base = {"arrival_rate": 0.9, "service_rate": 1.0, "servers": 1}
    small = run_experiment("queueing", dict(base, capacity=2), 1).metrics["loss_fraction"]
    big = run_experiment("queueing", dict(base, capacity=20), 1).metrics["loss_fraction"]
    assert big < small


def test_strip_rolling_model_physics_sanity():
    cu = run_experiment("strip_rolling_model", {"reduction": 0.2, "material": "copper"}).metrics
    assert abs(cu["draft_mm"] - 0.4) < 1e-9 and cu["bite_ok"]
    more = run_experiment("strip_rolling_model", {"reduction": 0.3, "material": "copper"}).metrics
    assert more["roll_force_kn"] > cu["roll_force_kn"]  # force rises with draft
    wide = run_experiment("strip_rolling_model", {"reduction": 0.2, "material": "copper", "width_mm": 100.0}).metrics
    assert abs(wide["roll_force_kn"] / cu["roll_force_kn"] - 2.0) < 1e-9  # linear in width
    big = run_experiment("strip_rolling_model", {"reduction": 0.8, "material": "copper"}).metrics  # bite limit is 2R(1-cos(atan mu)); the earlier limit was half
    assert not big["bite_ok"]
    two = run_experiment("strip_rolling_passes", {"reduction": 0.8, "passes": 2, "friction": 0.12}).metrics
    one = run_experiment("strip_rolling_passes", {"reduction": 0.8, "passes": 1, "friction": 0.12}).metrics
    assert two["peak_roll_force_kn"] < one["peak_roll_force_kn"] and two["all_passes_bite_ok"] and not one["all_passes_bite_ok"]


# ------------------------------------------------------------- hypotheses and validation
def _problem():
    return Problem("p", "p", "s", variables=[Variable("reduction", "%", value=20.0), Variable("thickness", "mm", value=2.0),
                                              Variable("width", "mm", value=50.0)])


class FakeConcept:
    def __init__(self, t):
        self.concept_type, self.name, self.analog_name, self.id = t, f"concept {t}", "Analog", f"{t}:x"


def test_hypotheses_have_prediction_falsifier_and_six_categories():
    assert len(CATEGORIES) == 6 and set(CONCEPT_CATEGORY.values()) == set(CATEGORIES)
    hs = generate([FakeConcept(t) for t in CONCEPT_CATEGORY], Problem("g", "g", "s"))
    assert len(hs) == len(CONCEPT_CATEGORY)
    for h in hs:
        assert h.prediction and h.falsifier and h.statement and h.provenance is Provenance.COMPUTATION
    assert {h.category for h in hs} == set(CATEGORIES)


def test_validation_reproducible_and_caveat_labelled():
    h = generate([FakeConcept("close_feedback_loop")], _problem())[0]
    v1, v2 = validate(h), validate(h)
    assert v1.to_dict() == v2.to_dict()
    assert v1.outcome == "supported"
    assert "SIMULATION ONLY" in v1.caveats
    assert v1.evidence["config_hashes"] and v1.evidence["code_version"] and v1.evidence["n"] == 20


def test_validation_untested_refuted_and_inconclusive_states():
    h = Hypothesis("u", "s", "p", "f")
    v = validate(h)
    assert v.outcome == "untested" and "No claim" in v.caveats
    # refuted: proposed arm is worse (less damping settles slower)
    h2 = Hypothesis("r", "s", "p", "f", experiment={"kind": "damped_oscillator", "baseline": {"damping": 1.0},
                                                    "proposed": {"damping": 0.1}, "metric": "settling_time", "direction": "lower"})
    assert validate(h2).outcome == "refuted"
    # inconclusive: tiny effect below threshold but positive
    h3 = Hypothesis("i", "s", "p", "f", experiment={"kind": "resource_allocation", "baseline": {"policy": "equal"},
                                                    "proposed": {"policy": "marginal"}, "metric": "total_utility",
                                                    "direction": "higher", "min_effect": 0.5})
    assert validate(h3).outcome == "inconclusive"
    h4 = Hypothesis("m", "s", "p", "f", experiment={"kind": "queueing", "baseline": None, "proposed": {}, "metric": "x", "direction": "lower"})
    assert validate(h4).outcome == "untested"


def test_unknown_concept_has_no_experiment():
    assert experiment_for("add_overload_protection", Problem("g", "g", "s")) is None


# ------------------------------------------------------------- learning
def test_memory_versioning_retrieval_and_persistence(tmp_path):
    m = MemoryStore()
    h = Hypothesis("h1", "s", "p", "f", category="robustness")
    v = validate(generate([FakeConcept("close_feedback_loop")], _problem())[0])
    r1 = m.record_validation(h, v, "close_feedback_loop", {"domain": "x"})
    r2 = m.record_validation(h, v, "close_feedback_loop", {"domain": "x"})
    assert (r1["version"], r2["version"]) == (1, 2) and r1["evidence_level"] == "simulation"
    assert m.latest("strategy:close_feedback_loop", {"domain": "x"})["version"] == 2
    assert len(m.history("strategy:close_feedback_loop")) == 2
    assert m.strategy_stats("close_feedback_loop")["supported"] == 2
    assert 0 < m.prior_adjustment("close_feedback_loop") <= 0.1
    m.record_feedback("match:x", True, {"domain": "x"})
    top = m.retrieve("", {"domain": "x"})
    assert top[0]["evidence_level"] == "expert_review"  # ranked above simulation
    with pytest.raises(ValueError):
        m.add("k", "o", evidence_level="rumour")
    path = os.path.join(tmp_path, "mem.json")
    m.save(path)
    assert MemoryStore(path).records == m.records


def test_untested_validation_is_stored_with_no_evidence_level():
    m = MemoryStore()
    v = validate(Hypothesis("u", "s", "p", "f"))
    assert m.record_validation(Hypothesis("u", "s", "p", "f"), v, "add_buffer")["evidence_level"] == "none"
