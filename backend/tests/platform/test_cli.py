import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

from isomorph_app import cli

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEXT = "A pump moves fluid. The pipe constrains the fluid flow. Friction dissipates energy. The goal is to minimise energy loss."


def run(args, home, capsys):
    code = cli.main(args + ["--home", str(home)]) if args[0] not in ("version",) else cli.main(args)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_doctor_ok_and_broken(tmp_path, capsys):
    code, out, _ = run(["doctor"], tmp_path / "ok", capsys)
    assert code == 0 and "[ OK ] database" in out and "All required checks passed" in out
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code, out, err = run(["doctor"], blocker / "sub", capsys)
    assert code == 1 and "[FAIL] data directory" in out and "failed" in err


def test_doctor_flags_insecure_host(tmp_path, capsys):
    code, out, _ = run(["doctor", "--host", "0.0.0.0"], tmp_path / "h", capsys)
    assert code == 1 and "ISOMORPH_TOKEN" in out


def test_validate_and_version(tmp_path, capsys):
    code, out, _ = run(["validate"], tmp_path, capsys)
    assert code == 0 and "knowledge OK" in out
    code, out, _ = run(["version"], tmp_path, capsys)
    assert code == 0 and out.startswith("isomorph ")


def test_analyze_text_file_and_errors(tmp_path, capsys):
    home = tmp_path / "h"
    code, out, err = run(["analyze", TEXT, "--title", "Pump"], home, capsys)
    assert code == 0 and out.startswith("# Pump") and "## Hypotheses" in out
    f = tmp_path / "p.txt"
    f.write_text(TEXT)
    dest = tmp_path / "r.json"
    code, _, _ = run(["analyze", "--file", str(f), "--format", "json", "--out", str(dest)], home, capsys)
    assert code == 0 and json.loads(dest.read_text())["run_status"] == "done"
    assert run(["analyze"], home, capsys)[0] == 2
    assert run(["analyze", "--file", str(tmp_path / "nope.txt")], home, capsys)[0] == 2
    assert run(["analyze", TEXT, "--file", str(f)], home, capsys)[0] == 2
    code, out, _ = run(["list"], home, capsys)
    assert code == 0 and out.count("done") == 2


def test_seed_idempotent_backup_restore_export_reset(tmp_path, capsys):
    home = tmp_path / "h"
    assert run(["seed"], home, capsys)[0] == 0
    assert "already present" in run(["seed"], home, capsys)[1]
    bk = tmp_path / "bk.db"
    assert run(["backup", str(bk)], home, capsys)[0] == 0 and bk.exists()
    assert run(["backup", str(bk)], home, capsys)[0] == 1  # never overwrites
    exp = tmp_path / "e.json"
    assert run(["export", "--out", str(exp)], home, capsys)[0] == 0
    assert len(json.loads(exp.read_text())["runs"]) == 1

    assert run(["reset", "--yes"], home, capsys)[0] == 0
    assert "no discoveries" in run(["list"], home, capsys)[1]
    assert os.listdir(home / "backups")  # reset made a safety backup

    assert run(["restore", str(bk)], home, capsys)[0] == 1  # no tty, no --yes: refuses
    assert run(["restore", str(bk), "--yes"], home, capsys)[0] == 0
    assert "demo-roller-strip" in run(["list"], home, capsys)[1]
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"junk")
    code, _, err = run(["restore", str(bad), "--yes"], home, capsys)
    assert code == 1 and "unchanged" in err
    assert "demo-roller-strip" in run(["list"], home, capsys)[1]


def test_port_helpers():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    busy = s.getsockname()[1]
    try:
        assert not cli.port_free("127.0.0.1", busy)
        assert cli.pick_port("127.0.0.1", busy, strict=False) != busy
        try:
            cli.pick_port("127.0.0.1", busy, strict=True)
            assert False
        except OSError:
            pass
    finally:
        s.close()


def test_serve_subprocess_end_to_end(tmp_path):
    env = dict(os.environ, ISOMORPH_HOME=str(tmp_path / "home"), PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, "-m", "isomorph_app", "serve", "--no-browser", "--port", "0"], cwd=BACKEND, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        line = p.stdout.readline()
        url = re.search(r"http://\S+", line).group(0)
        with urllib.request.urlopen(url + "api/v1/health", timeout=10) as r:
            assert json.loads(r.read())["status"] == "ok"
        req = urllib.request.Request(url + "api/v1/discoveries", data=json.dumps({"text": TEXT}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        rid = json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]
        for _ in range(100):
            with urllib.request.urlopen(url + f"api/v1/discoveries/{rid}", timeout=10) as r:
                status = json.loads(r.read())["status"]
            if status != "queued" and status != "running":
                break
            time.sleep(0.2)
        assert status == "done"
    finally:
        p.send_signal(signal.SIGINT)
        out = p.communicate(timeout=20)[0]
    assert p.returncode == 0 and "shutting down" in out


def test_serve_refuses_open_bind(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "ISOMORPH_TOKEN"}
    env["ISOMORPH_HOME"] = str(tmp_path / "home")
    p = subprocess.run([sys.executable, "-m", "isomorph_app", "serve", "--no-browser", "--host", "0.0.0.0", "--port", "0"],
                       cwd=BACKEND, env=env, capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "ISOMORPH_TOKEN" in p.stderr
