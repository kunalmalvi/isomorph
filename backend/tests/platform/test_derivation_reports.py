import json

import pytest

from core.errors import ValidationFailed
from intelligence.schemas import SchemaError
from services.derivation import concepts_for_mapping, hypothesis_for_concept, run_arms, validate_hypothesis
from services.knowledge import default_knowledge
from services.orchestrator import Orchestrator
from services.problem_builder import build_problem
from services.reports import build_report, report_markdown
from services.run_store import InMemoryRunStore
from tests.platform.test_orchestrator import TEXT


@pytest.fixture(scope="module")
def run():
    o = Orchestrator(InMemoryRunStore(), default_knowledge())
    return o.run(o.create_run(text=TEXT).id)


def test_stepwise_derivation_matches_pipeline(run):
    kb = default_knowledge()
    problem = run.stages["perception"].output["problem"]
    ext = run.stages["structural_extraction"].output
    m = run.stages["mechanism_mapping"].output["mappings"][0]
    concepts = concepts_for_mapping(kb, None, problem, ext, m["system_id"], m["mapping"], m["score"])
    assert concepts and all(c.relies_on for c in concepts)
    h = hypothesis_for_concept(concepts[0].to_dict(), problem)
    assert h["status"] == "untested" and h["provenance"] == "computation"
    with pytest.raises(ValidationFailed):
        concepts_for_mapping(kb, None, problem, ext, "no_such_system", m["mapping"], 1.0)


def test_run_arms_deterministic_and_rejects_missing_model(run):
    spec = next((h["experiment"] for h in run.stages["hypothesis_generation"].output["hypotheses"] if h["experiment"]), None)
    assert spec is not None
    a, b = run_arms(spec, 3), run_arms(spec, 3)
    assert a == b and a["config_hash"] == run_arms(spec, 3)["config_hash"]
    assert run_arms(spec, 4)["config_hash"] != a["config_hash"]
    with pytest.raises(ValidationFailed):
        run_arms(None, 1)
    with pytest.raises(ValidationFailed):
        run_arms({"kind": "nope", "baseline": {}, "proposed": {}}, 1)


def test_validate_hypothesis_untested_without_experiment(run):
    hs = run.stages["hypothesis_generation"].output["hypotheses"]
    no_exp = next((h for h in hs if not h["experiment"]), None)
    if no_exp:
        assert validate_hypothesis(no_exp)["outcome"] == "untested"
    with_exp = next(h for h in hs if h["experiment"])
    assert validate_hypothesis(with_exp, 5)["outcome"] in ("supported", "refuted", "inconclusive")


def test_report_has_provenance_disclaimer_and_marks_missing_stages(run):
    rep = build_report("T", run.to_dict())
    md = report_markdown(rep)
    assert "not real-world evidence" in md and "provenance:" in md and md.startswith("# T")
    partial = run.to_dict()
    for s in partial["stages"]:
        if s["name"] in ("transformation", "hypothesis_generation", "validation"):
            s["status"], s["output"] = "pending", None
    rep2 = build_report("P", partial)
    assert rep2["concepts"] == [] and rep2["hypotheses"] == []
    assert "- none" in report_markdown(rep2)
    json.dumps(rep)


def test_problem_builder():
    ents = [{"id": "a", "name": "Pump", "kind": "source"}, {"id": "b", "name": "Tank", "kind": "buffer"}, {"id": "c", "name": "Thing", "kind": "widget"}]
    rels = [{"source_entity_id": "a", "target_entity_id": "b", "relation_type": "flows_to", "weight": 2}]
    p = build_problem("p", "T", "S", None, ents, rels, [{"id": "k", "description": "d", "kind": "hard"}],
                      [{"name": "x", "min_value": 0, "max_value": 5, "value": 2}])
    assert [n.role for n in p.graph.nodes] == ["source", "buffer", None]
    assert p.graph.edges[0].weight == 2 and p.values() == {"x": 2}
    with pytest.raises(SchemaError):
        build_problem("p", "T", "S", "", ents, [dict(rels[0], relation_type="bogus")], [], [])
    with pytest.raises(SchemaError):
        build_problem("p", "T", "S", "", ents, [dict(rels[0], target_entity_id="zzz")], [], [])
    with pytest.raises(SchemaError):
        build_problem("p", "T", "S", "", [dict(ents[0], provenance="made_up")], [], [], [])
