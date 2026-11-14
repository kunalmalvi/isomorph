"""Generality: the same engine handles unrelated problems. The roller scenario is only one demo."""
import json

import pytest

from intelligence.domain_engine import DomainRegistry
from intelligence.pipeline import investigate
from intelligence.schemas import Problem
from knowledge_base import load_systems, load_domains
from .helpers import load_script


@pytest.fixture(scope="module")
def kb():
    return load_systems(), DomainRegistry(load_domains())


BIKE = ("A bike sharing company has docks at stations. Riders take bikes from a dock and return them to another dock. "
        "Demand varies by hour so some docks become empty while others are full. A truck moves bikes between docks. "
        "A dispatcher decides where the truck goes. The dock stock must not exceed 20 bikes. "
        "The goal is to keep every dock from running empty or full.")

ER = ("Patients arrive at the emergency department. A triage nurse sends each patient to a treatment room. "
      "Waiting patients form a queue. The number of rooms is at most 8. "
      "The goal is to reduce waiting time and avoid overcrowding.")


def test_unrelated_text_problem_runs_through_whole_pipeline(kb):
    systems, domains = kb
    r = investigate(BIKE, systems, domains, title="Bike sharing rebalancing", cross_domain_only=True, top_n=10)
    labels = {n.label for n in r["problem"].graph.nodes}
    assert {"truck", "dispatcher", "dock"} <= labels
    unknown_roles = [n.label for n in r["problem"].graph.nodes if n.role is None]
    assert "truck" in unknown_roles and any("truck" in q for q in r["perception"].clarification_questions)
    assert r["query_domain"] != "unknown"
    assert r["search"].matches and all(m.domain != r["query_domain"] for m in r["search"].matches)
    assert all(h.falsifier and h.prediction for h in r["hypotheses"])
    # nothing roller specific leaks in
    blob = json.dumps(r["search"].to_dict()) + json.dumps([c.to_dict() for c in r["concepts"]])
    assert "strip_rolling" not in blob
    assert all(h.experiment is None or h.experiment["kind"] not in ("strip_rolling_gauge", "strip_rolling_passes") for h in r["hypotheses"])


def test_second_problem_gets_generic_experiment_and_validation(kb):
    systems, domains = kb
    r = investigate(ER, systems, domains, title="Emergency department flow", cross_domain_only=True, top_n=10)
    outcomes = {v.outcome for v in r["validations"]}
    assert outcomes <= {"supported", "refuted", "inconclusive", "untested"}
    tested = [v for v in r["validations"] if v.outcome != "untested"]
    for v in tested:
        assert "baseline_mean" in v.evidence and v.caveats
    roles = {n.label: n.role for n in r["problem"].graph.nodes}
    assert roles["triage nurse"] is None and roles["queue"] == "buffer"
    assert any(e.relation == "flows_to" and e.source == "triage_nurse" for e in r["problem"].graph.edges)
    assert any("triage nurse" in q for q in r["perception"].clarification_questions)


def test_structured_problem_input_and_determinism(kb):
    systems, domains = kb
    g = {"nodes": [{"id": "grid", "label": "Grid", "role": "source"}, {"id": "bat", "label": "Battery", "role": "buffer"},
                   {"id": "house", "label": "House", "role": "consumer"}, {"id": "ctl", "label": "Controller", "role": "controller"},
                   {"id": "sen", "label": "Meter", "role": "sensor"}],
         "edges": [{"id": "e1", "source": "grid", "target": "bat", "relation": "flows_to"},
                   {"id": "e2", "source": "bat", "target": "house", "relation": "flows_to"},
                   {"id": "e3", "source": "bat", "target": "sen", "relation": "observed_by"},
                   {"id": "e4", "source": "sen", "target": "ctl", "relation": "signals"},
                   {"id": "e5", "source": "ctl", "target": "grid", "relation": "inhibits"}]}
    p = Problem.from_dict({"id": "home", "title": "Home storage", "statement": "Regulate battery charge to avoid overflow and shortage",
                           "goal": "regulate", "graph": g})
    a = investigate(p, systems, domains, query_domain="energy_systems", top_n=5)
    b = investigate(p, systems, domains, query_domain="energy_systems", top_n=5)
    assert a["search"].to_dict() == b["search"].to_dict()
    assert [h.to_dict() for h in a["hypotheses"]] == [h.to_dict() for h in b["hypotheses"]]
    assert a["search"].matches[0].mapping.confidence > 0.3


def test_demo_end_to_end_distinct_concepts_and_baseline_vs_proposed():
    demo = load_script("run_demo")
    r = demo.run_demo()
    types = [c.concept_type for c in r["concepts"]]
    assert len(set(types)) >= 3 and len(types) == len(set(types))
    tested = [v for v in r["validations"] if "baseline_mean" in v.evidence]
    assert tested, "at least one hypothesis must be tested with baseline vs proposed"
    ev = tested[0].evidence
    assert ev["proposed_mean"] != ev["baseline_mean"] and ev["config_hashes"]
    assert all("SIMULATION ONLY" in v.caveats for v in r["validations"] if v.outcome == "supported")
    # reproducible
    r2 = demo.run_demo()
    assert [v.to_dict() for v in r["validations"]] == [v.to_dict() for v in r2["validations"]]
    assert r["search"].to_dict() == r2["search"].to_dict()


def test_demo_reduction_is_configurable_and_constraints_block():
    demo = load_script("run_demo")
    ok = demo.run_demo(20.0)
    blocked = demo.run_demo(40.0)
    assert all(c.status == "ok" for c in ok["concepts"])
    assert any(c.status == "blocked" for c in blocked["concepts"])
    silver = demo.run_demo(20.0, "silver")
    assert silver["model_values"]["single_pass"]["roll_force_kn"] != ok["model_values"]["single_pass"]["roll_force_kn"]


def test_report_rendering_has_no_em_dash():
    demo = load_script("run_demo")
    r = demo.run_demo()
    report = demo.render_report(r, demo.material_table(r["params"]))
    assert "\u2014" not in report and "sample discovery report" in report
