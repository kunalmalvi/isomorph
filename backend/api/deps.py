"""Request dependencies: DB session, authentication, rate limiting, ownership and RBAC checks.

Isolation rule: a user can only see rows of projects they are a member of. A project the user cannot see answers
404 (not 403), so existence is not leaked. A member with too low a role gets 403.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterator, Optional, Type

from fastapi import Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import Forbidden, NotFound, TooManyRequests, Unauthorized
from core.rate_limit import client_key
from core.security import TokenError, decode_token, role_allows
from database.models import Project, ProjectMember, User


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _client_key(request: Request) -> str:
    peer = request.client.host if request.client else None
    return client_key(peer, request.headers.get("x-forwarded-for"), request.app.state.settings.trusted_proxies)


def api_rate_limit(request: Request) -> None:
    ok, retry = request.app.state.api_limiter.check(_client_key(request))
    if not ok:
        raise TooManyRequests(retry_after=retry)


def auth_rate_limit(request: Request) -> None:
    ok, retry = request.app.state.auth_limiter.check(_client_key(request))
    if not ok:
        raise TooManyRequests("too many authentication attempts", retry_after=retry)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("missing bearer token")
    try:
        claims = decode_token(token, request.app.state.settings.secret_key)
        uid = uuid.UUID(claims["sub"])
    except (TokenError, ValueError):
        raise Unauthorized("invalid or expired token")
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise Unauthorized("invalid or expired token")
    return user


def pagination(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    return {"limit": limit, "offset": offset}


def page(db: Session, stmt, p: dict, serialize=lambda x: x) -> dict:
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.limit(p["limit"]).offset(p["offset"])).scalars().all()
    return {"items": [serialize(r) for r in rows], "total": total, "limit": p["limit"], "offset": p["offset"]}


def member_role(db: Session, user: User, project_id: uuid.UUID) -> Optional[str]:
    return db.execute(select(ProjectMember.role).where(ProjectMember.project_id == project_id,
                                                       ProjectMember.user_id == user.id)).scalar_one_or_none()


def load_project(db: Session, user: User, project_id: uuid.UUID, minimum: str = "viewer", for_update: bool = False) -> tuple:
    proj = db.get(Project, project_id)
    role = member_role(db, user, project_id) if proj is not None and proj.deleted_at is None else None
    if role is None:
        raise NotFound("project not found")
    if not role_allows(role, minimum):
        raise Forbidden(f"requires project role {minimum} or higher")
    return proj, role


def load_owned(db: Session, user: User, model: Type[Any], row_id: uuid.UUID, minimum: str = "viewer", what: str = "resource"):
    """Load a row that has project_id, enforcing membership and role. Soft deleted rows are hidden."""
    row = db.get(model, row_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise NotFound(f"{what} not found")
    load_project(db, user, row.project_id, minimum)  # raises NotFound or Forbidden
    return row


def load_problem(db: Session, user: User, problem_id: uuid.UUID, minimum: str = "viewer"):
    from database.models import Problem
    return load_owned(db, user, Problem, problem_id, minimum, "problem")


def visible_project_ids(user: User):
    """Projects the user belongs to, excluding soft deleted and archived ones (archived projects are listed under /archive)."""
    return (select(ProjectMember.project_id).join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None), Project.archived_at.is_(None)))


def row_dict(row: Any, exclude: tuple = ()) -> dict:
    """Generic ORM row to JSON friendly dict (UUID and datetime become strings)."""
    from sqlalchemy import inspect
    out = {}
    for attr in inspect(row).mapper.column_attrs:
        if attr.key in exclude or attr.key == "password_hash":
            continue
        v = getattr(row, attr.key)
        key = "metadata" if attr.key == "meta" else attr.key
        out[key] = str(v) if isinstance(v, uuid.UUID) else (v.isoformat() if hasattr(v, "isoformat") else v)
    return out
