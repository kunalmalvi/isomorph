import json

import pytest

from ai_providers import CompletionResult, Provider, ProviderTransportError
from core.errors import Conflict, NotFound, ValidationFailed
from services.knowledge import default_knowledge
from services.orchestrator import STAGES, Orchestrator, validate_config
from services.run_store import InMemoryRunStore, JsonFileRunStore
from workers.job_runner import JobRunner

TEXT = ("A rolling mill reduces the thickness of a metal strip between two rollers. The roll force must not exceed "
        "800 kN. The strip thickness varies and must stay within tolerance. A sensor measures the exit thickness.")


@pytest.fixture(scope="module")
def kb():
    return default_knowledge()


@pytest.fixture
def orch(kb):
    return Orchestrator(InMemoryRunStore(), kb)


def test_full_run_all_stages_inspectable(orch):
    r = orch.run(orch.create_run(text=TEXT, run_id="r1").id)
    assert r.status == "done" and list(r.stages) == list(STAGES)
    for name in STAGES:
        st = orch.get_stage("r1", name)
        assert st.status == "done" and st.version == 1 and st.output and st.started_at is not None
    assert orch.get_stage("r1", "perception").source == "computation"
    assert orch.get_stage("r1", "structural_matching").output["matches"]
    assert orch.get_stage("r1", "validation").output["validations"]
    json.dumps(r.to_dict())  # fully JSON serialisable


def test_deterministic_across_runs(orch):
    a = orch.run(orch.create_run(text=TEXT).id)
    b = orch.run(orch.create_run(text=TEXT).id)
    for n in STAGES:
        assert a.stages[n].output == b.stages[n].output


def test_edit_marks_downstream_stale_and_rerun_recomputes(orch):
    orch.run(orch.create_run(text=TEXT, run_id="e1").id)
    before_h = orch.get_stage("e1", "hypothesis_generation").output
    cands = orch.get_stage("e1", "cross_domain_search").output
    edited = json.loads(json.dumps(cands))
    edited["candidates"] = edited["candidates"][:3]
    run = orch.edit_stage("e1", "cross_domain_search", edited)
    assert run.stages["cross_domain_search"].source == "user" and run.stages["cross_domain_search"].version == 2
    assert run.stages["perception"].status == "done"
    assert all(run.stages[n].status == "stale" for n in STAGES[4:])
    run = orch.rerun_downstream("e1", "cross_domain_search")
    assert run.status == "done"
    assert run.stages["cross_domain_search"].source == "user"  # edit preserved
    ids = {m["system_id"] for m in run.stages["structural_matching"].output["matches"]}
    assert ids <= {c["system_id"] for c in edited["candidates"]}
    assert run.stages["structural_matching"].version == 2 and run.stages["perception"].version == 1
    assert before_h is not None


def test_edit_perception_changes_everything_downstream(orch):
    orch.run(orch.create_run(text=TEXT, run_id="e2").id)
    out = json.loads(json.dumps(orch.get_stage("e2", "perception").output))
    out["problem"]["goal"] = "edited goal"
    orch.edit_stage("e2", "perception", out)
    run = orch.rerun_downstream("e2", "perception")
    assert run.stages["structural_extraction"].version == 2
    assert run.stages["perception"].output["problem"]["goal"] == "edited goal"


def test_rerun_from_discards_edit(orch):
    orch.run(orch.create_run(text=TEXT, run_id="e3").id)
    out = json.loads(json.dumps(orch.get_stage("e3", "cross_domain_search").output))
    out["candidates"] = out["candidates"][:1]
    orch.edit_stage("e3", "cross_domain_search", out)
    run = orch.rerun_from("e3", "cross_domain_search")
    assert run.stages["cross_domain_search"].source == "computation"
    assert len(run.stages["cross_domain_search"].output["candidates"]) > 1


def test_invalid_edit_rejected_and_state_unchanged(orch):
    orch.run(orch.create_run(text=TEXT, run_id="e4").id)
    with pytest.raises(ValidationFailed):
        orch.edit_stage("e4", "perception", {"problem": {"id": "x", "graph": {"nodes": [{"id": "a"}], "edges": [{"bad": 1}]}}})
    with pytest.raises(ValidationFailed):
        orch.edit_stage("e4", "mechanism_mapping", {"mappings": [{"mapping": {}}]})
    with pytest.raises(NotFound):
        orch.edit_stage("e4", "nope", {})
    assert orch.get_stage("e4", "perception").version == 1


def test_cannot_edit_stage_without_output(orch):
    r = orch.create_run(text=TEXT, run_id="e5")
    with pytest.raises(Conflict):
        orch.edit_stage("e5", "perception", {})


def test_config_validation():
    for bad in ({"weights": {"functional": 50}}, {"top_k": 0}, {"threshold": -1}, {"nope": 1}, {"seeds": 0}):
        with pytest.raises(ValidationFailed):
            validate_config(bad)
    assert validate_config({"weights": {"functional": 20, "relationship": 30}})["weights"]["relationship"] == 30


def test_create_run_input_validation(orch):
    with pytest.raises(ValidationFailed):
        orch.create_run()
    with pytest.raises(ValidationFailed):
        orch.create_run(text="a", problem={"id": "p"})
    with pytest.raises(ValidationFailed):
        orch.create_run(problem={"graph": 3})


def test_structured_problem_input_skips_perception(orch):
    spec = {"id": "p1", "title": "Pump", "statement": "A pump moves fluid through a pipe into a tank. Pressure must not exceed a limit.",
            "graph": {"nodes": [{"id": "pump", "label": "pump", "role": "source"}, {"id": "tank", "label": "tank", "role": "store"}],
                      "edges": [{"id": "e1", "source": "pump", "target": "tank", "relation": "flows_to"}]}}
    r = orch.run(orch.create_run(problem=spec).id)
    assert r.stages["perception"].source == "user"
    assert r.status in ("done", "failed")


def test_weights_change_scores(orch):
    a = orch.run(orch.create_run(text=TEXT).id).stages["structural_matching"].output
    b = orch.run(orch.create_run(text=TEXT, config={"weights": {"functional": 5, "relationship": 5, "topological": 5,
                                                                "dynamic": 5, "constraint": 5, "semantic": 75}}).id)
    assert a["weights"]["functional"] == 25 and b.stages["structural_matching"].output["weights"]["semantic"] == 75


class FailingProvider(Provider):
    name = "openai"

    def complete(self, req):
        raise ProviderTransportError("boom")


class BadShapeProvider(Provider):
    name = "openai"

    def complete(self, req):
        return CompletionResult("{}", {"problem": {"id": "x", "graph": {"nodes": [{"id": "a", "role": "invented_role"}], "edges": []}}},
                                "openai", "m", "ai_hypothesis")


class GoodRemoteProvider(Provider):
    name = "openai"

    def complete(self, req):
        d = {"problem": {"id": "p", "title": "t", "statement": TEXT, "graph": {"nodes": [{"id": "mill", "label": "mill", "role": "converter"}], "edges": []}}}
        return CompletionResult("{}", d, "openai", "m", "ai_hypothesis", {"prompt_tokens": 1})


def test_provider_failure_fails_stage_without_fabricating(kb):
    o = Orchestrator(InMemoryRunStore(), kb, provider=FailingProvider())
    r = o.run(o.create_run(text=TEXT, config={"provider": "openai"}).id)
    assert r.status == "failed" and "perception" in r.error
    assert r.stages["perception"].status == "failed" and r.stages["perception"].output is None
    assert all(r.stages[n].status == "pending" for n in STAGES[1:])


def test_ai_output_is_labelled_ai_hypothesis(kb):
    o = Orchestrator(InMemoryRunStore(), kb, provider=GoodRemoteProvider())
    r = o.run(o.create_run(text=TEXT, config={"provider": "openai"}).id)
    st = r.stages["perception"]
    assert st.source == "ai_hypothesis"
    assert all(n["provenance"] == "ai_hypothesis" for n in st.output["problem"]["graph"]["nodes"])


def test_unavailable_provider_rejected(kb):
    o = Orchestrator(InMemoryRunStore(), kb)
    r = o.run(o.create_run(text=TEXT, config={"provider": "gemini"}).id)
    assert r.stages["perception"].status == "failed"


def test_json_file_store_persists_progress(kb, tmp_path):
    o = Orchestrator(JsonFileRunStore(str(tmp_path)), kb)
    o.run(o.create_run(text=TEXT, run_id="persist-1").id)
    o2 = Orchestrator(JsonFileRunStore(str(tmp_path)), kb)  # new process view
    assert o2.get_stage("persist-1", "validation").status == "done"
    with pytest.raises(ValueError):
        JsonFileRunStore(str(tmp_path)).get("../evil")


def test_job_runner_async_and_progress_persisted(kb):
    o = Orchestrator(InMemoryRunStore(), kb)
    o.create_run(text=TEXT, run_id="j1")
    jr = JobRunner(o, max_workers=1)
    jr.submit("j1")
    jr.wait("j1", 60)
    assert o.store.get("j1").status == "done"
    assert o.store.get("j1").progress()["completed"] == len(STAGES)
    jr.shutdown()


def test_job_cancel_between_stages(kb):
    o = Orchestrator(InMemoryRunStore(), kb)
    o.create_run(text=TEXT, run_id="j2")
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    r = o.run("j2", cancel)
    assert r.status == "cancelled"
    done = [n for n in STAGES if r.stages[n].status == "done"]
    assert done == list(STAGES[:3])


def test_job_runner_records_unexpected_exception(kb):
    o = Orchestrator(InMemoryRunStore(), kb)
    o.create_run(text=TEXT, run_id="j3")
    jr = JobRunner(o, synchronous=True)

    def boom(should_cancel):
        raise RuntimeError("kaput")

    jr.submit("j3", boom)
    rec = o.store.get("j3")
    assert rec.status == "failed" and "kaput" in rec.error


def test_job_runner_rejects_duplicate_submission(kb):
    import threading
    o = Orchestrator(InMemoryRunStore(), kb)
    o.create_run(text=TEXT, run_id="j4")
    gate = threading.Event()
    jr = JobRunner(o, max_workers=1)
    jr.submit("j4", lambda c: gate.wait(5))
    with pytest.raises(RuntimeError):
        jr.submit("j4")
    gate.set()
    jr.wait("j4", 10)
    jr.shutdown()


def test_job_cancel_flag(kb):
    o = Orchestrator(InMemoryRunStore(), kb)
    o.create_run(text=TEXT, run_id="j5")
    jr = JobRunner(o, synchronous=True)
    assert jr.cancel("missing") is False
