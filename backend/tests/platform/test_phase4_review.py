"""Review fixes for the stdlib runtime: Host/Origin/Content-Type checks, security headers, auth throttling,
restore and reset guard while a server runs, and a clear message when knowledge data is missing."""
import http.client
import json
import os
import subprocess
import sys

from isomorph_app import cli
from isomorph_app.config import AppConfig

from .test_server import TEXT, start, stop

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def raw(server, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        data = body.encode() if body is not None else None
        if data is not None:
            conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        r = conn.getresponse()
        b = r.read()
        return r.status, dict(r.getheaders()), b
    finally:
        conn.close()


def test_host_header_allowlist_in_tokenless_mode(tmp_path):
    app, server, c = start(tmp_path)
    try:
        port = server.port
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}", "localhost"):
            assert raw(server, "GET", "/api/v1/health", {"Host": host})[0] == 200, host
        st, _, body = raw(server, "GET", "/api/v1/discoveries", {"Host": f"attacker.example:{port}"})
        assert st == 403 and json.loads(body)["error"]["code"] == "forbidden"
        assert raw(server, "GET", "/", {"Host": "attacker.example"})[0] == 403  # the UI is covered too
    finally:
        stop(app, server)


def test_origin_must_match_host(tmp_path):
    app, server, c = start(tmp_path)
    try:
        h = {"Host": f"localhost:{server.port}"}
        assert raw(server, "GET", "/api/v1/health", dict(h, Origin=f"http://localhost:{server.port}"))[0] == 200
        assert raw(server, "GET", "/api/v1/health", dict(h, Origin="https://evil.example"))[0] == 403
        assert raw(server, "GET", "/api/v1/health", dict(h, Origin="null"))[0] == 403
        body = json.dumps({"text": TEXT})
        st, _, _ = raw(server, "POST", "/api/v1/discoveries",
                       dict(h, Origin="https://evil.example", **{"Content-Type": "application/json"}), body)
        assert st == 403
        assert app.store.list_runs(10, 0, None)["total"] == 0
    finally:
        stop(app, server)


def test_content_type_must_be_json(tmp_path):
    app, server, c = start(tmp_path)
    try:
        h = {"Host": f"localhost:{server.port}"}
        body = json.dumps({"text": TEXT})
        for ct in ("text/plain", "application/x-www-form-urlencoded"):
            st, _, b = raw(server, "POST", "/api/v1/discoveries", dict(h, **{"Content-Type": ct}), body)
            assert st == 415 and json.loads(b)["error"]["code"] == "unsupported_media_type", ct
        st, _, _ = raw(server, "POST", "/api/v1/discoveries", dict(h), body)  # no Content-Type at all
        assert st == 415
        assert app.store.list_runs(10, 0, None)["total"] == 0
        st, _, _ = raw(server, "POST", "/api/v1/discoveries", dict(h, **{"Content-Type": "application/json; charset=utf-8"}), body)
        assert st == 202
    finally:
        stop(app, server)


def test_security_headers_on_ui_and_api(tmp_path):
    app, server, c = start(tmp_path)
    try:
        for path in ("/", "/api/v1/health"):
            st, hdr, _ = raw(server, "GET", path, {"Host": f"localhost:{server.port}"})
            hdr = {k.lower(): v for k, v in hdr.items()}
            assert st == 200
            assert hdr["x-frame-options"] == "DENY"
            assert "default-src 'self'" in hdr["content-security-policy"]
    finally:
        stop(app, server)


def test_failed_token_attempts_are_throttled(tmp_path):
    app, server, c = start(tmp_path, token="s3cret-token")
    try:
        codes = [c.call("GET", "/api/v1/discoveries", token="wrong")[0] for _ in range(12)]
        assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
        # even the right token is refused while the client is locked out
        assert c.call("GET", "/api/v1/discoveries")[0] == 429
    finally:
        stop(app, server)


def test_token_mode_accepts_any_host_name(tmp_path):
    app, server, c = start(tmp_path, token="s3cret-token")
    try:
        st, _, _ = raw(server, "GET", "/api/v1/discoveries",
                       {"Host": "isomorph.internal", "Authorization": "Bearer s3cret-token"})
        assert st == 200
    finally:
        stop(app, server)


def _cli(args, home, capsys):
    code = cli.main(args + ["--home", str(home)])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_restore_and_reset_refuse_while_server_runs(tmp_path, capsys):
    home = tmp_path / "h"
    assert _cli(["seed"], home, capsys)[0] == 0
    bk = tmp_path / "bk.db"
    assert _cli(["backup", str(bk)], home, capsys)[0] == 0
    cfg = AppConfig(home=str(home))
    cli._write_lock(cfg, 8765)  # this process counts as the live server
    assert cli.server_running(cfg)
    code, _, err = _cli(["restore", str(bk), "--yes"], home, capsys)
    assert code == 1 and "server" in err and "Stop it" in err
    code, _, err = _cli(["reset", "--yes"], home, capsys)
    assert code == 1 and "server" in err
    assert "demo-roller-strip" in _cli(["list"], home, capsys)[1]  # nothing was deleted
    assert _cli(["reset", "--yes", "--force"], home, capsys)[0] == 0
    cli._remove_lock(cfg)
    assert cli.server_running(cfg) is None
    assert _cli(["restore", str(bk), "--yes"], home, capsys)[0] == 0


def test_stale_lock_is_ignored(tmp_path, capsys):
    home = tmp_path / "h"
    home.mkdir()
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    (home / cli.LOCK_NAME).write_text(json.dumps({"pid": p.pid, "host": "127.0.0.1", "port": 1}))
    assert cli.server_running(AppConfig(home=str(home))) is None
    (home / cli.LOCK_NAME).write_text("not json")
    assert cli.server_running(AppConfig(home=str(home))) is None


def test_serve_lock_lifecycle_and_missing_data_message(tmp_path):
    env = dict(os.environ, ISOMORPH_HOME=str(tmp_path / "home"), ISOMORPH_DATA_DIR=str(tmp_path / "nodata"))
    p = subprocess.run([sys.executable, "-m", "isomorph_app", "serve", "--no-browser", "--port", "0"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "knowledge data not found" in p.stderr and "ISOMORPH_DATA_DIR" in p.stderr
    d = subprocess.run([sys.executable, "-m", "isomorph_app", "doctor"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=60)
    assert d.returncode != 0 and "wheel install has no data/" in (d.stdout + d.stderr)


def test_real_server_process_holds_and_releases_lock(tmp_path):
    import re
    import signal
    home = tmp_path / "home"
    env = dict(os.environ, ISOMORPH_HOME=str(home), PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, "-m", "isomorph_app", "serve", "--no-browser", "--port", "0"], cwd=BACKEND, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert re.search(r"http://\S+", p.stdout.readline())
        import time
        for _ in range(50):
            if (home / cli.LOCK_NAME).exists():
                break
            time.sleep(0.1)
        assert cli.server_running(AppConfig(home=str(home)))["pid"] == p.pid
        r = subprocess.run([sys.executable, "-m", "isomorph_app", "reset", "--yes"], cwd=BACKEND, env=env,
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 1 and "Stop it" in r.stderr
        r = subprocess.run([sys.executable, "-m", "isomorph_app", "serve", "--no-browser", "--port", "0"], cwd=BACKEND, env=env,
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 1 and "already using" in r.stderr
    finally:
        p.send_signal(signal.SIGINT)
        p.communicate(timeout=20)
    assert not (home / cli.LOCK_NAME).exists()
