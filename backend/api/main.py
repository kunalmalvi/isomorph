"""FastAPI application factory. UNVERIFIED in the authoring sandbox (FastAPI is not installable there)."""
from __future__ import annotations

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
from database.session import make_engine, make_session_factory
from services.knowledge import default_knowledge
from services.orchestrator import Orchestrator
from workers.job_runner import JobRunner

from .db_store import SqlRunStore
from .deps import api_rate_limit
from .routers import (archive, auth, discoveries, knowledge, matches, pipeline, problems, projects, reports, settings as settings_router,
                      structural)

API_PREFIX = "/api/v1"


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
