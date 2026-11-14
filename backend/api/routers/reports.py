from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFound
from database.models import DiscoverySession, Report, User
from services.reports import build_report, report_markdown
from ..deps import current_user, get_db, load_owned, load_project, page, pagination, row_dict, visible_project_ids
from ..schemas import ReportIn

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(project_id: Optional[uuid.UUID] = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user),
                 p: dict = Depends(pagination)):
    stmt = select(Report).where(Report.deleted_at.is_(None), Report.project_id.in_(visible_project_ids(user)))
    if project_id:
        stmt = stmt.where(Report.project_id == project_id)
    return page(db, stmt.order_by(Report.created_at.desc(), Report.id), p, lambda r: row_dict(r, ("deleted_at", "content")))


@router.post("", status_code=201)
def create_report(body: ReportIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_project(db, user, body.project_id, "editor")
    s = db.get(DiscoverySession, body.discovery_session_id)
    if s is None or s.deleted_at is not None or s.project_id != body.project_id:
        raise NotFound("discovery not found in this project")
    run = request.app.state.orchestrator.store.get(str(s.id))
    row = Report(project_id=body.project_id, discovery_session_id=s.id, title=body.title, content=build_report(body.title, run.to_dict()),
                 created_by=user.id)
    db.add(row)
    db.commit()
    return row_dict(row, ("deleted_at",))


@router.get("/{report_id}")
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, Report, report_id, "viewer", "report"), ("deleted_at",))


@router.get("/{report_id}/export")
def export_report(report_id: uuid.UUID, format: Literal["md", "json"] = Query("md"), db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    r = load_owned(db, user, Report, report_id, "viewer", "report")
    if format == "json":
        return JSONResponse(r.content, headers={"Content-Disposition": f'attachment; filename="report-{r.id}.json"'})
    return PlainTextResponse(report_markdown(r.content), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="report-{r.id}.md"'})
