"""FastAPI application factory. UNVERIFIED in the authoring sandbox (FastAPI is not installable there)."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_providers import get_provider
from core.config import Settings, load_settings
from core.errors import AppError, TooManyRequests, error_envelope
from core.rate_limit import RateLimiter
from core.uploads import cleanup_uploads
from database.session import make_engine, make_session_factory
from services.annotations import InMemoryAnnotationStore, JsonFileAnnotationStore
from services.knowledge import default_knowledge
from services.orchestrator import Orchestrator
from workers.job_runner import JobRunner
from workers.recovery import recover_interrupted_runs

from .db_store import SqlRunStore
from .deps import api_rate_limit
from .routers import (archive, auth, discoveries, knowledge, matches, pipeline, problems, projects, reports, settings as settings_router,
                      structural)

API_PREFIX = "/api/v1"


def _cleanup_orphan_annotations(store, session_factory, uploads_dir: Optional[str] = None) -> None:
    """Remove annotation files whose discovery is gone or whose project was deleted. Never blocks startup."""
    try:
        from sqlalchemy import select
        from database.models import DiscoverySession, Problem
        # Soft deleted rows still exist, so their notes and uploads are kept. Only rows that are gone count as orphans.
        with session_factory() as db:
            live = [str(i) for i in db.execute(select(DiscoverySession.id)).scalars().all()]
            live_problems = [str(i) for i in db.execute(select(Problem.id)).scalars().all()]
        log = logging.getLogger(__name__)
        removed = store.safe_cleanup_orphans(live)  # skipped when the database has no runs
        if removed:
            log.info("removed annotations of %d orphaned runs", len(removed))
        elif not live:
            log.info("annotation sweep skipped: no discovery runs in the database")
        if uploads_dir:
            gone = cleanup_uploads(uploads_dir, live_problems)
            if gone:
                log.info("removed uploads of %d orphaned problems", len(gone))
    except Exception:  # tables may not exist yet (create_tables or migrations pending)
        logging.getLogger(__name__).warning("annotation cleanup skipped", exc_info=True)


def create_app(settings: Optional[Settings] = None, session_factory=None, synchronous_jobs: bool = False,
               create_tables: bool = False) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="ISOMORPH API", version="0.1.0", openapi_url=f"{API_PREFIX}/openapi.json", docs_url=f"{API_PREFIX}/docs")
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.database_url))
    if create_tables:  # tests and quick local runs only. Real deployments use `alembic upgrade head`.
        from database.base import Base
        import database.models  # noqa: F401
        Base.metadata.create_all(session_factory.kw["bind"])
    kb = default_knowledge(settings.data_dir)
    orch = Orchestrator(SqlRunStore(session_factory), kb, provider_factory=lambda name: get_provider(settings, name))
    if settings.recover_interrupted_runs:  # disable when running more than one API process
        recover_interrupted_runs(orch.store)  # runs left queued or running by a previous process can never finish
    app.state.annotations = (JsonFileAnnotationStore(os.path.join(settings.state_dir, "annotations")) if settings.state_dir
                             else InMemoryAnnotationStore())
    _cleanup_orphan_annotations(app.state.annotations, session_factory,
                               os.path.join(settings.state_dir, "uploads") if settings.state_dir else None)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.kb = kb
    app.state.orchestrator = orch
    app.state.jobs = JobRunner(orch, settings.worker_threads, synchronous=synchronous_jobs)
    app.state.api_limiter = RateLimiter(settings.api_requests_per_minute, 60.0)
    app.state.auth_limiter = RateLimiter(settings.auth_attempts_per_minute, 60.0)

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"Retry-After": str(int(getattr(exc, "retry_after", 1)) + 1)} if isinstance(exc, TooManyRequests) else None
        return JSONResponse(exc.envelope(), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(error_envelope("validation_error", "request validation failed", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(exc.status_code, "http_error")
        return JSONResponse(error_envelope(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):  # never leak internals
        return JSONResponse(error_envelope("internal_error", "internal server error"), status_code=500)

    @app.get(f"{API_PREFIX}/health", tags=["health"])
    def health():
        return {"status": "ok"}

    guard = [Depends(api_rate_limit)]
    app.include_router(auth.router, prefix=API_PREFIX)
    for r in (projects, problems, discoveries, structural, knowledge, matches, pipeline, archive, reports, settings_router):
        app.include_router(r.router, prefix=API_PREFIX, dependencies=guard)
    return app
