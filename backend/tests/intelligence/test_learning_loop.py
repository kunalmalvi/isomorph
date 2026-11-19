"""Self-improving loop core: evidence, registry, proposals, gate, overlay, conditional priors. No real clock."""
import json
import os

import pytest

from intelligence.learning_engine import (
    EvidenceLog, MemoryStore, ModelRegistry, build_candidate, empty_config, heldout_overlap, heldout_vocabulary,
    learned_prior, propose_lexicon, propose_priors, run_gate, compute_metrics, DECISIONS)
from intelligence.perception import perceive_text
from evaluation.perception import evaluate
from .helpers import ROOT

PUBLISHED = {"role_accuracy": 0.404, "precision_when_assigned": 0.857, "detection_recall": 0.846}


class Clock:
    def __init__(self):
        self.t = 0

    def __call__(self):
        self.t += 1
        return self.t


def corr(log, term, role, run):
    return log.append("role_correction", {"term": term, "role": role, "run_id": run})


def accept_gate(candidate, active, cv=None, av=None):
    return {"accepted": True, "sensitive": False, "regressions": [], "note": "stub", "metrics": {}}


# ---------------------------------------------------------------- evidence

def test_evidence_validation_rejects_bad_input():
    log = EvidenceLog(clock=Clock())
    for kind, payload in [
        ("role_correction", {"term": "Flumox", "role": "regulator"}),
        ("role_correction", {"term": "a b c d e", "role": "regulator"}),
        ("role_correction", {"term": "flu1", "role": "regulator"}),
        ("role_correction", {"term": "flumox", "role": "wizard"}),
        ("hypothesis_feedback", {"concept_type": "x", "decision": "maybe"}),
        ("experiment_outcome", {"concept_type": "x", "outcome": "supported", "evidence_level": "real_world"}),
        ("experiment_outcome", {"concept_type": "x", "outcome": "great"}),
        ("mapping_edit", {"action": "delete", "source": "a", "target": "b"}),
        ("bogus", {}),
    ]:
        with pytest.raises(ValueError):
            log.append(kind, payload)
    with pytest.raises(ValueError):
        log.append("role_correction", {"term": "flumox", "role": "regulator"}, provenance="experiment")
    assert log.events == []


def test_evidence_provenance_and_persistence(tmp_path):
    path = str(tmp_path / "ev.jsonl")
    log = EvidenceLog(path, clock=Clock())
    a = corr(log, "flumox", "regulator", "r1")
    b = log.append("experiment_outcome", {"concept_type": "feedback", "outcome": "supported"})
    assert a["provenance"] == "user" and b["provenance"] == "experiment"
    assert b["payload"]["evidence_level"] == "simulation"
    again = EvidenceLog(path)
    assert [e["id"] for e in again.events] == ["ev-1", "ev-2"] and again.events[0]["timestamp"] == 1


def test_decisions_match_annotations():
    from services.annotations import DECISIONS as ANN
    assert tuple(DECISIONS) == tuple(ANN)


# ---------------------------------------------------------------- lexicon proposals

def test_two_distinct_corrections_create_candidate_one_does_not():
    log = EvidenceLog(clock=Clock())
    corr(log, "flumox", "regulator", "r1")
    corr(log, "zindle", "buffer", "r1")
    corr(log, "flumox", "regulator", "r2")
    cand, report = propose_lexicon(log.events)
    assert cand["lexicon_overlay"] == {"flumox": "regulator"}
    assert [s for s in report["skipped"] if s["term"] == "zindle"][0]["reason"] == "insufficient_evidence"


def test_same_run_repeated_does_not_count_twice():
    log = EvidenceLog(clock=Clock())
    corr(log, "flumox", "regulator", "r1")
    corr(log, "flumox", "regulator", "r1")
    cand, _ = propose_lexicon(log.events)
    assert cand["lexicon_overlay"] == {}


def test_conflicting_corrections_not_learned():
    log = EvidenceLog(clock=Clock())
    for i, role in enumerate(["regulator", "regulator", "buffer", "buffer"]):
        corr(log, "flumox", role, f"r{i}")
    cand, report = propose_lexicon(log.events)
    assert cand["lexicon_overlay"] == {}
    assert report["skipped"][0]["reason"] == "conflict"


def test_agreement_threshold_80_percent():
    log = EvidenceLog(clock=Clock())
    for i in range(4):
        corr(log, "flumox", "regulator", f"r{i}")
    corr(log, "flumox", "buffer", "r9")
    cand, _ = propose_lexicon(log.events)
    assert cand["lexicon_overlay"] == {"flumox": "regulator"}  # 4 of 5 = 0.8
    corr(log, "flumox", "buffer", "r10")
    cand, report = propose_lexicon(log.events)
    assert cand["lexicon_overlay"] == {} and report["skipped"][0]["reason"] == "conflict"


def test_heldout_overlap_is_quarantined_and_recorded():
    log = EvidenceLog(clock=Clock())
    for run in ("r1", "r2"):
        corr(log, "thermowell", "sensor", run)  # appears in the frozen held-out phrases
        corr(log, "flumox", "regulator", run)
    cand, report = propose_lexicon(log.events)
    assert "thermowell" not in cand["lexicon_overlay"] and "flumox" in cand["lexicon_overlay"]
    assert {"term": "thermowell", "reason": "heldout_overlap"} in report["skipped"]


def test_heldout_vocabulary_flags_frozen_terms_only():
    vocab = heldout_vocabulary()
    assert heldout_overlap("thermowell", vocab) and not heldout_overlap("flumox", vocab)


# ---------------------------------------------------------------- priors

def test_priors_need_n3_and_carry_conditions():
    log = EvidenceLog(clock=Clock())
    cond = {"query_domain": "brewing"}
    for d in ("saved", "saved", "rejected"):
        log.append("hypothesis_feedback", {"concept_type": "feedback", "decision": d, "conditions": cond})
    log.append("hypothesis_feedback", {"concept_type": "buffer", "decision": "saved", "conditions": cond})
    cand, report = propose_priors(log.events)
    assert len(cand["priors"]) == 1
    p = cand["priors"][0]
    assert p["key"] == "feedback" and p["conditions"] == cond and p["n"] == 3
    assert p["accepted"] == 2 and p["rejected"] == 1 and abs(p["value"]) <= 0.1 and p["basis"] == "user_feedback"
    assert report["skipped"][0]["key"] == "buffer"


def test_prior_value_is_bounded_and_experiments_marked_simulation():
    log = EvidenceLog(clock=Clock())
    for _ in range(50):
        log.append("experiment_outcome", {"concept_type": "feedback", "outcome": "supported", "conditions": {"query_domain": "x"}})
    p = propose_priors(log.events)[0]["priors"][0]
    assert 0 < p["value"] <= 0.1 and p["basis"] == "simulation"


def test_learned_prior_only_inside_conditions():
    cfg = {"lexicon_overlay": {}, "priors": [{"key": "feedback", "conditions": {"query_domain": "brewing"},
                                                "n": 5, "accepted": 5, "rejected": 0, "value": 0.07}]}
    assert learned_prior(cfg, "feedback", {"query_domain": "brewing"}) == 0.07
    assert learned_prior(cfg, "feedback", {"query_domain": "cooking"}) == 0.0
    assert learned_prior(cfg, "feedback", {}) == 0.0
    assert learned_prior(cfg, "buffer", {"query_domain": "brewing"}) == 0.0


def test_memory_prior_adjustment_conditional_and_backward_compatible():
    m = MemoryStore()
    for _ in range(2):
        m.add("strategy:feedback", "supported", conditions={"query_domain": "a"})
    assert m.prior_adjustment("feedback") > 0  # unconditional behaviour unchanged
    assert m.prior_adjustment("feedback", {"query_domain": "a"}) == 0.0  # only 2 matching records
    m.add("strategy:feedback", "supported", conditions={"query_domain": "a"})
    assert m.prior_adjustment("feedback", {"query_domain": "a"}) == 0.1
    assert m.prior_adjustment("feedback", {"query_domain": "b"}) == 0.0


# ---------------------------------------------------------------- gate and registry

def test_gate_accepts_neutral_candidate_and_reports_insensitivity():
    cand = {"lexicon_overlay": {"flumox": "regulator"}, "priors": []}
    report = run_gate(cand, empty_config())
    assert report["accepted"] and not report["sensitive"] and "not sensitive" in report["note"]
    assert set(report["metrics"]) == {"perception.role_accuracy", "perception.precision_when_assigned",
                                      "perception.detection_recall", "heldout.mrr_strong", "heldout.ndcg_at_10",
                                      "tuning.mrr_primary"}


def test_gate_rejects_candidate_that_lowers_a_metric(tmp_path):
    reg = ModelRegistry(str(tmp_path / "reg"), clock=Clock())

    # Built by calling the gate directly: the leak guard would quarantine these held-out terms in a real proposal.
    data = json.load(open(os.path.join(ROOT, "data", "benchmark_problems", "perception_heldout.json")))
    terms = {}
    for prob in data["problems"]:
        for g in prob["entities"]:
            words = g["phrase"].lower().split()
            if len(words) == 1 and g["role"] != "sink":
                terms[words[0]] = "sink"
    cand = {"lexicon_overlay": dict(sorted(terms.items())), "priors": []}
    report = run_gate(cand, empty_config())
    assert not report["accepted"], "an overlay that mislabels held-out entities must be rejected"
    assert "perception.role_accuracy" in report["regressions"]
    v = reg.propose(cand, [], "harmful by construction")
    assert v["status"] == "rejected"
    assert reg.active()["id"] == "v0" and reg.active()["config"] == empty_config()
    assert [a["action"] for a in reg.audit()] == ["propose", "reject"]
    assert reg.get("v1")["gate"]["metrics"]["perception.role_accuracy"]["delta"] < 0


def test_registry_accept_rollback_diff_and_persistence(tmp_path):
    d = str(tmp_path / "reg")
    reg = ModelRegistry(d, clock=Clock())
    assert reg.active()["id"] == "v0" and reg.active()["config"] == empty_config()
    c1 = {"lexicon_overlay": {"flumox": "regulator"}, "priors": []}
    v1 = reg.propose(c1, ["ev-1", "ev-2"], "first", gate_fn=accept_gate)
    c2 = {"lexicon_overlay": {"flumox": "regulator", "zindle": "buffer"}, "priors": []}
    v2 = reg.propose(c2, [], "second", gate_fn=accept_gate)
    assert (v1["id"], v2["id"], v2["parent"]) == ("v1", "v2", "v1")
    assert reg.active()["id"] == "v2" and reg.get("v1")["status"] == "superseded"
    assert reg.propose(c2, [], "same", gate_fn=accept_gate) is None
    back = reg.rollback(reason="bad day")
    assert back["id"] == "v1" and reg.active()["config"] == c1
    assert reg.get("v2")["status"] == "rolled_back"
    assert reg.audit()[-1]["action"] == "rollback" and reg.audit()[-1]["reason"] == "bad day"
    assert reg.diff("v1", "v2")["lexicon_added"] == {"zindle": "buffer"}
    reg.activate("v2", "retry")
    assert reg.active()["id"] == "v2"
    reg.rollback(to="v0", reason="reset")
    assert reg.active()["config"] == empty_config()
    with pytest.raises(ValueError):
        reg.rollback()  # v0 has no parent
    again = ModelRegistry(d)
    assert again.active()["id"] == "v0" and [v["id"] for v in again.history()] == ["v0", "v1", "v2"]
    assert len(again.audit()) == len(reg.audit()) and again.audit()[0]["action"] == "propose"
    assert not [f for f in os.listdir(os.path.join(d, "versions")) if f.endswith(".tmp")]


def test_registry_end_to_end_with_real_gate(tmp_path):
    log = EvidenceLog(clock=Clock())
    corr(log, "flumox", "regulator", "r1")
    corr(log, "flumox", "regulator", "r2")
    reg = ModelRegistry(str(tmp_path / "reg"), clock=Clock())
    cand, report, used = build_candidate(log, reg.active()["config"])
    v = reg.propose(cand, used, "loop run")
    assert v["status"] == "active" and v["gate"]["accepted"] and not v["gate"]["sensitive"]
    assert reg.active()["config"]["lexicon_overlay"] == {"flumox": "regulator"}


def test_registry_rejects_invalid_config_and_version_id(tmp_path):
    reg = ModelRegistry(str(tmp_path / "reg"))
    with pytest.raises(ValueError):
        reg.propose({"lexicon_overlay": {"x y": "wizard"}, "priors": []}, [], "bad", gate_fn=accept_gate)
    with pytest.raises(ValueError):
        reg.propose({"lexicon_overlay": {}, "priors": [{"key": "a", "conditions": {}, "n": 1, "value": 0.01}]}, [], "bad",
                    gate_fn=accept_gate)
    with pytest.raises(ValueError):
        reg.get("../etc")


# ---------------------------------------------------------------- overlay

TEXT = "The flumox feeds the pump. The pump moves fluid."


def _roles(res):
    return {n.label: (n.role, n.attrs.get("role_source")) for n in res.problem.graph.nodes}


def test_overlay_gives_learned_role_source_and_no_overlay_is_unchanged():
    plain = perceive_text(TEXT, "t")
    assert perceive_text(TEXT, "t", overlay=None).problem.to_dict() == plain.problem.to_dict()
    assert perceive_text(TEXT, "t", overlay={}).problem.to_dict() == plain.problem.to_dict()
    res = perceive_text(TEXT, "t", overlay={"Flumoxes": "regulator"}, overlay_version="v7")
    assert _roles(res)["flumox"] == ("regulator", "learned")
    assert any("v7" in i["statement"] and i.get("source") == "learned" for i in res.inferences)
    assert next(n for n in res.problem.graph.nodes if n.label == "flumox").confidence == 0.6
    # the overlay does not leak into the next call
    assert _roles(perceive_text(TEXT, "t")) == _roles(plain)


def test_overlay_does_not_override_direct_lexicon_hits():
    res = perceive_text(TEXT, "t", overlay={"pump": "sink", "fluid": "sink"})
    assert _roles(res)["pump"] == ("actuator", None)


def test_overlay_matches_phrase_head():
    res = perceive_text("The blue flumox feeds the pump.", "t", overlay={"flumox": "buffer"})
    assert [n.role for n in res.problem.graph.nodes if "flumox" in n.label] == ["buffer"]


def test_perception_with_empty_active_config_matches_published_numbers():
    m, _ = evaluate(overlay=empty_config()["lexicon_overlay"] or None)
    for k, v in PUBLISHED.items():
        assert round(m[k], 3) == v
    metrics = compute_metrics(empty_config())
    assert round(metrics["perception.role_accuracy"], 3) == 0.404
    assert metrics["heldout.mrr_strong"] == 0.975 and metrics["tuning.mrr_primary"] == 0.9286


# ---------------------------------------------------------------- pipeline

def test_investigate_reports_learned_version_and_overlay():
    from knowledge_base import load_systems, load_domains
    from intelligence.domain_engine import DomainRegistry
    from intelligence.pipeline import investigate
    systems, domains = load_systems(), DomainRegistry(load_domains())
    text = "The flumox feeds the pump. The pump moves fluid to the tank. The controller reads the sensor."
    plain = investigate(text, systems, domains, title="t", top_n=3)
    assert plain["learned_version"] is None
    learned = {"id": "v3", "config": {"lexicon_overlay": {"flumox": "regulator"}, "priors": []}}
    out = investigate(text, systems, domains, title="t", top_n=3, learned=learned)
    assert out["learned_version"] == "v3"
    assert _roles(out["perception"])["flumox"] == ("regulator", "learned")


def test_investigate_priors_apply_only_inside_conditions():
    from knowledge_base import load_systems, load_domains
    from intelligence.domain_engine import DomainRegistry
    from intelligence.pipeline import investigate
    systems, domains = load_systems(), DomainRegistry(load_domains())
    text = "The pump moves fluid to the tank. The controller reads the sensor and adjusts the valve."
    base = investigate(text, systems, domains, title="t", top_n=5, query_domain="brewing")
    types = [c.concept_type for c in base["concepts"]]
    last = types[-1]
    prior = {"key": last, "conditions": {"query_domain": "brewing"}, "n": 9, "accepted": 9, "rejected": 0, "value": 0.1}
    inside = investigate(text, systems, domains, title="t", top_n=5, query_domain="brewing",
                         learned={"id": "v1", "config": {"lexicon_overlay": {}, "priors": [prior]}})
    outside = investigate(text, systems, domains, title="t", top_n=5, query_domain="cooking",
                          learned={"id": "v1", "config": {"lexicon_overlay": {}, "priors": [prior]}})
    out_plain = investigate(text, systems, domains, title="t", top_n=5, query_domain="cooking")
    assert [c.id for c in outside["concepts"]] == [c.id for c in out_plain["concepts"]]
    assert inside["learned_version"] == "v1"


def test_determinism():
    def build():
        log = EvidenceLog(clock=Clock())
        for run in ("r1", "r2", "r3"):
            corr(log, "flumox", "regulator", run)
            log.append("hypothesis_feedback", {"concept_type": "feedback", "decision": "saved", "conditions": {"query_domain": "a"}})
        return build_candidate(log, empty_config())
    a, b = build(), build()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert json.dumps(run_gate(a[0], empty_config()), sort_keys=True) == json.dumps(run_gate(a[0], empty_config()), sort_keys=True)


# ---------------------------------------------------------------- review fixes

def test_two_evidence_logs_on_one_file_keep_ids_unique_and_visible(tmp_path):
    path = str(tmp_path / "evidence.jsonl")
    a, b = EvidenceLog(path, clock=Clock()), EvidenceLog(path, clock=Clock())
    e1 = corr(a, "flumox", "regulator", "r1")
    e2 = corr(b, "flumox", "regulator", "r2")
    e3 = corr(a, "zorb", "regulator", "r3")
    assert [e1["id"], e2["id"], e3["id"]] == ["ev-1", "ev-2", "ev-3"]
    assert len(a.events) == len(b.events) == 3


def test_registry_finds_last_rejected_candidate_for_same_evidence(tmp_path):
    reg = ModelRegistry(str(tmp_path / "reg"), clock=Clock())
    cfg = {"lexicon_overlay": {"flumox": "regulator"}, "priors": []}

    def reject(c, a, cv=None, av=None):
        return {"accepted": False, "sensitive": True, "regressions": ["x"], "note": "stub reject", "metrics": {}}

    v = reg.propose(cfg, ["ev-1", "ev-2"], gate_fn=reject)
    assert v["status"] == "rejected"
    assert reg.last_rejected_for(cfg, ["ev-2", "ev-1"])["id"] == v["id"]
    assert reg.last_rejected_for(cfg, ["ev-1", "ev-2", "ev-3"]) is None
