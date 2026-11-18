import json
import os
import time
import urllib.error
import urllib.request

import pytest

from isomorph_app.app import App
from isomorph_app.config import AppConfig
from isomorph_app.server import InsecureBind, create_server, serve_in_thread

TEXT = ("A pump moves fluid. The pipe constrains the fluid flow. Friction dissipates energy at the wall. "
        "The goal is to minimise energy loss.")


class Client:
    def __init__(self, base, token=None):
        self.base, self.token = base, token

    def call(self, method, path, body=None, raw=None, headers=None, token="default"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method)
        tok = self.token if token == "default" else token
        if tok:
            req.add_header("Authorization", "Bearer " + tok)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
                ct = r.headers.get("Content-Type", "")
                return r.status, (json.loads(b) if "json" in ct and b else b)
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b)
            except ValueError:
                return e.code, b

    def wait_done(self, rid, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            st, run = self.call("GET", f"/api/v1/discoveries/{rid}")
            if run["status"] in ("done", "failed", "cancelled"):
                return run
            time.sleep(0.1)
        raise AssertionError("run did not finish")


def start(tmp_path, **kw):
    cfg = AppConfig(home=str(tmp_path / "home"), port=0, **kw)
    app = App(cfg)
    server = create_server(app)
    serve_in_thread(server)
    return app, server, Client(f"http://127.0.0.1:{server.port}", cfg.token)


def stop(app, server):
    server.shutdown()
    server.server_close()
    app.close()


@pytest.fixture
def srv(tmp_path):
    app, server, client = start(tmp_path)
    yield app, server, client, tmp_path
    stop(app, server)


def test_full_flow_and_persistence_across_restart(tmp_path):
    app, server, c = start(tmp_path)
    assert c.call("GET", "/api/v1/health")[1]["status"] == "ok"
    st, r = c.call("POST", "/api/v1/discoveries", {"text": TEXT, "title": "pump"})
    assert st == 202
    rid = r["id"]
    run = c.wait_done(rid)
    assert run["status"] == "done", run.get("error")
    st, page = c.call("GET", "/api/v1/discoveries")
    assert page["total"] == 1 and page["items"][0]["title"] == "pump"
    st, stages = c.call("GET", f"/api/v1/discoveries/{rid}/stages")
    assert [s["name"] for s in stages["items"]][0] == "perception" and "output" not in stages["items"][0]
    st, matches = c.call("GET", f"/api/v1/discoveries/{rid}/matches")
    assert st == 200 and matches["total"] > 0

    # edit a stage: later stages become stale, rerun downstream recomputes them
    st, hyp = c.call("GET", f"/api/v1/discoveries/{rid}/stages/hypothesis_generation")
    out = hyp["output"]
    hid = out["hypotheses"][0]["id"]
    out["hypotheses"][0]["statement"] = out["hypotheses"][0]["statement"] + " (edited by reviewer)"
    st, edited = c.call("PUT", f"/api/v1/discoveries/{rid}/stages/hypothesis_generation", {"output": out})
    assert st == 200 and edited["source"] == "user"
    st, vs = c.call("GET", f"/api/v1/discoveries/{rid}/stages/validation")
    assert vs["status"] == "stale"
    st, _ = c.call("POST", f"/api/v1/discoveries/{rid}/stages/hypothesis_generation/rerun?mode=downstream")
    assert st == 202
    run = c.wait_done(rid)
    assert run["status"] == "done"
    st, hyp2 = c.call("GET", f"/api/v1/discoveries/{rid}/stages/hypothesis_generation")
    assert "(edited by reviewer)" in json.dumps(hyp2["output"])
    st, bad = c.call("PUT", f"/api/v1/discoveries/{rid}/stages/hypothesis_generation", {"output": {"hypotheses": 5}})
    assert st == 422 and bad["error"]["code"] == "validation_error"
    st, _ = c.call("POST", f"/api/v1/discoveries/{rid}/stages/validation/rerun?mode=sideways")
    assert st == 422
    st, _ = c.call("POST", f"/api/v1/discoveries/{rid}/stages/validation/rerun?mode=from")
    assert st == 202
    assert c.wait_done(rid)["status"] == "done"

    # annotations
    st, a = c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "promoted", "note": "worth testing"})
    assert st == 200 and a["provenance"] == "user"
    assert c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/H99-nope", {"decision": "saved"})[0] == 404
    assert c.call("PUT", f"/api/v1/discoveries/{rid}/annotations/{hid}", {"decision": "weird"})[0] == 422
    st, md = c.call("GET", f"/api/v1/discoveries/{rid}/report")
    assert st == 200 and b"## Hypotheses" in md and b"worth testing" in md
    st, js = c.call("GET", f"/api/v1/discoveries/{rid}/report?format=json")
    assert js["annotations"][hid]["decision"] == "promoted"
    assert c.call("GET", f"/api/v1/discoveries/{rid}/report?format=pdf")[0] == 422

    # restart: new server and App on the same data directory
    stop(app, server)
    app2, server2, c2 = start(tmp_path)
    try:
        st, run = c2.call("GET", f"/api/v1/discoveries/{rid}")
        assert st == 200 and run["status"] == "done"
        st, notes = c2.call("GET", f"/api/v1/discoveries/{rid}/annotations")
        assert notes["items"][hid]["note"] == "worth testing"
        assert c2.call("DELETE", f"/api/v1/discoveries/{rid}/annotations/{hid}")[0] == 204
        assert c2.call("GET", f"/api/v1/discoveries/{rid}/annotations")[1]["items"] == {}
        assert c2.call("DELETE", f"/api/v1/discoveries/{rid}")[0] == 204
        assert c2.call("GET", f"/api/v1/discoveries/{rid}")[0] == 404
    finally:
        stop(app2, server2)


def test_restart_recovers_interrupted_run(tmp_path):
    cfg = AppConfig(home=str(tmp_path / "h"), port=0)
    app = App(cfg, synchronous=True)
    run = app.orch.create_run(text=TEXT)
    r = app.store.get(run.id)
    r.status = "running"
    r.stages["perception"].status = "running"
    app.store.save(r)
    app.close()
    app2 = App(cfg, synchronous=True)
    got = app2.store.get(run.id)
    assert got.status == "failed" and got.error == "interrupted by restart" and app2.recovered == [run.id]
    app2.close()


def test_sse_stream(srv):
    app, server, c, _ = srv
    rid = c.call("POST", "/api/v1/discoveries", {"text": TEXT})[1]["id"]
    req = urllib.request.Request(c.base + f"/api/v1/discoveries/{rid}/events")
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.headers["Content-Type"].startswith("text/event-stream")
        body = r.read().decode()
    assert "event: progress" in body and "event: end" in body


def test_validation_errors_and_unknown(srv):
    app, server, c, _ = srv
    assert c.call("POST", "/api/v1/discoveries", {})[0] == 422
    assert c.call("POST", "/api/v1/discoveries", raw=b"{not json")[0] == 422
    assert c.call("POST", "/api/v1/discoveries", raw=b"[1]")[0] == 422
    assert c.call("POST", "/api/v1/discoveries", {"text": TEXT, "config": {"nope": 1}})[0] == 422
    assert c.call("POST", "/api/v1/discoveries", {"text": TEXT, "top_k": 0})[0] == 422
    st, e = c.call("GET", "/api/v1/discoveries/doesnotexist")
    assert st == 404 and e["error"]["code"] == "not_found"
    assert c.call("GET", "/api/v1/discoveries/..%2f..%2fetc")[0] == 404
    assert c.call("GET", "/api/v1/nothing")[0] == 404
    assert c.call("GET", "/api/v1/discoveries?limit=500")[0] == 422
    assert c.call("POST", "/health")[0] == 405
    st, kn = c.call("GET", "/api/v1/knowledge-systems?limit=5&domain=biology")
    assert st == 200 and kn["items"] and all(s["domain"] == "biology" for s in kn["items"])
    assert c.call("GET", "/api/v1/knowledge-systems/" + kn["items"][0]["id"])[0] == 200
    assert c.call("GET", "/api/v1/domains")[1]["total"] == 12
    assert c.call("GET", "/api/v1/settings")[1]["knowledge"]["systems"] > 50


def test_oversize_and_traversal(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>ui</h1>")
    (static / "app.js").write_text("x=1")
    (tmp_path / "secret.txt").write_text("secret")
    app, server, c = start(tmp_path, max_body_bytes=1000, static_dir=str(static))
    try:
        st, e = c.call("POST", "/api/v1/discoveries", raw=json.dumps({"text": "a" * 5000}).encode())
        assert st == 413 and e["error"]["code"] == "payload_too_large"
        assert c.call("GET", "/")[1] == b"<h1>ui</h1>"
        assert c.call("GET", "/app.js")[0] == 200
        assert c.call("GET", "/some/route")[1] == b"<h1>ui</h1>"  # single page app fallback
        assert c.call("GET", "/missing.js")[0] == 404
        for evil in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt", "/a%00.js", "/..\\secret.txt"):
            st, body = c.call("GET", evil)
            assert body != b"secret", evil
            assert st in (200, 404), evil
    finally:
        stop(app, server)


def test_token_auth_and_bind_guard(tmp_path):
    app, server, c = start(tmp_path, token="s3cret-token")
    try:
        assert c.call("GET", "/api/v1/health", token=None)[0] == 200
        assert c.call("GET", "/api/v1/discoveries", token=None)[0] == 401
        assert c.call("GET", "/api/v1/discoveries", token="wrong")[0] == 401
        assert c.call("GET", "/api/v1/discoveries")[0] == 200
    finally:
        stop(app, server)
    cfg = AppConfig(home=str(tmp_path / "h2"), host="0.0.0.0", port=0)
    a = App(cfg)
    try:
        with pytest.raises(InsecureBind):
            create_server(a)
    finally:
        a.close()


def test_cancel_and_conflict(srv):
    app, server, c, _ = srv
    rid = c.call("POST", "/api/v1/discoveries", {"text": TEXT})[1]["id"]
    c.wait_done(rid)
    assert c.call("POST", f"/api/v1/discoveries/{rid}/cancel")[0] == 409  # already finished
