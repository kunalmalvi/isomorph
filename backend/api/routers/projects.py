from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import Conflict, NotFound, ValidationFailed
from database.models import DiscoverySession, Project, ProjectMember, User
from ..deps import current_user, get_db, load_project, page, pagination, row_dict
from ..schemas import MemberIn, ProjectIn, ProjectPatch

router = APIRouter(prefix="/projects", tags=["projects"])


def _out(p: Project, role: str) -> dict:
    d = row_dict(p, ("deleted_at",))
    d["role"] = role
    return d


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user), p: dict = Depends(pagination)):
    stmt = (select(Project, ProjectMember.role).join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None), Project.archived_at.is_(None))
            .order_by(Project.created_at.desc(), Project.id))
    from sqlalchemy import func
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.limit(p["limit"]).offset(p["offset"])).all()
    return {"items": [_out(pr, role) for pr, role in rows], "total": total, "limit": p["limit"], "offset": p["offset"]}


@router.post("", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj = Project(name=body.name, description=body.description, created_by=user.id)
    db.add(proj)
    db.flush()
    db.add(ProjectMember(project_id=proj.id, user_id=user.id, role="owner"))
    db.commit()
    return _out(proj, "owner")


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj, role = load_project(db, user, project_id)
    return _out(proj, role)


@router.patch("/{project_id}")
def update_project(project_id: uuid.UUID, body: ProjectPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj, role = load_project(db, user, project_id, "editor")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k == "name":
            raise ValidationFailed("name cannot be null")
        setattr(proj, k, v)
    db.commit()
    return _out(proj, role)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj, _ = load_project(db, user, project_id, "owner")
    proj.deleted_at = datetime.now(timezone.utc)  # soft delete
    run_ids = [str(i) for i in db.execute(select(DiscoverySession.id).where(DiscoverySession.project_id == project_id)).scalars()]
    db.commit()
    for rid in run_ids:  # reviewer notes are not reachable once the project is gone; do not leave them on disk
        request.app.state.annotations.purge_run(rid)
    return Response(status_code=204)


@router.get("/{project_id}/members")
def list_members(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user), p: dict = Depends(pagination)):
    load_project(db, user, project_id)
    stmt = select(ProjectMember).where(ProjectMember.project_id == project_id).order_by(ProjectMember.created_at, ProjectMember.id)
    return page(db, stmt, p, lambda m: {"user_id": str(m.user_id), "project_id": str(m.project_id), "role": m.role})


@router.post("/{project_id}/members", status_code=201)
def add_member(project_id: uuid.UUID, body: MemberIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_project(db, user, project_id, "owner")
    target = db.get(User, body.user_id) if body.user_id else \
        db.execute(select(User).where(User.email == (body.email or "").strip().lower())).scalar_one_or_none()
    if target is None or not target.is_active:
        raise NotFound("user not found")
    m = ProjectMember(project_id=project_id, user_id=target.id, role=body.role)
    db.add(m)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("user is already a member")
    return {"user_id": str(m.user_id), "project_id": str(project_id), "role": m.role}


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(project_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_project(db, user, project_id, "owner")
    m = db.execute(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise NotFound("member not found")
    if m.role == "owner":
        owners = db.execute(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.role == "owner")).scalars().all()
        if len(owners) <= 1:
            raise Conflict("a project must keep at least one owner")
    db.delete(m)
    db.commit()
    return Response(status_code=204)
