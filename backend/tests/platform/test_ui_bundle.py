"""The bundled web UI: files exist, are served by the real server, avoid unsafe patterns and match the API."""
import json
import os
import re
import shutil
import subprocess

import pytest

from isomorph_app.server import STATIC_DEFAULT
from tests.platform.test_server import start, stop

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
NODE = shutil.which("node")


def _read(name):
    with open(os.path.join(STATIC_DEFAULT, name), encoding="utf-8") as f:
        return f.read()


def test_ui_files_present_and_self_contained():
    for name in ("index.html", "app.js", "lib.js", "styles.css"):
        assert os.path.isfile(os.path.join(STATIC_DEFAULT, name)), name
    for name in ("index.html", "app.js", "lib.js", "styles.css"):
        text = _read(name)
        assert not re.search(r"(src|href)=[\"']https?://", text), name + " loads an external resource"
        assert "cdn." not in text and "googleapis" not in text
        assert "@import" not in text
    for name in ("app.js", "lib.js"):
        text = _read(name)
        code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(", code), name


def test_demo_example_matches_bundled_demo_problem():
    with open(os.path.join(ROOT, "data", "demo", "roller_problem.json"), encoding="utf-8") as f:
        statement = json.load(f)["statement"]
    assert statement in _read("lib.js")


def test_server_serves_bundled_ui(tmp_path):
    app, server, c = start(tmp_path)
    try:
        for path, ctype in (("/", "text/html"), ("/index.html", "text/html"), ("/app.js", "javascript"), ("/lib.js", "javascript"),
                            ("/styles.css", "text/css"), ("/run/abc123", "text/html"), ("/knowledge", "text/html")):
            import urllib.request
            with urllib.request.urlopen(c.base + path, timeout=10) as r:
                body = r.read().decode()
                assert r.status == 200 and ctype in r.headers["Content-Type"], path
                assert r.headers["X-Content-Type-Options"] == "nosniff"
            if path == "/":
                assert "<title>ISOMORPH</title>" in body and "/app.js" in body
        st, _ = c.call("GET", "/missing.js")
        assert st == 404
        st, h = c.call("GET", "/api/v1/health")
        assert st == 200 and h["status"] == "ok"
    finally:
        stop(app, server)


def test_ui_routes_use_real_api_paths():
    """Every API path the UI calls must exist in the server's routes."""
    js = _read("app.js")
    server_src = open(os.path.join(os.path.dirname(STATIC_DEFAULT), "server.py"), encoding="utf-8").read()
    for frag in ("/discoveries", "/annotations", "/report", "/events", "/cancel", "/resume", "/rerun", "/knowledge-systems", "/domains",
                 "/settings", "/health"):
        assert frag in js, frag
        assert frag.strip("/").split("/")[0] in server_src, frag


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_syntax_and_helper_tests():
    for name in ("app.js", "lib.js"):
        r = subprocess.run([NODE, "--check", os.path.join(STATIC_DEFAULT, name)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([NODE, os.path.join(here, "ui_helpers.test.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ui helper tests passed" in r.stdout
