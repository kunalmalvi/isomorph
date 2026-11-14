from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import CandidateMatch, User
from ..deps import current_user, get_db, load_owned, page, pagination, row_dict, visible_project_ids

router = APIRouter(prefix="/matches", tags=["matches"])


def _summary(m: CandidateMatch) -> dict:
    b = m.breakdown or {}
    return {"id": str(m.id), "discovery_session_id": str(m.discovery_session_id), "rank": m.rank, "system_key": m.system_key,
            "system_name": b.get("system_name"), "domain": b.get("domain"), "score": m.score, "domain_distance": m.domain_distance}


@router.get("")
def list_matches(discovery_id: Optional[uuid.UUID] = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user),
                 p: dict = Depends(pagination)):
    stmt = select(CandidateMatch).where(CandidateMatch.project_id.in_(visible_project_ids(user)))
    if discovery_id:
        stmt = stmt.where(CandidateMatch.discovery_session_id == discovery_id)
    return page(db, stmt.order_by(CandidateMatch.discovery_session_id, CandidateMatch.rank), p, _summary)


@router.get("/{match_id}")
def get_match(match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = load_owned(db, user, CandidateMatch, match_id, "viewer", "match")
    return dict(_summary(m), breakdown=m.breakdown)


@router.get("/{match_id}/breakdown")
def get_breakdown(match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = load_owned(db, user, CandidateMatch, match_id, "viewer", "match")
    b = m.breakdown or {}
    return {"total": m.score, "components": b.get("components", {}), "domain_distance": m.domain_distance,
            "differences": b.get("differences", []), "limitations": b.get("limitations", []), "flags": b.get("flags", [])}
