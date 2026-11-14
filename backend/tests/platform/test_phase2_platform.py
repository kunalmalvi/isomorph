"""Stdlib tests for phase 2 platform logic: annotations, restart recovery, proxy aware client key, bounded SSE,
seed loading and an end to end edit/rerun/validate flow. The FastAPI glue that exposes these is tested in test_api.py."""
import json

import pytest

from core.config import ConfigError, load_settings
from core.errors import ValidationFailed
from core.rate_limit import client_key
from core.sse import MAX_INTERVAL, MIN_INTERVAL, parse_last_event_id, progress_stream
from database.seed import MemorySink, apply_plan, plan_seed
from services.annotations import InMemoryAnnotationStore, JsonFileAnnotationStore
from services.knowledge import default_knowledge
from services.orchestrator import STAGES, Orchestrator
from services.run_store import InMemoryRunStore, JsonFileRunStore
from tests.platform.test_orchestrator import TEXT
from workers.recovery import INTERRUPTED, recover_interrupted_runs


# ------------------------------------------------------------------ (a) annotations
@pytest.mark.parametrize("make", [lambda tmp: InMemoryAnnotationStore(), lambda tmp: JsonFileAnnotationStore(str(tmp))])
def test_annotations_roundtrip_and_validation(make, tmp_path):
    st = make(tmp_path)
    assert st.list("r1") == {}
    rec = st.set("r1", "H1-x", "promoted", "worth testing")
    assert rec["provenance"] == "user" and st.list("r1")["H1-x"]["decision"] == "promoted"
    st.set("r1", "H1-x", "rejected", "changed my mind")
    assert st.list("r1")["H1-x"]["decision"] == "rejected" and "r2" not in st.list("r2") and st.list("r2") == {}
    for bad in (("H1", "maybe", ""), ("", "saved", ""), ("a b", "saved", ""), ("H1", "saved", "x" * 5001)):
        with pytest.raises(ValidationFailed):
            st.set("r1", *bad)
    assert st.delete("r1", "H1-x") and not st.delete("r1", "H1-x") and st.list("r1") == {}


def test_annotations_survive_restart_and_reject_bad_run_ids(tmp_path):
    JsonFileAnnotationStore(str(tmp_path)).set("run-1", "H1", "saved", "n")
    assert JsonFileAnnotationStore(str(tmp_path)).list("run-1")["H1"]["note"] == "n"
    with pytest.raises(ValueError):
        JsonFileAnnotationStore(str(tmp_path)).list("../etc")


def test_annotations_do_not_touch_hypothesis_output():
    o = Orchestrator(InMemoryRunStore(), default_knowledge())
    run = o.run(o.create_run(text=TEXT, run_id="a1").id)
    hyps = run.stages["hypothesis_generation"].output["hypotheses"]
    InMemoryAnnotationStore().set("a1", hyps[0]["id"], "rejected", "no")
    assert o.get_stage("a1", "hypothesis_generation").output["hypotheses"] == hyps


# ------------------------------------------------------------------ (b) restart recovery
def _interrupted(store):
    o = Orchestrator(store, default_knowledge())
    done = o.run(o.create_run(text=TEXT, run_id="done1").id)
    o.create_run(text=TEXT, run_id="queued1")
    mid = o.create_run(text=TEXT, run_id="mid1")
    mid.status = "running"
    mid.stages["perception"].status = "running"
    store.save(mid)
    return o, done


@pytest.mark.parametrize("kind", ["memory", "file"])
def test_recovery_marks_active_runs_failed(kind, tmp_path):
    store = InMemoryRunStore() if kind == "memory" else JsonFileRunStore(str(tmp_path))
    o, _ = _interrupted(store)
    assert store.active_run_ids() == ["mid1", "queued1"]
    assert recover_interrupted_runs(store) == ["mid1", "queued1"]
    for rid in ("mid1", "queued1"):
        r = store.get(rid)
        assert r.status == "failed" and r.error == INTERRUPTED == "interrupted by restart"
    assert store.get("mid1").stages["perception"].status == "failed"
    assert store.get("done1").status == "done" and store.get("done1").error is None
    assert recover_interrupted_runs(store) == []  # idempotent
    # a recovered run can be resumed: failed stages rerun, nothing is fabricated
    assert o.run("mid1").status == "done"


def test_recovery_keeps_completed_stage_outputs():
    store = InMemoryRunStore()
    o = Orchestrator(store, default_knowledge())
    run = o.run(o.create_run(text=TEXT, run_id="k1").id)
    out = run.stages["perception"].output
    run.status = "running"
    run.stages["structural_matching"].status = "running"
    store.save(run)
    recover_interrupted_runs(store)
    r = store.get("k1")
    assert r.stages["perception"].output == out and r.stages["perception"].status == "done"


# ------------------------------------------------------------------ (c) trusted proxies
def test_forwarded_for_ignored_without_trusted_proxy():
    assert client_key("203.0.113.9", "1.2.3.4", ()) == "203.0.113.9"
    assert client_key("203.0.113.9", "1.2.3.4", ("10.0.0.0/8",)) == "203.0.113.9"  # peer not trusted: spoofing ignored


def test_forwarded_for_honored_from_trusted_proxy():
    assert client_key("10.0.0.5", "198.51.100.7", ("10.0.0.5",)) == "198.51.100.7"
    assert client_key("10.0.0.5", "6.6.6.6, 198.51.100.7", ("10.0.0.0/8",)) == "198.51.100.7"  # client supplied prefix is not trusted
    assert client_key("10.0.0.5", "198.51.100.7, 10.0.0.9", ("10.0.0.0/8",)) == "198.51.100.7"  # chain of trusted proxies
    assert client_key("10.0.0.5", "10.0.0.9", ("10.0.0.0/8",)) == "10.0.0.5"  # only proxies listed
    assert client_key("10.0.0.5", "garbage", ("10.0.0.0/8",)) == "10.0.0.5"
    assert client_key("10.0.0.5", None, ("10.0.0.0/8",)) == "10.0.0.5"
    assert client_key("::1", "2001:db8::1", ("::1",)) == "2001:db8::1"
    assert client_key(None, "1.2.3.4", ("10.0.0.0/8",)) == "unknown"


def test_trusted_proxies_setting():
    assert load_settings({}).trusted_proxies == ()
    assert load_settings({"TRUSTED_PROXIES": "10.0.0.0/8, 192.168.1.1"}).trusted_proxies == ("10.0.0.0/8", "192.168.1.1")
    with pytest.raises(ConfigError):
        load_settings({"TRUSTED_PROXIES": "not-an-ip"})
    with pytest.raises(ConfigError):
        load_settings({"SSE_MAX_SECONDS": "0"})


# ------------------------------------------------------------------ (d) SSE
def test_sse_retry_hint_and_bounded_connection():
    out = list(progress_stream(lambda: {"status": "running"}, sleep=lambda s: None, max_seconds=3, clock=iter([0, 1, 2, 3, 4]).__next__))
    assert out[0] == "retry: 2000\n\n"
    assert "event: timeout" in out[-1] and '"reconnect":true' in out[-1]


def test_sse_interval_is_clamped_and_polling_is_bounded():
    sleeps = []
    t = [0.0]

    def sleep(s):
        sleeps.append(s)
        t[0] += s
    list(progress_stream(lambda: {"status": "running"}, interval=0.0, max_seconds=2, sleep=sleep, clock=lambda: t[0]))
    assert set(sleeps) == {MIN_INTERVAL} and len(sleeps) == 8
    sleeps.clear()
    t[0] = 0.0
    list(progress_stream(lambda: {"status": "running"}, interval=999, max_seconds=12, sleep=sleep, clock=lambda: t[0]))
    assert set(sleeps) == {MAX_INTERVAL}


def test_sse_reconnect_continues_ids_and_resends_state():
    out = list(progress_stream(lambda: {"status": "done", "n": 2}, sleep=lambda s: None, last_event_id=7))
    assert out[1].startswith("id: 8\n") and out[2].startswith("id: 9\n") and "event: end" in out[2]
    assert parse_last_event_id("7") == 7
    assert [parse_last_event_id(x) for x in (None, "", "abc", "-3", "9" * 20)] == [0, 0, 0, 0, 0]


def test_default_sse_duration_is_short():
    assert load_settings({}).sse_max_seconds == 30.0


# ------------------------------------------------------------------ (e) seeding
def test_seed_plan_covers_data_and_is_deterministic():
    p1, p2 = plan_seed(), plan_seed()
    assert p1 == p2
    kb = default_knowledge()
    assert len(p1["systems"]) == len(kb.systems)
    assert len(p1["mechanisms"]) == len(kb.mechanism_ids)
    assert {d["name"] for d in p1["domains"]} >= {s["domain"] for s in p1["systems"]}
    assert all(s["source"] for s in p1["systems"]) and all(m["function_tag"] for m in p1["mechanisms"])


def test_seed_is_idempotent():
    plan, sink = plan_seed(), MemorySink()
    first = apply_plan(plan, sink)
    assert first["domain_systems"] == len(plan["systems"]) and first["system_entities"] > 0 and first["mechanisms"] > 0
    snapshot = {t: len(r) for t, r in sink.rows.items()}
    second = apply_plan(plan, sink)
    assert set(second.values()) == {0}
    assert {t: len(r) for t, r in sink.rows.items()} == snapshot


def test_seed_relationships_reference_existing_entities():
    sink = MemorySink()
    apply_plan(plan_seed(), sink)
    ids = {r["id"] for r in sink.rows["system_entities"].values()}
    for r in sink.rows["system_relationships"].values():
        assert r["source_entity_id"] in ids and r["target_entity_id"] in ids


def test_seed_dry_run_cli(capsys):
    from database.seed import main
    assert main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["domain_systems"] > 0


# ------------------------------------------------------------------ (f) end to end
def test_end_to_end_edit_hypothesis_stage_rerun_downstream_validate():
    store = InMemoryRunStore()
    o = Orchestrator(store, default_knowledge())
    run = o.run(o.create_run(text=TEXT, run_id="e2e").id)
    assert run.status == "done"
    hyp_stage = "hypothesis_generation"
    old = o.get_stage("e2e", hyp_stage).output
    before_val = o.get_stage("e2e", "validation").output
    assert before_val["validations"]

    edited = json.loads(json.dumps(old))
    edited["hypotheses"] = edited["hypotheses"][:1]
    edited["hypotheses"][0]["statement"] = "Edited by the user: adding a buffer reduces thickness variance."
    r = o.edit_stage("e2e", hyp_stage, edited)
    # stale flags: edited stage stays done with source user, only later stages go stale
    assert r.stages[hyp_stage].status == "done" and r.stages[hyp_stage].source == "user"
    assert r.stages[hyp_stage].version == 2
    assert [r.stages[n].status for n in STAGES[:STAGES.index(hyp_stage) + 1]] == ["done"] * (STAGES.index(hyp_stage) + 1)
    assert r.stages["validation"].status == "stale"
    assert r.stages["validation"].output == before_val  # old output is kept but flagged, not silently dropped

    r = o.rerun_downstream("e2e", hyp_stage)
    assert r.status == "done" and all(s.status == "done" for s in r.stages.values())
    assert r.stages[hyp_stage].output == edited and r.stages[hyp_stage].source == "user"  # the edit was not recomputed away
    val = r.stages["validation"]
    assert val.source == "computation" and val.version == 2
    assert len(val.output["validations"]) == 1
    assert val.output["hypotheses"][0]["statement"].startswith("Edited by the user")
    assert val.output["validations"][0]["outcome"] in ("supported", "refuted", "inconclusive")
    assert "not real world evidence" in val.output["note"]
    for h in val.output["hypotheses"]:  # edited hypotheses are never presented as source facts
        assert h["provenance"] in ("computation", "user", "ai_hypothesis")


def test_joined_forwarded_for_lines_cannot_hide_the_proxy_hop():
    # Two header lines: the client sent "6.6.6.6", the proxy appended "198.51.100.7". Joined with a comma they walk like one line.
    assert client_key("10.0.0.5", ",".join(["6.6.6.6", "198.51.100.7"]), ("10.0.0.0/8",)) == "198.51.100.7"


def test_seed_keeps_every_source_and_links_the_first(caplog, tmp_path):
    import shutil
    from database.seed import DEFAULT_DATA_DIR
    data = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIR, data)
    for fp in (data / "seed_knowledge").glob("*.json"):
        doc = json.loads(fp.read_text())
        doc["systems"][0]["sources"] = [{"citation": "First 2001", "kind": "paper"}, {"citation": "Second 2002", "kind": "book"}]
        fp.write_text(json.dumps(doc))
        break
    with caplog.at_level("INFO", logger="database.seed"):
        plan = plan_seed(str(data))
    cites = {s["citation"] for s in plan["sources"]}
    assert {"First 2001", "Second 2002"} <= cites
    assert any("linking the first only" in r.message for r in caplog.records)
