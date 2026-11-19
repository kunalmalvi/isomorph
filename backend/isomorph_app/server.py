"""Stdlib HTTP server: JSON API under /api/v1 plus the bundled web UI. Stdlib only.

The API mirrors docs/api-contracts.md for the pieces the single-user app needs (discoveries, stages, annotations,
knowledge, reports, health, settings). Multi-user resources (projects, members, auth) are not part of this runtime.

Safety: binds to 127.0.0.1 by default and refuses a non-loopback bind without ISOMORPH_TOKEN. Request bodies are
size limited, static files are served from one directory with path traversal protection, and every error uses the
documented envelope.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import sys
import threading
from email.parser import BytesParser
from email import policy as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

from core.errors import AppError, Forbidden, NotFound, PayloadTooLarge, Unauthorized, ValidationFailed, error_envelope
from core.rate_limit import RateLimiter
from core.sse import format_sse, parse_last_event_id, progress_stream
from intelligence.schemas import ROLES
from services.annotations import DECISIONS

from . import __version__
from .app import App, knowledge_summary
from .config import AppConfig, is_loopback

API = "/api/v1"
STATIC_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_FALLBACK_PAGE = b"""<!doctype html><meta charset="utf-8"><title>ISOMORPH</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto"><h1>ISOMORPH</h1>
<p>The API is running. The bundled web UI was not found in this install.</p>
<p>Try <a href="/api/v1/health">/api/v1/health</a>.</p></body>"""


CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
AUTH_FAILURES_PER_MINUTE = 10


def _host_only(value: str) -> str:
    """Host name from a Host header value: drops the port and IPv6 brackets, lower case."""
    v = (value or "").strip().lower()
    if v.startswith("["):
        return v[1:].split("]", 1)[0]
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


class InsecureBind(RuntimeError):
    pass


def _check_bind(config: AppConfig) -> None:
    if not is_loopback(config.host) and not config.token:
        raise InsecureBind(f"refusing to bind {config.host} without ISOMORPH_TOKEN; set a token or use 127.0.0.1")


class Handler(BaseHTTPRequestHandler):
    server_version = f"ISOMORPH/{__version__}"
    protocol_version = "HTTP/1.1"
    timeout = 30

    # ------------------------------------------------------------------ plumbing
    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        if getattr(self.server, "quiet", True):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload=None) -> None:
        if status == 204:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send(status, json.dumps(payload, sort_keys=True).encode(), "application/json; charset=utf-8")

    def _error(self, e: AppError) -> None:
        self._json(e.status, e.envelope())

    def _read_json(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise AppError("chunked request bodies are not supported", code="bad_request", status=411)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValidationFailed("invalid Content-Length")
        if n < 0:
            raise ValidationFailed("invalid Content-Length")
        if n > self.app.config.max_body_bytes:
            self.close_connection = True  # body is not read, so the connection cannot be reused
            raise PayloadTooLarge(f"request body exceeds {self.app.config.max_body_bytes} bytes")
        if n == 0:
            return {}
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            self.close_connection = True  # body is not read
            raise AppError("Content-Type must be application/json", code="unsupported_media_type", status=415)
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationFailed("request body must be valid JSON")
        if not isinstance(body, dict):
            raise ValidationFailed("request body must be a JSON object")
        return body

    def _read_upload(self, q: dict):
        """Raw body with ?filename=, or multipart/form-data with one file part. Returns (filename, bytes)."""
        if self.headers.get("Transfer-Encoding"):
            raise AppError("chunked request bodies are not supported", code="bad_request", status=411)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValidationFailed("invalid Content-Length")
        if n <= 0:
            raise ValidationFailed("upload body is empty")
        if n > self.app.config.max_body_bytes:
            self.close_connection = True
            raise PayloadTooLarge(f"request body exceeds {self.app.config.max_body_bytes} bytes")
        raw = self.rfile.read(n)
        ctype = self.headers.get("Content-Type") or ""
        if ctype.lower().startswith("multipart/form-data"):
            msg = BytesParser(policy=email_policy.HTTP).parsebytes(
                b"Content-Type: " + ctype.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
            for part in msg.iter_parts() if msg.is_multipart() else []:
                fn = part.get_filename()
                if fn:
                    return fn, part.get_payload(decode=True) or b""
            raise ValidationFailed("multipart body has no file part")
        return q.get("filename") or "", raw

    def _check_origin(self) -> None:
        """Defence against DNS rebinding and cross-site requests to a local server.

        Without a token, only loopback names and the configured host are accepted in Host. A browser Origin header
        must always match the Host the request was sent to (the bundled UI is same origin).
        """
        host = self.headers.get("Host") or ""
        if not self.app.config.token:
            allowed = set(LOCAL_HOSTS) | {self.app.config.host.lower()}
            if _host_only(host) not in allowed:
                raise Forbidden("Host header not allowed; use localhost or set ISOMORPH_TOKEN")
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc.lower() != host.strip().lower():
            raise Forbidden("cross-origin requests are not allowed")

    def _check_auth(self) -> None:
        token = self.app.config.token
        if not token:
            return
        ip = self.client_address[0]
        limiter = self.server.auth_limiter  # type: ignore[attr-defined]
        if limiter.remaining(ip) == 0:
            raise AppError("too many failed attempts, try again later", code="rate_limited", status=429)
        h = self.headers.get("Authorization") or ""
        given = h[7:] if h.lower().startswith("bearer ") else ""
        if not given:
            raise Unauthorized("missing bearer token")
        if not hmac.compare_digest(given.encode(), token.encode()):
            limiter.check(ip)  # only failures are counted
            raise Unauthorized("invalid bearer token")

    # ------------------------------------------------------------------ dispatch
    def do_HEAD(self):
        self._dispatch()

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def _dispatch(self) -> None:
        parts = urlsplit(self.path)
        path, query = parts.path, {k: v[-1] for k, v in parse_qs(parts.query).items()}
        try:
            self._check_origin()
            if path == API or path.startswith(API + "/"):
                sub = path[len(API):] or "/"
                if sub != "/health":
                    self._check_auth()
                self._route(self.command, sub.rstrip("/") or "/", query)
            elif self.command in ("GET", "HEAD"):
                self._static(path)
            else:
                raise AppError("method not allowed", code="method_not_allowed", status=405)
        except AppError as e:
            self._error(e)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as e:  # never leak internals to the client
            sys.stderr.write(f"internal error on {self.command} {path}: {type(e).__name__}: {e}\n")
            try:
                self._json(500, error_envelope("internal_error", "internal server error"))
            except OSError:
                self.close_connection = True

    # ------------------------------------------------------------------ static files
    def _static(self, path: str) -> None:
        root = os.path.realpath(self.app.config.static_dir or STATIC_DEFAULT)
        rel = unquote(path)
        if "\x00" in rel or "\\" in rel:
            raise NotFound("not found")
        target = os.path.realpath(os.path.join(root, rel.lstrip("/")))
        if target != root and not target.startswith(root + os.sep):
            raise NotFound("not found")
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            # single page app: unknown paths without an extension serve the UI shell
            index = os.path.join(root, "index.html")
            if "." not in os.path.basename(rel) and os.path.isfile(index):
                target = index
            elif rel in ("", "/") or "." not in os.path.basename(rel):
                self._send(200, _FALLBACK_PAGE, "text/html; charset=utf-8")
                return
            else:
                raise NotFound("not found")
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(target, "rb") as f:
            self._send(200, f.read(), ctype)

    # ------------------------------------------------------------------ API routes
    def _route(self, method: str, path: str, q: dict) -> None:
        app = self.app
        if method == "HEAD":
            method = "GET"
        m = _match

        if path == "/health" and method == "GET":
            return self._json(200, app.health())
        if path == "/settings" and method == "GET":
            s = app.settings
            return self._json(200, {"version": __version__, "provider": s.ai_provider, "home": app.config.home,
                                    "auth_required": bool(app.config.token), "max_body_bytes": app.config.max_body_bytes,
                                    "knowledge": knowledge_summary(app.kb), "decisions": list(DECISIONS), "roles": list(ROLES)})

        # knowledge (read only)
        if path == "/domains" and method == "GET":
            counts = {}
            for s in app.kb.systems:
                counts[s.domain] = counts.get(s.domain, 0) + 1
            items = [dict(d, system_count=counts.get(d["id"], 0)) for d in app.kb.domains_doc["domains"]]
            return self._json(200, _page(items, q))
        if path in ("/knowledge-systems", "/mechanisms") and method == "GET":
            dom, text = q.get("domain"), (q.get("q") or "").lower()
            only_mech = path == "/mechanisms"
            items = [s for s in app.kb.systems if (not only_mech or s.id in app.kb.mechanism_ids)
                     and (not dom or s.domain == dom) and (not text or text in (s.name + " " + s.summary).lower())]
            return self._json(200, _page([_system_summary(s) for s in items], q))
        g = m(r"/knowledge-systems/([A-Za-z0-9_.:-]{1,100})", path)
        if g and method == "GET":
            s = app.kb.by_id.get(g[0])
            if s is None:
                raise NotFound("knowledge system not found")
            return self._json(200, s.to_dict())

        # learning loop (evidence, gated cycles, versions, rollback). No AI call is made by any of these.
        if path == "/learning" and method == "GET":
            return self._json(200, app.learning.status())
        if path == "/learning/versions" and method == "GET":
            return self._json(200, app.learning.versions())
        if path == "/learning/corrections" and method == "POST":
            body = self._read_json()
            rid = body.get("run_id")
            if rid is not None and not isinstance(rid, str):
                raise ValidationFailed("run_id must be a string")
            term = body.get("term", body.get("entity_label"))
            note = body.get("note") or ""
            if not isinstance(note, str) or len(note) > 1000:
                raise ValidationFailed("note must be a string of at most 1000 characters")
            return self._json(201, app.correct_role(rid, term, body.get("role"), note))
        if path == "/learning/cycle" and method == "POST":
            self._read_json()
            return self._json(200, app.learning.cycle())
        if path == "/learning/rollback" and method == "POST":
            to = self._read_json().get("to")
            if to is not None and not isinstance(to, str):
                raise ValidationFailed("to must be a version id string")
            return self._json(200, app.learning.rollback(to))

        # uploads
        if path == "/uploads" and method == "POST":
            name, data = self._read_upload(q)
            if not name:
                raise ValidationFailed("filename is required (?filename= or a multipart file part)")
            return self._json(201, app.upload(name, data, q.get("interpret") or None))

        # discoveries
        if path == "/discoveries" and method == "POST":
            body = self._read_json()
            cfg = dict(body.get("config") or {})
            for k in ("weights", "threshold", "top_k"):
                if k in body and body[k] is not None:
                    cfg[k] = body[k]
            if "provider" in body and body["provider"]:
                cfg["provider"] = body["provider"]
            title = body.get("title") or ""
            if not isinstance(title, str) or len(title) > 200:
                raise ValidationFailed("title must be a string of at most 200 characters")
            upload_id = body.get("upload_id")
            if upload_id is not None:
                if not isinstance(upload_id, str) or not re.fullmatch(r"[0-9a-f]{64}", upload_id):
                    raise ValidationFailed("upload_id must be a 64 character sha256 hex digest")
                if body.get("text") is not None or body.get("problem") is not None:
                    raise ValidationFailed("provide exactly one of text, problem or upload_id")
                return self._json(202, app.start_run_from_upload(upload_id, title=title, config=cfg))
            text = body.get("text")
            if text is not None and (not isinstance(text, str) or len(text) > 50000):
                raise ValidationFailed("text must be a string of at most 50000 characters")
            return self._json(202, app.start_run(text=text, problem=body.get("problem"), title=title, config=cfg))
        if path == "/discoveries" and method == "GET":
            lim, off = _paging(q)
            status = q.get("status")
            return self._json(200, app.store.list_runs(lim, off, status if status in ("queued", "running", "done", "failed", "cancelled") else None))
        g = m(r"/discoveries/([A-Za-z0-9_-]{1,64})", path)
        if g:
            if method == "GET":
                run = app.require_run(g[0])
                return self._json(200, run.to_dict(include_output=q.get("outputs") in ("1", "true")))
            if method == "DELETE":
                app.delete_run(g[0])
                return self._json(204)
        g = m(r"/discoveries/([A-Za-z0-9_-]{1,64})/(stages|matches|cancel|resume|events|report|annotations)", path)
        if g:
            rid, what = g
            if what == "stages" and method == "GET":
                return self._json(200, {"items": [s.to_dict(False) for s in app.require_run(rid).stages.values()]})
            if what == "matches" and method == "GET":
                out = app.require_run(rid).stages["structural_matching"].output or {}
                return self._json(200, _page(out.get("matches", []), q))
            if what == "cancel" and method == "POST":
                return self._json(202, app.cancel(rid))
            if what == "resume" and method == "POST":
                return self._json(202, app.resume(rid))
            if what == "events" and method == "GET":
                return self._events(rid)
            if what == "report" and method == "GET":
                fmt = q.get("format", "md")
                if fmt not in ("md", "json"):
                    raise ValidationFailed("format must be md or json")
                rep = app.report(rid, fmt)
                if fmt == "json":
                    return self._send(200, json.dumps(rep, sort_keys=True).encode(), "application/json; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="report-{rid}.json"'})
                return self._send(200, rep.encode(), "text/markdown; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="report-{rid}.md"'})
            if what == "annotations" and method == "GET":
                return self._json(200, {"items": app.visible_annotations(rid)})
        g = m(r"/discoveries/([A-Za-z0-9_-]{1,64})/stages/([a-z_]{1,40})", path)
        if g:
            rid, stage = g
            if method == "GET":
                app.require_run(rid)
                return self._json(200, app.orch.get_stage(rid, stage).to_dict())
            if method == "PUT":
                body = self._read_json()
                if "output" not in body:
                    raise ValidationFailed("body must contain 'output'")
                app.require_run(rid)
                run = app.edit_stage(rid, stage, body["output"])
                return self._json(200, run.stages[stage].to_dict(False))
        g = m(r"/discoveries/([A-Za-z0-9_-]{1,64})/stages/([a-z_]{1,40})/rerun", path)
        if g and method == "POST":
            return self._json(202, app.rerun(g[0], g[1], q.get("mode", "downstream")))
        g = m(r"/discoveries/([A-Za-z0-9_-]{1,64})/annotations/([A-Za-z0-9_.:-]{1,128})", path)
        if g:
            rid, hid = g
            if method == "PUT":
                body = self._read_json()
                if hid not in app.hypothesis_ids(rid):
                    raise NotFound("hypothesis not found in this discovery")
                return self._json(200, app.set_annotation(rid, hid, body.get("decision", "none"), body.get("note", "")))
            if method == "DELETE":
                app.require_run(rid)
                app.annotations.delete(rid, hid)
                return self._json(204)
        raise NotFound("endpoint not found")

    def _events(self, run_id: str) -> None:
        app = self.app
        app.require_run(run_id)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        last = parse_last_event_id(self.headers.get("Last-Event-ID"))

        def snapshot():
            run = app.store.get(run_id)
            return run.progress() if run else None
        try:
            for chunk in progress_stream(snapshot, interval=0.5, max_seconds=app.config.sse_max_seconds, last_event_id=last):
                self.wfile.write(chunk.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass


def _match(pattern: str, path: str):
    r = re.fullmatch(pattern, path)
    return r.groups() if r else None


def _paging(q: dict):
    try:
        lim, off = int(q.get("limit", 20)), int(q.get("offset", 0))
    except ValueError:
        raise ValidationFailed("limit and offset must be integers")
    if not 1 <= lim <= 100 or off < 0:
        raise ValidationFailed("limit must be 1..100 and offset 0 or more")
    return lim, off


def _page(items: list, q: dict) -> dict:
    lim, off = _paging(q)
    return {"items": items[off:off + lim], "total": len(items), "limit": lim, "offset": off}


def _system_summary(s) -> dict:
    return {"id": s.id, "name": s.name, "domain": s.domain, "kind": s.kind, "summary": s.summary, "confidence": s.confidence,
            "node_count": len(s.graph.nodes), "edge_count": len(s.graph.edges),
            "sources": [x.to_dict() if hasattr(x, "to_dict") else x for x in s.sources]}


class IsomorphServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, app: App, host: str, port: int, quiet: bool = True):
        self.app = app
        self.quiet = quiet
        self.auth_limiter = RateLimiter(AUTH_FAILURES_PER_MINUTE, 60.0)
        super().__init__((host, port), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]


def create_server(app: App, quiet: bool = True) -> IsomorphServer:
    _check_bind(app.config)
    return IsomorphServer(app, app.config.host, app.config.port, quiet)


def serve_in_thread(server: IsomorphServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True, name="isomorph-http")
    t.start()
    return t
