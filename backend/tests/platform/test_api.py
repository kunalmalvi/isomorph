"""API tests: authentication, RBAC, ownership isolation, pagination, errors, discovery flow, SSE.

UNVERIFIED in the authoring sandbox: skipped there because fastapi and sqlalchemy are not installed.
Run them after `pip install -r backend/requirements-dev.txt`.
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pydantic")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402
from core.config import load_settings  # noqa: E402

PW = "correct horse battery"
STATEMENT = ("A rolling mill reduces the thickness of a metal strip between two rollers. The roll force must not exceed "
             "800 kN. The strip thickness varies and must stay within tolerance. A sensor measures the exit thickness.")


@pytest.fixture
def client(tmp_path):
    s = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path}/t.db", "ISOMORPH_SECRET_KEY": "k" * 40, "AUTH_ATTEMPTS_PER_MINUTE": "1000",
                       "API_REQUESTS_PER_MINUTE": "100000", "MAX_UPLOAD_BYTES": "2000"})
    with TestClient(create_app(s, synchronous_jobs=True, create_tables=True)) as c:
        yield c


def signup(c, name):
    r = c.post("/api/v1/auth/register", json={"email": f"{name}@example.com", "password": PW})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def mkproject(c, h, name="P"):
    r = c.post("/api/v1/projects", json={"name": name}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mkproblem(c, h, pid):
    r = c.post("/api/v1/problems", json={"project_id": pid, "title": "Mill", "statement": STATEMENT}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_auth_required_and_error_envelope(client):
    r = client.get("/api/v1/projects")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r = client.get("/api/v1/projects", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert client.get("/api/v1/nope").json()["error"]["code"] == "not_found"


def test_register_login_and_validation(client):
    signup(client, "a")
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": PW}).status_code == 409
    assert client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong password!"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": PW}).status_code == 401
    ok = client.post("/api/v1/auth/login", json={"email": "A@example.com", "password": PW})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    r = client.post("/api/v1/auth/register", json={"email": "bad", "password": PW})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error" and r.json()["error"]["details"]


def test_project_isolation_between_users(client):
    a, b = signup(client, "a"), signup(client, "b")
    pid = mkproject(client, a)
    prob = mkproblem(client, a, pid)
    assert client.get(f"/api/v1/projects/{pid}", headers=b).status_code == 404
    assert client.get(f"/api/v1/problems/{prob}", headers=b).status_code == 404
    assert client.patch(f"/api/v1/problems/{prob}", json={"title": "x"}, headers=b).status_code == 404
    assert client.delete(f"/api/v1/projects/{pid}", headers=b).status_code == 404
    assert client.post("/api/v1/problems", json={"project_id": pid, "title": "t", "statement": "s"}, headers=b).status_code == 404
    assert client.get("/api/v1/projects", headers=b).json()["total"] == 0
    assert client.get("/api/v1/problems", headers=b).json()["total"] == 0
    assert client.post("/api/v1/discoveries", json={"problem_id": prob}, headers=b).status_code == 404
    assert client.get("/api/v1/projects", headers=a).json()["total"] == 1


def test_rbac_viewer_editor_owner(client):
    a, b = signup(client, "a"), signup(client, "b")
    pid = mkproject(client, a)
    prob = mkproblem(client, a, pid)
    r = client.post(f"/api/v1/projects/{pid}/members", json={"email": "b@example.com", "role": "viewer"}, headers=a)
    assert r.status_code == 201
    assert client.get(f"/api/v1/problems/{prob}", headers=b).status_code == 200
    assert client.patch(f"/api/v1/problems/{prob}", json={"title": "x"}, headers=b).status_code == 403
    assert client.post(f"/api/v1/problems/{prob}/entities", json={"name": "e"}, headers=b).status_code == 403
    assert client.post("/api/v1/discoveries", json={"problem_id": prob}, headers=b).status_code == 403
    uid = r.json()["user_id"]
    client.delete(f"/api/v1/projects/{pid}/members/{uid}", headers=a)
    client.post(f"/api/v1/projects/{pid}/members", json={"user_id": uid, "role": "editor"}, headers=a)
    assert client.patch(f"/api/v1/problems/{prob}", json={"title": "x"}, headers=b).status_code == 200
    assert client.delete(f"/api/v1/projects/{pid}", headers=b).status_code == 403
    assert client.post(f"/api/v1/projects/{pid}/members", json={"email": "a@example.com", "role": "owner"}, headers=b).status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}", headers=a).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=a).status_code == 404  # soft deleted


def test_last_owner_cannot_be_removed(client):
    a = signup(client, "a")
    pid = mkproject(client, a)
    me = client.get("/api/v1/auth/me", headers=a).json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}/members/{me}", headers=a).status_code == 409


def test_pagination_bounds(client):
    a = signup(client, "a")
    for i in range(3):
        mkproject(client, a, f"p{i}")
    r = client.get("/api/v1/projects?limit=2&offset=1", headers=a).json()
    assert len(r["items"]) == 2 and r["total"] == 3 and r["limit"] == 2 and r["offset"] == 1
    assert client.get("/api/v1/projects?limit=101", headers=a).status_code == 422
    assert client.get("/api/v1/projects?offset=-1", headers=a).status_code == 422


def test_problem_children_validation(client):
    a = signup(client, "a")
    prob = mkproblem(client, a, mkproject(client, a))
    e1 = client.post(f"/api/v1/problems/{prob}/entities", json={"name": "pump", "kind": "source"}, headers=a).json()["id"]
    e2 = client.post(f"/api/v1/problems/{prob}/entities", json={"name": "tank", "kind": "buffer"}, headers=a).json()["id"]
    assert client.post(f"/api/v1/problems/{prob}/relationships", json={"source_entity_id": e1, "target_entity_id": e2, "relation_type": "bogus"}, headers=a).status_code == 422
    assert client.post(f"/api/v1/problems/{prob}/relationships", json={"source_entity_id": e1, "target_entity_id": e2, "relation_type": "flows_to"}, headers=a).status_code == 201
    assert client.post(f"/api/v1/problems/{prob}/variables", json={"name": "x", "min_value": 5, "max_value": 1}, headers=a).status_code == 422
    other = mkproblem(client, a, mkproject(client, a, "other"))
    assert client.post(f"/api/v1/problems/{other}/relationships", json={"source_entity_id": e1, "target_entity_id": e2, "relation_type": "flows_to"}, headers=a).status_code == 422


def test_upload_validation(client):
    a = signup(client, "a")
    prob = mkproblem(client, a, mkproject(client, a))
    url = f"/api/v1/problems/{prob}/uploads"
    ok = client.post(url, files={"file": ("n.txt", b"A pump moves water into a tank.", "text/plain")}, headers=a)
    assert ok.status_code == 200 and ok.json()["processed"] is True
    assert client.post(url, files={"file": ("n.exe", b"MZ", "application/octet-stream")}, headers=a).status_code == 422
    assert client.post(url, files={"file": ("big.txt", b"x" * 5000, "text/plain")}, headers=a).status_code == 413


def test_weights_must_sum_to_100(client):
    a = signup(client, "a")
    assert client.patch("/api/v1/settings/weights", json={"weights": {"functional": 50}}, headers=a).status_code == 422
    ok = client.patch("/api/v1/settings/weights", json={"weights": {"functional": 30, "relationship": 20}}, headers=a)
    assert ok.status_code == 200 and ok.json()["weights"]["functional"] == 30
    assert client.get("/api/v1/settings", headers=a).json()["weights_are_default"] is False
    prob = mkproblem(client, a, mkproject(client, a))
    assert client.post("/api/v1/discoveries", json={"problem_id": prob, "weights": {"functional": 99}}, headers=a).status_code == 422


def test_provider_status_exposes_no_secrets(client):
    a = signup(client, "a")
    r = client.get("/api/v1/settings/providers", headers=a).json()["providers"]
    assert r[0]["name"] == "local" and r[0]["configured"] is True
    assert all("key" not in str(p.keys()).lower() for p in r)


def test_knowledge_endpoints(client):
    a = signup(client, "a")
    assert client.get("/api/v1/domains").status_code == 401
    d = client.get("/api/v1/domains?limit=5", headers=a).json()
    assert d["total"] >= 5
    sid = client.get("/api/v1/knowledge-systems?limit=1", headers=a).json()["items"][0]["id"]
    assert client.get(f"/api/v1/knowledge-systems/{sid}/graph", headers=a).json()["nodes"]
    assert client.get("/api/v1/knowledge-systems/nope", headers=a).status_code == 404
    assert client.get("/api/v1/mechanisms", headers=a).json()["total"] > 0


def test_full_discovery_flow_isolation_and_stage_edit(client):
    a, b = signup(client, "a"), signup(client, "b")
    pid = mkproject(client, a)
    prob = mkproblem(client, a, pid)
    r = client.post("/api/v1/discoveries", json={"problem_id": prob, "top_k": 5}, headers=a)
    assert r.status_code == 202
    did = r.json()["id"]
    d = client.get(f"/api/v1/discoveries/{did}", headers=a).json()
    assert d["status"] == "done" and d["progress"]["completed"] == 9
    assert client.get(f"/api/v1/discoveries/{did}", headers=b).status_code == 404
    assert client.get(f"/api/v1/discoveries/{did}/stages/perception", headers=b).status_code == 404
    stages = client.get(f"/api/v1/discoveries/{did}/stages", headers=a).json()["stages"]
    assert [s["name"] for s in stages][0] == "perception" and all("output" not in s for s in stages)
    cand = client.get(f"/api/v1/discoveries/{did}/stages/cross_domain_search", headers=a).json()["output"]
    cand["candidates"] = cand["candidates"][:2]
    assert client.put(f"/api/v1/discoveries/{did}/stages/cross_domain_search", json={"output": cand}, headers=b).status_code == 404
    assert client.put(f"/api/v1/discoveries/{did}/stages/cross_domain_search", json={"output": cand}, headers=a).status_code == 200
    assert client.get(f"/api/v1/discoveries/{did}/stages/structural_matching", headers=a).json()["status"] == "stale"
    assert client.post(f"/api/v1/discoveries/{did}/stages/cross_domain_search/rerun", headers=a).status_code == 202
    m = client.get(f"/api/v1/discoveries/{did}/matches", headers=a).json()
    assert 1 <= m["total"] <= 2
    mid = m["items"][0]["id"]
    assert client.get(f"/api/v1/matches/{mid}/breakdown", headers=b).status_code == 404
    bd = client.get(f"/api/v1/matches/{mid}/breakdown", headers=a).json()
    assert set(bd["components"]) == {"functional", "relationship", "topological", "dynamic", "constraint", "semantic"}
    assert client.get("/api/v1/matches", headers=b).json()["total"] == 0
    # derivation chain
    mp = client.post("/api/v1/mappings", json={"match_id": mid}, headers=a)
    assert mp.status_code == 201
    assert client.post("/api/v1/mappings", json={"match_id": mid}, headers=b).status_code == 404
    tr = client.post("/api/v1/transformations", json={"mapping_id": mp.json()["id"]}, headers=a)
    assert tr.status_code == 201 and tr.json()["status"] in ("ok", "blocked")
    hy = client.post("/api/v1/hypotheses", json={"transformation_id": tr.json()["id"]}, headers=a)
    assert hy.status_code == 201 and hy.json()["status"] == "untested"
    hid = hy.json()["id"]
    assert client.get(f"/api/v1/hypotheses/{hid}", headers=b).status_code == 404
    v = client.post("/api/v1/validation", json={"hypothesis_id": hid, "seeds": 5}, headers=a)
    assert v.status_code == 201 and v.json()["outcome"] in ("untested", "supported", "refuted", "inconclusive")
    assert client.get(f"/api/v1/validation?hypothesis_id={hid}", headers=b).json()["total"] == 0
    # report
    rep = client.post("/api/v1/reports", json={"project_id": pid, "discovery_session_id": did, "title": "R"}, headers=a)
    assert rep.status_code == 201
    rid = rep.json()["id"]
    assert client.get(f"/api/v1/reports/{rid}/export?format=md", headers=a).text.startswith("# R")
    assert client.get(f"/api/v1/reports/{rid}/export?format=json", headers=a).json()["title"] == "R"
    assert client.get(f"/api/v1/reports/{rid}/export?format=pdf", headers=a).status_code == 422
    assert client.get(f"/api/v1/reports/{rid}", headers=b).status_code == 404


def test_sse_progress_stream(client):
    a = signup(client, "a")
    prob = mkproblem(client, a, mkproject(client, a))
    did = client.post("/api/v1/discoveries", json={"problem_id": prob}, headers=a).json()["id"]
    with client.stream("GET", f"/api/v1/discoveries/{did}/events", headers=a) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "event: progress" in body and "event: end" in body and '"status":"done"' in body
    b = signup(client, "b")
    assert client.get(f"/api/v1/discoveries/{did}/events", headers=b).status_code == 404


def test_archive_and_restore(client):
    a, b = signup(client, "a"), signup(client, "b")
    pid = mkproject(client, a)
    assert client.post(f"/api/v1/archive/{pid}", headers=b).status_code == 404
    assert client.post(f"/api/v1/archive/{pid}", headers=a).status_code == 200
    assert client.post(f"/api/v1/archive/{pid}", headers=a).status_code == 409
    assert client.get("/api/v1/archive", headers=a).json()["total"] == 1
    assert client.get("/api/v1/projects", headers=a).json()["total"] == 0
    assert client.post(f"/api/v1/archive/{pid}/restore", headers=a).status_code == 200


def test_rate_limit_on_auth(tmp_path):
    s = load_settings({"DATABASE_URL": f"sqlite:///{tmp_path}/r.db", "ISOMORPH_SECRET_KEY": "k" * 40, "AUTH_ATTEMPTS_PER_MINUTE": "3"})
    with TestClient(create_app(s, synchronous_jobs=True, create_tables=True)) as c:
        codes = [c.post("/api/v1/auth/login", json={"email": "x@example.com", "password": PW}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_lists_hide_deleted_projects_and_non_members_get_404_before_validation(client):
    a, b = signup(client, "a"), signup(client, "b")
    pid = mkproject(client, a)
    prob = mkproblem(client, a, pid)
    bogus = "00000000-0000-0000-0000-000000000001"
    rel = {"source_entity_id": bogus, "target_entity_id": bogus, "relation_type": "flows_to"}
    assert client.post(f"/api/v1/problems/{prob}/relationships", json=rel, headers=b).status_code == 404
    assert client.post(f"/api/v1/problems/{prob}/evidence", json={"statement": "c", "source_id": bogus}, headers=b).status_code == 404
    assert client.get("/api/v1/problems", headers=a).json()["total"] == 1
    assert client.delete(f"/api/v1/projects/{pid}", headers=a).status_code in (200, 204)
    assert client.get("/api/v1/problems", headers=a).json()["total"] == 0


# ---- phase 2 (UNVERIFIED: skipped where FastAPI is not installed)
def test_annotations_endpoints(client):
    a, b = signup(client, "a"), signup(client, "b")
    prob = mkproblem(client, a, mkproject(client, a))
    did = client.post("/api/v1/discoveries", json={"problem_id": prob}, headers=a).json()["id"]
    hid = client.get(f"/api/v1/discoveries/{did}/stages/hypothesis_generation", headers=a).json()["output"]["hypotheses"][0]["id"]
    url = f"/api/v1/discoveries/{did}/annotations"
    assert client.get(url, headers=a).json() == {"items": {}}
    r = client.put(f"{url}/{hid}", json={"decision": "promoted", "note": "n"}, headers=a)
    assert r.status_code == 200 and r.json()["provenance"] == "user"
    assert client.get(url, headers=a).json()["items"][hid]["decision"] == "promoted"
    assert client.put(f"{url}/{hid}", json={"decision": "bogus"}, headers=a).status_code == 422
    assert client.put(f"{url}/nope", json={"decision": "saved"}, headers=a).status_code == 404
    assert client.get(url, headers=b).status_code == 404
    assert client.delete(f"{url}/{hid}", headers=a).status_code == 204
    assert client.get(url, headers=a).json()["items"] == {}


def test_sse_reconnect_header_continues_ids(client):
    a = signup(client, "a")
    prob = mkproblem(client, a, mkproject(client, a))
    did = client.post("/api/v1/discoveries", json={"problem_id": prob}, headers=a).json()["id"]
    with client.stream("GET", f"/api/v1/discoveries/{did}/events", headers={**a, "Last-Event-ID": "5"}) as r:
        body = "".join(r.iter_text())
    assert "retry: 2000" in body and "id: 6\n" in body
