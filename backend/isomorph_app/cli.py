"""`isomorph` command line: run, check and manage the app. Stdlib only.

Subcommands: serve, doctor, analyze, seed, validate, backup, restore, export, reset, list, version.
Every command takes --home (or ISOMORPH_HOME) so one data directory holds the database, uploads and backups.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from typing import List, Optional

from . import __version__
from .config import AppConfig, DEFAULT_PORT, is_loopback, load_config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO_PROBLEM = os.path.join(ROOT, "data", "demo", "roller_problem.json")


def _out(msg: str = "") -> None:
    print(msg, flush=True)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def port_free(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
        return True
    except OSError:
        return False


def pick_port(host: str, start: int, strict: bool, tries: int = 20) -> int:
    if port_free(host, start):
        return start
    if strict or start == 0:
        raise OSError(f"port {start} on {host} is already in use")
    for p in range(start + 1, start + tries + 1):
        if port_free(host, p):
            return p
    raise OSError(f"no free port found in {start}..{start + tries} on {host}")


LOCK_NAME = "server.lock"


def _lock_path(cfg: AppConfig) -> str:
    return os.path.join(cfg.home, LOCK_NAME)


def server_running(cfg: AppConfig) -> Optional[dict]:
    """Returns the lock info of a live server using this data directory, else None (stale locks are ignored)."""
    try:
        with open(_lock_path(cfg), encoding="utf-8") as f:
            info = json.load(f)
        pid, port = int(info["pid"]), int(info["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pid == os.getpid():
        return info
    if sys.platform == "win32":
        alive = not port_free(info.get("host") or "127.0.0.1", port)
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
        except OSError:
            alive = False
    return info if alive else None


def _write_lock(cfg: AppConfig, port: int) -> None:
    cfg.ensure_dirs()
    with open(_lock_path(cfg), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "host": cfg.host, "port": port}, f)


def _remove_lock(cfg: AppConfig) -> None:
    try:
        with open(_lock_path(cfg), encoding="utf-8") as f:
            if json.load(f).get("pid") != os.getpid():
                return
        os.remove(_lock_path(cfg))
    except (OSError, ValueError):
        pass


def _refuse_if_serving(cfg: AppConfig, action: str, force: bool) -> bool:
    info = server_running(cfg)
    if info and not force:
        _err(f"error: an ISOMORPH server (pid {info['pid']}, port {info['port']}) is using {cfg.home}. "
             f"Stop it before you {action}, or pass --force if you are sure it is not running.")
        return True
    return False


def _config(args) -> AppConfig:
    return load_config(home=getattr(args, "home", None), host=getattr(args, "host", None), port=getattr(args, "port", None))


def _open_app(args, synchronous: bool = False):
    from .app import App
    return App(_config(args), synchronous=synchronous)


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        _err("refusing to continue without confirmation; pass --yes to confirm non-interactively")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# ------------------------------------------------------------------ serve
def cmd_serve(args) -> int:
    from .server import InsecureBind, create_server, serve_in_thread
    cfg = _config(args)
    from knowledge_base.loader import data_dir
    kb_dir = os.path.join(data_dir(), "seed_knowledge")
    if not os.path.isdir(kb_dir):
        _err(f"error: knowledge data not found at {kb_dir}. A wheel install does not include data/. "
             "Run from a checkout, use an editable install (pip install -e .), or set ISOMORPH_DATA_DIR.")
        return 2
    if server_running(cfg):
        _err(f"error: another ISOMORPH server is already using {cfg.home}; use a different --home or stop it")
        return 1
    try:
        cfg = AppConfig(**{**cfg.__dict__, "port": pick_port(cfg.host, cfg.port, args.strict_port)})
        from .app import App
        app = App(cfg)
        server = create_server(app, quiet=not args.verbose)
    except InsecureBind as e:
        _err(f"error: {e}")
        return 2
    except OSError as e:
        _err(f"error: {e}")
        return 1
    shown = "localhost" if is_loopback(cfg.host) else cfg.host
    url = f"http://{shown}:{server.port}/"
    _out(f"ISOMORPH {__version__} running at {url}")
    _out(f"data directory: {cfg.home}")
    if app.recovered:
        _out(f"marked {len(app.recovered)} interrupted run(s) as failed; open them and use rerun to resume")
    if cfg.token:
        _out("API token required (Authorization: Bearer <ISOMORPH_TOKEN>)")
    if not is_loopback(cfg.host):
        _err("warning: this server speaks plain HTTP, so the token travels unencrypted. Put a TLS proxy in front of it.")
    _out("press Ctrl+C to stop")
    _write_lock(cfg, server.port)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    serve_in_thread(server)
    if not args.no_browser and not cfg.token:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        while not stop.wait(0.5):
            pass
    finally:
        _out("shutting down")
        _remove_lock(cfg)
        server.shutdown()
        server.server_close()
        app.close()
    return 0


# ------------------------------------------------------------------ doctor
def run_doctor(cfg: AppConfig) -> List[tuple]:
    """Returns (name, level, detail). level is ok, warn or fail. Never raises."""
    checks: List[tuple] = []

    def add(name, level, detail):
        checks.append((name, level, detail))

    v = sys.version_info
    add("python", "ok" if v >= (3, 9) else "fail", f"{v.major}.{v.minor}.{v.micro}" + ("" if v >= (3, 9) else " (need 3.9 or newer)"))
    # data directory
    try:
        os.makedirs(cfg.home, exist_ok=True)
        probe = tempfile.NamedTemporaryFile(dir=cfg.home, delete=True)
        probe.close()
        add("data directory", "ok", f"{cfg.home} is writable")
        writable = True
    except OSError as e:
        add("data directory", "fail", f"{cfg.home} is not usable: {e.strerror or e}")
        writable = False
    if writable:
        try:
            from services.sqlite_store import SqliteDatabase
            db = SqliteDatabase(cfg.db_path)
            ok = db.integrity_ok()
            add("database", "ok" if ok else "fail", f"{cfg.db_path}, schema {db.schema_version()}, integrity " + ("ok" if ok else "FAILED"))
        except Exception as e:
            add("database", "fail", f"cannot open {cfg.db_path}: {type(e).__name__}: {e}")
    else:
        add("database", "fail", "skipped because the data directory is not usable")
    # knowledge
    try:
        problems, n = validate_knowledge()
        add("knowledge base", "ok" if not problems else "fail",
            f"{n} systems valid" if not problems else f"{len(problems)} problem(s), first: {problems[0]}")
    except Exception as e:
        from knowledge_base.loader import data_dir
        add("knowledge base", "fail", f"cannot load seed data from {data_dir()}: {type(e).__name__}: {e}. "
            "A wheel install has no data/; run from a checkout, use pip install -e ., or set ISOMORPH_DATA_DIR")
    # UI and port
    from .server import STATIC_DEFAULT
    static = cfg.static_dir or STATIC_DEFAULT
    add("web UI", "ok" if os.path.isfile(os.path.join(static, "index.html")) else "warn",
        "bundled" if os.path.isfile(os.path.join(static, "index.html")) else "not bundled, the API still works")
    free = port_free(cfg.host, cfg.port)
    add("port", "ok" if free else "warn", f"{cfg.host}:{cfg.port} is free" if free else f"{cfg.host}:{cfg.port} is busy, serve will pick the next free port")
    if not is_loopback(cfg.host) and not cfg.token:
        add("network", "fail", f"host {cfg.host} is not local and ISOMORPH_TOKEN is not set")
    # optional extras
    import importlib.util
    present = [m for m in ("fastapi", "sqlalchemy", "uvicorn") if importlib.util.find_spec(m)]
    add("optional packages", "ok", ("installed: " + ", ".join(present)) if present else "none installed (not needed)")
    return checks


def cmd_doctor(args) -> int:
    checks = run_doctor(_config(args))
    mark = {"ok": " OK ", "warn": "WARN", "fail": "FAIL"}
    for name, level, detail in checks:
        _out(f"[{mark[level]}] {name}: {detail}")
    failed = [c for c in checks if c[1] == "fail"]
    if failed:
        _err(f"\n{len(failed)} check(s) failed. Fix the items marked FAIL and run `isomorph doctor` again.")
        return 1
    _out("\nAll required checks passed.")
    return 0


def validate_knowledge():
    from knowledge_base import load_domains, load_systems
    systems = load_systems()
    domains = {d["id"] for d in load_domains()["domains"]}
    problems: List[str] = []
    ids = [s.id for s in systems]
    if len(ids) != len(set(ids)):
        problems.append("duplicate system ids")
    for s in systems:
        problems += s.validate()
        if s.domain not in domains:
            problems.append(f"{s.id}: unknown domain {s.domain}")
    return problems, len(systems)


def cmd_validate(args) -> int:
    problems, n = validate_knowledge()
    if problems:
        for p in problems[:50]:
            _err(f"  {p}")
        _err(f"knowledge validation failed: {len(problems)} problem(s) in {n} systems")
        return 1
    _out(f"knowledge OK: {n} systems validated")
    return 0


# ------------------------------------------------------------------ analyze, seed, list
def cmd_analyze(args) -> int:
    if bool(args.text) == bool(args.file):
        _err("error: provide the problem text as an argument or with --file (not both)")
        return 2
    text = args.text
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                text = f.read(60000)
        except (OSError, UnicodeDecodeError) as e:
            _err(f"error: cannot read {args.file}: {e}")
            return 2
    from core.errors import AppError
    app = _open_app(args, synchronous=True)
    fmt = "json" if args.format == "json" else "md"
    try:
        run = app.analyze(text, args.title or "", None)
        if run["status"] != "done":
            _err(f"analysis {run['status']}: {run.get('error')}")
            return 1
        rep = app.report(run["id"], fmt)
    except AppError as e:
        _err(f"error: {e.message}")
        return 2
    finally:
        app.close()
    body = json.dumps(rep, indent=2, sort_keys=True) if fmt == "json" else rep
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(body)
        _err(f"report written to {args.out} (run {run['id']})")
    else:
        _out(body)
        _err(f"run {run['id']} saved")
    return 0


def cmd_seed(args) -> int:
    """Store the bundled demo discovery so a fresh install has something to look at. Idempotent."""
    from core.errors import AppError
    app = _open_app(args, synchronous=True)
    try:
        demo_id = "demo-roller-strip"
        if app.store.get(demo_id) is not None:
            _out(f"demo discovery already present ({demo_id})")
            return 0
        with open(DEMO_PROBLEM, encoding="utf-8") as f:
            spec = json.load(f)
        run = app.orch.create_run(text=spec["statement"], title=spec["title"], run_id=demo_id)
        app.orch.run(run.id)
        status = app.store.get(demo_id).status
        _out(f"demo discovery stored as {demo_id} ({status})")
        return 0 if status == "done" else 1
    except (OSError, KeyError, AppError) as e:
        _err(f"error: {e}")
        return 1
    finally:
        app.close()


def cmd_list(args) -> int:
    app = _open_app(args, synchronous=True)
    try:
        res = app.store.list_runs(limit=100)
    finally:
        app.close()
    if not res["items"]:
        _out("no discoveries yet. Run `isomorph seed` or `isomorph analyze \"...\"`.")
    for r in res["items"]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created_at"]))
        _out(f"{r['id']}  {r['status']:<9} {when}  {r['title'] or '(untitled)'}")
    return 0


# ------------------------------------------------------------------ backup, restore, export, reset
def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def cmd_backup(args) -> int:
    from services.sqlite_store import SqliteDatabase
    cfg = _config(args)
    cfg.ensure_dirs()
    dest = args.dest or os.path.join(cfg.backups_dir, f"isomorph-{_timestamp()}.db")
    try:
        SqliteDatabase(cfg.db_path).backup_to(dest)
    except FileExistsError:
        _err(f"error: {dest} already exists")
        return 1
    except OSError as e:
        _err(f"error: backup failed: {e}")
        return 1
    _out(f"backup written to {dest}")
    return 0


def cmd_restore(args) -> int:
    from services.sqlite_store import SchemaTooNew, SqliteDatabase
    cfg = _config(args)
    cfg.ensure_dirs()
    if _refuse_if_serving(cfg, "restore", args.force):
        return 1
    db = SqliteDatabase(cfg.db_path)
    if not _confirm(f"Replace the current database in {cfg.home} with {args.source}? A safety backup is made first.", args.yes):
        return 1
    try:
        safety = db.backup_to(os.path.join(cfg.backups_dir, f"before-restore-{_timestamp()}.db"))
        db.restore_from(args.source)
    except (OSError, ValueError, SchemaTooNew) as e:
        _err(f"error: restore failed, current data is unchanged: {e}")
        return 1
    _out(f"restored from {args.source} (previous data saved as {safety})")
    return 0


def cmd_export(args) -> int:
    app = _open_app(args, synchronous=True)
    try:
        runs = []
        for rid in app.store.all_ids():
            r = app.store.get(rid)
            runs.append({"run": r.to_dict(), "annotations": app.annotations.list(rid)})
    finally:
        app.close()
    doc = {"isomorph_export": 1, "version": __version__, "exported_at": time.time(), "runs": runs}
    body = json.dumps(doc, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(body)
        _err(f"exported {len(runs)} discovery(ies) to {args.out}")
    else:
        _out(body)
    return 0


def cmd_reset(args) -> int:
    from services.sqlite_store import SqliteDatabase
    cfg = _config(args)
    if not os.path.exists(cfg.db_path):
        _out("nothing to reset")
        return 0
    if _refuse_if_serving(cfg, "reset", args.force):
        return 1
    if not _confirm(f"Delete ALL discoveries and notes in {cfg.home}?", args.yes):
        return 1
    db = SqliteDatabase(cfg.db_path)
    if not args.no_backup:
        cfg.ensure_dirs()
        _out(f"backup saved as {db.backup_to(os.path.join(cfg.backups_dir, f'before-reset-{_timestamp()}.db'))}")
    with db.connection() as c:
        c.execute("DELETE FROM annotations")
        c.execute("DELETE FROM runs")
    _out("all discoveries and notes deleted")
    return 0


def cmd_version(args) -> int:
    _out(f"isomorph {__version__} (python {sys.version.split()[0]})")
    return 0


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", help="data directory (default: $ISOMORPH_HOME or ~/.isomorph)")
    p = argparse.ArgumentParser(prog="isomorph", description="ISOMORPH cross-domain structural discovery. Runs with the Python standard library only.")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    s = sub.add_parser("serve", parents=[common], help="start the web app and API")
    s.add_argument("--host", help="bind address (default 127.0.0.1; non-local needs ISOMORPH_TOKEN)")
    s.add_argument("--port", type=int, help=f"port (default {DEFAULT_PORT}, next free port is used if busy)")
    s.add_argument("--strict-port", action="store_true", help="fail instead of picking another port")
    s.add_argument("--no-browser", action="store_true", help="do not open a browser")
    s.add_argument("--verbose", action="store_true", help="log every request")
    s.set_defaults(fn=cmd_serve)

    d = sub.add_parser("doctor", parents=[common], help="check that this install works")
    d.add_argument("--host")
    d.add_argument("--port", type=int)
    d.set_defaults(fn=cmd_doctor)

    a = sub.add_parser("analyze", parents=[common], help="analyze a problem and print a report")
    a.add_argument("text", nargs="?", help="problem description")
    a.add_argument("--file", "-f", help="read the problem description from a file")
    a.add_argument("--title", help="report title")
    a.add_argument("--format", choices=("md", "json"), default="md")
    a.add_argument("--out", "-o", help="write the report to this file")
    a.set_defaults(fn=cmd_analyze)

    sub.add_parser("seed", parents=[common], help="store the bundled demo discovery").set_defaults(fn=cmd_seed)
    sub.add_parser("validate", parents=[common], help="validate the seed knowledge base").set_defaults(fn=cmd_validate)
    sub.add_parser("list", parents=[common], help="list stored discoveries").set_defaults(fn=cmd_list)

    b = sub.add_parser("backup", parents=[common], help="write a consistent backup of the database")
    b.add_argument("dest", nargs="?", help="backup file (default: <home>/backups/isomorph-<time>.db)")
    b.set_defaults(fn=cmd_backup)

    r = sub.add_parser("restore", parents=[common], help="replace the database with a backup")
    r.add_argument("source", help="backup file")
    r.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    r.add_argument("--force", action="store_true", help="skip the check for a running server")
    r.set_defaults(fn=cmd_restore)

    e = sub.add_parser("export", parents=[common], help="export every discovery and note as JSON")
    e.add_argument("--out", "-o", help="output file (default: stdout)")
    e.set_defaults(fn=cmd_export)

    x = sub.add_parser("reset", parents=[common], help="delete all discoveries and notes (backs up first)")
    x.add_argument("--yes", "-y", action="store_true")
    x.add_argument("--no-backup", action="store_true")
    x.add_argument("--force", action="store_true", help="skip the check for a running server")
    x.set_defaults(fn=cmd_reset)

    sub.add_parser("version", help="print the version").set_defaults(fn=cmd_version)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
