"""The self-improving loop wired into the app: HTTP API, CLI, orchestrator, annotations and rollback."""
import json
import os

from isomorph_app import cli
from tests.platform.test_server import start, stop

TEXT = "The pump feeds the zorblat. The zorblat supplies the tank. The goal is to maximise flow. Flow must not exceed 5 kg."
TEXT2 = "A valve opens into the zorblat. The zorblat drives the turbine. The goal is to maximise output."
PLAIN = "A pump moves fluid. The pipe constrains the fluid flow. Friction dissipates energy at the wall. The goal is to minimise energy loss."


def node(run, label):
    out = next(s for s in run["stages"] if s["name"] == "perception")["output"]
    return next(n for n in out["problem"]["graph"]["nodes"] if n["label"] == label), out


def discover(c, text):
    st, r = c.call("POST", "/api/v1/discoveries", {"text": text})
    assert st == 202
    c.wait_done(r["id"])
    return r["id"], c.call("GET", f"/api/v1/discoveries/{r['id']}?outputs=1")[1]


def test_end_to_end_loop_over_http_and_rollback(tmp_path):
    app, server, c = start(tmp_path)
    try:
        st, s0 = c.call("GET", "/api/v1/learning")
        assert st == 200 and s0["active"]["id"] == "v0" and s0["evidence"]["total"] == 0
        assert "cannot detect harm" in s0["limits"]

        r1, run1 = discover(c, TEXT)
        z, out1 = node(run1, "zorblat")
        assert z["role"] is None  # unknown before learning
        assert out1["learned_version"] == "v0"
        r2, run2 = discover(c, TEXT2)

        # one correction is not enough
        st, res = c.call("POST", "/api/v1/learning/corrections", {"run_id": r1, "term": "Zorblat", "role": "transformer"})
        assert st == 201 and res["term"] == "zorblat" and "2 distinct runs" in res["clarification"]
        st, cyc = c.call("POST", "/api/v1/learning/cycle", {})
        assert st == 200 and cyc["changed"] is False and "Nothing changed" in cyc["message"]

        # a second correction from another run
        c.call("POST", "/api/v1/learning/corrections", {"run_id": r2, "term": "zorblat", "role": "transformer"})
        st, cyc = c.call("POST", "/api/v1/learning/cycle", {})
        assert cyc["accepted"] is True and cyc["after"] == "v1" and cyc["before"] == "v0"
        assert set(cyc["metrics"]) >= {"perception.role_accuracy", "heldout.mrr_strong", "tuning.mrr_primary"}
        assert all(r["delta"] >= -1e-9 for r in cyc["metrics"].values())
        assert cyc["sensitive"] is False  # honest: frozen sets do not contain this word

        # the next run uses the learned word and states the version
        r3, run3 = discover(c, TEXT)
        z, out3 = node(run3, "zorblat")
        assert z["role"] == "transformer" and z["attrs"]["role_source"] == "learned"
        assert out3["learned_version"] == "v1"
        assert "learned config version v1" in json.dumps(out3["inferences"])
        st, rep = c.call("GET", f"/api/v1/discoveries/{r3}/report?format=md")
        assert b"learned config version v1" in rep

        st, vs = c.call("GET", "/api/v1/learning/versions")
        assert [v["id"] for v in vs["items"]] == ["v0", "v1"] and vs["active"] == "v1"
        assert vs["items"][1]["gate"]["accepted"] is True
        assert [e["action"] for e in vs["audit"]] == ["propose", "accept"]

        # rollback returns to unknown
        st, rb = c.call("POST", "/api/v1/learning/rollback", {})
        assert st == 200 and rb["active"] == "v0"
        r4, run4 = discover(c, TEXT)
        z, out4 = node(run4, "zorblat")
        assert z["role"] is None and out4["learned_version"] == "v0"
        # nothing earlier to roll back to now
        st, err = c.call("POST", "/api/v1/learning/rollback", {})
        assert st == 422 and err["error"]["code"]
        # old runs keep the version that produced them
        assert node(c.call("GET", f"/api/v1/discoveries/{r3}?outputs=1")[1], "zorblat")[1]["learned_version"] == "v1"
    finally:
        stop(app, server)


def test_runs_without_learning_data_are_unchanged(tmp_path):
    app, server, c = start(tmp_path)
    try:
        rid, run = discover(c, PLAIN)
        out = next(s for s in run["stages"] if s["name"] == "perception")["output"]
        from intelligence.perception import perceive_text
        assert out["problem"] == perceive_text(PLAIN, "").to_dict()["problem"]
        assert run["status"] == "done"
    finally:
        stop(app, server)


def test_validation_errors_are_422(tmp_path):
    app, server, c = start(tmp_path)
    try:
        for body in ({"term": "zorblat", "role": "wizard"}, {"term": "Zorb-lat!", "role": "buffer"}, {"role": "buffer"},
                     {"term": "zorblat"}, {"term": "zorblat", "role": "buffer", "run_id": 5}):
            st, err = c.call("POST", "/api/v1/learning/corrections", body)
            assert st == 422 and "error" in err, body
        st, err = c.call("POST", "/api/v1/learning/corrections", {"run_id": "nope", "term": "zorblat", "role": "buffer"})
        assert st == 404
        st, _ = c.call("POST", "/api/v1/learning/rollback", {"to": "v9"})
        assert st == 422
        st, _ = c.call("POST", "/api/v1/learning/rollback", {"to": 3})
        assert st == 422
        assert c.call("GET", "/api/v1/learning")[1]["evidence"]["total"] == 0
    finally:
        stop(app, server)


def test_annotations_become_evidence_with_conditions(tmp_path):
    app, server, c = start(tmp_path)
    try:
        rid, run = discover(c, PLAIN)
        hyps = next(s for s in run["stages"] if s["name"] == "hypothesis_generation")["output"]["hypotheses"]
        domain = next(s for s in run["stages"] if s["name"] == "structural_extraction")["output"]["query_domain"]
        hid = hyps[0]["id"]
        ctype = hyps[0]["based_on"][0].split(":")[0]
        st, _ = c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "promoted", "note": "x"})
        assert st == 200
        ev = app.learning.evidence.by_kind("hypothesis_feedback")
        assert len(ev) == 1
        assert ev[0]["payload"]["conditions"] == {"query_domain": domain}
        assert ev[0]["payload"]["concept_type"] == ctype and ev[0]["payload"]["decision"] == "promoted"
        assert ev[0]["provenance"] == "user"
        # 'none' and delete are not evidence
        c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "none"})
        c.call("DELETE", f"/api/v1/discoveries/{rid}/annotations/{hid}")
        assert len(app.learning.evidence.by_kind("hypothesis_feedback")) == 1
        # an invalid decision is rejected and records nothing
        st, _ = c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "bogus"})
        assert st == 422 and len(app.learning.evidence.by_kind("hypothesis_feedback")) == 1
        # a changed mind on the same hypothesis counts once for priors
        c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "rejected"})
        from intelligence.learning_engine import propose_priors
        events = app.learning.evidence.by_kind("hypothesis_feedback")
        assert len(events) == 2
        cand, rep = propose_priors(events)
        assert cand["priors"] == [] and rep["skipped"][0]["n"] == 1
    finally:
        stop(app, server)


def test_perception_stage_edit_counts_only_changed_roles(tmp_path):
    app, server, c = start(tmp_path)
    try:
        rid, run = discover(c, TEXT)
        out = next(s for s in run["stages"] if s["name"] == "perception")["output"]
        # an unchanged save is not evidence
        assert c.call("PUT", f"/api/v1/discoveries/{rid}/stages/perception", {"output": out})[0] == 200
        assert app.learning.evidence.events == []
        for n in out["problem"]["graph"]["nodes"]:
            if n["label"] == "zorblat":
                n["role"] = "transformer"
        assert c.call("PUT", f"/api/v1/discoveries/{rid}/stages/perception", {"output": out})[0] == 200
        evs = app.learning.evidence.by_kind("role_correction")
        assert [(e["payload"]["term"], e["payload"]["role"], e["payload"]["run_id"]) for e in evs] == [("zorblat", "transformer", rid)]
    finally:
        stop(app, server)


def test_rejected_cycle_leaves_active_version_unchanged(tmp_path, monkeypatch):
    app, server, c = start(tmp_path)
    try:
        for rid in ("a1", "a2"):
            app.learning.record_correction("zorblat", "transformer", rid)
        from intelligence.learning_engine import gate

        real = gate.compute_metrics

        def worse(config, version_id=None):
            m = real(config, version_id)
            if config and config.get("lexicon_overlay"):
                m = dict(m, **{"perception.role_accuracy": m["perception.role_accuracy"] - 0.05})
            return m

        monkeypatch.setattr(gate, "compute_metrics", worse)
        st, cyc = c.call("POST", "/api/v1/learning/cycle", {})
        assert st == 200 and cyc["accepted"] is False and cyc["changed"] is False
        assert cyc["after"] == "v0" and "Rejected candidate v1" in cyc["message"]
        assert cyc["regressions"] == ["perception.role_accuracy"]
        st, vs = c.call("GET", "/api/v1/learning/versions")
        assert vs["active"] == "v0" and vs["items"][1]["status"] == "rejected"
        assert [e["action"] for e in vs["audit"]] == ["propose", "reject"]
        st, s = c.call("GET", "/api/v1/learning")
        assert s["active"]["id"] == "v0" and s["last_gate"]["status"] == "rejected"
        # the next run still sees an unknown word
        _, run = discover(c, TEXT)
        assert node(run, "zorblat")[0]["role"] is None
        # repeated cycle on unchanged evidence does not store another rejected version
        assert s["pending"]["would_change"] is False and s["pending"]["already_rejected"] is True
        st, again = c.call("POST", "/api/v1/learning/cycle", {})
        assert again["accepted"] is False and again["candidate"] == "v1" and "Skipped" in again["message"]
        assert len(c.call("GET", "/api/v1/learning/versions")[1]["items"]) == 2
    finally:
        stop(app, server)


def test_cli_loop_in_temp_home(tmp_path, capsys):
    home = tmp_path / "h"

    def run(*args):
        code = cli.main(list(args) + ["--home", str(home)])
        out = capsys.readouterr()
        return code, out.out, out.err

    code, out, _ = run("learn", "status")
    assert code == 0 and "active learned version: v0" in out and "cannot detect harm" in out
    assert run("learn", "correct", "--term", "zorblat", "--role", "wizard")[0] == 2
    rids = []
    for text in (TEXT, TEXT2):
        _, _, err = run("analyze", text, "--format", "json")
        rids.append(err.split("run ")[1].split()[0])
    code, out, _ = run("learn", "correct", "--term", "zorblat", "--role", "transformer", "--run", rids[0])
    assert code == 0 and "Recorded 'zorblat' as transformer" in out
    code, out, _ = run("learn", "cycle")
    assert code == 0 and "Nothing changed" in out
    run("learn", "correct", "--term", "zorblat", "--role", "transformer", "--run", rids[1])
    code, out, _ = run("learn", "cycle")
    assert code == 0 and "Accepted as v1" in out and "perception.role_accuracy" in out and "no metric changed" in out
    code, out, _ = run("learn", "status")
    assert "active learned version: v1" in out and "zorblat -> transformer" in out
    code, out, _ = run("analyze", TEXT, "--format", "json")
    rep = json.loads(out)
    assert rep["learned_version"] == "v1"
    code, out, _ = run("learn", "history")
    assert "v1   active" in out and "audit #2 accept v1" in out
    code, out, _ = run("learn", "rollback")
    assert code == 0 and "Rolled back from v1 to v0" in out
    assert "active: v0" in run("learn", "history")[1]
    code, _, err = run("learn", "rollback")
    assert code == 2 and "no parent" in err


def test_isomorph_home_isolation(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    app_a, server_a, ca = start(a)
    try:
        ca.call("POST", "/api/v1/learning/corrections", {"term": "zorblat", "role": "buffer"})
    finally:
        stop(app_a, server_a)
    app_b, server_b, cb = start(b)
    try:
        assert cb.call("GET", "/api/v1/learning")[1]["evidence"]["total"] == 0
    finally:
        stop(app_b, server_b)
    assert os.path.exists(a / "home" / "learning" / "evidence.jsonl")
    # evidence persists across a restart of the same home
    app_a2, server_a2, ca2 = start(a)
    try:
        assert ca2.call("GET", "/api/v1/learning")[1]["evidence"]["role_correction"] == 1
    finally:
        stop(app_a2, server_a2)
