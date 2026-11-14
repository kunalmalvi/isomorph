from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import Conflict
from database.models import Project, ProjectMember, User
from ..deps import current_user, get_db, load_project, page, pagination, row_dict

router = APIRouter(prefix="/archive", tags=["archive"])


@router.get("")
def list_archived(db: Session = Depends(get_db), user: User = Depends(current_user), p: dict = Depends(pagination)):
    stmt = (select(Project).join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None), Project.archived_at.is_not(None))
            .order_by(Project.archived_at.desc(), Project.id))
    return page(db, stmt, p, lambda r: row_dict(r, ("deleted_at",)))


@router.post("/{project_id}")
def archive_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj, _ = load_project(db, user, project_id, "owner")
    if proj.archived_at is not None:
        raise Conflict("project is already archived")
    proj.archived_at = datetime.now(timezone.utc)
    db.commit()
    return row_dict(proj, ("deleted_at",))


@router.post("/{project_id}/restore")
def restore_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    proj, _ = load_project(db, user, project_id, "owner")
    if proj.archived_at is None:
        raise Conflict("project is not archived")
    proj.archived_at = None
    db.commit()
    return row_dict(proj, ("deleted_at",))
