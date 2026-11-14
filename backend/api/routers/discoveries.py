from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import Conflict, NotFound, ValidationFailed
from core.sse import progress_stream
from database.models import (CandidateMatch, Constraint, DiscoverySession, ProblemEntity, ProblemRelationship, User, Variable)
from intelligence.schemas import SchemaError
from services.orchestrator import STAGES, validate_config
from services.problem_builder import build_problem
from ..db_store import persist_results
from ..deps import current_user, get_db, load_owned, load_problem, page, pagination, row_dict, visible_project_ids
from ..schemas import DiscoveryIn, StageEditIn

router = APIRouter(prefix="/discoveries", tags=["discoveries"])


def _problem_input(db: Session, pr) -> dict:
    """Structured input when the user modelled entities, otherwise free text for perception."""
    ents = db.execute(select(ProblemEntity).where(ProblemEntity.problem_id == pr.id).order_by(ProblemEntity.created_at, ProblemEntity.id)).scalars().all()
    if not ents:
        return {"text": pr.statement + (f"\nGoal: {pr.goal}" if pr.goal else ""), "problem": None}
    rels = db.execute(select(ProblemRelationship).where(ProblemRelationship.problem_id == pr.id)).scalars().all()
    cons = db.execute(select(Constraint).where(Constraint.problem_id == pr.id)).scalars().all()
    vs = db.execute(select(Variable).where(Variable.problem_id == pr.id)).scalars().all()
    try:
        problem = build_problem(str(pr.id), pr.title, pr.statement, pr.goal or "", [row_dict(e) for e in ents],
                                [row_dict(r) for r in rels], [row_dict(c) for c in cons], [row_dict(v) for v in vs])
    except SchemaError as e:
        raise ValidationFailed(f"problem model is invalid: {e}")
    return {"text": None, "problem": problem.to_dict()}


def _submit(request: Request, run_id: str, fn):
    jobs, sf = request.app.state.jobs, request.app.state.session_factory

    def action(should_cancel):
        try:
            fn(should_cancel)
        finally:
            persist_results(sf, run_id)
    try:
        jobs.submit(run_id, action)
    except RuntimeError:
        raise Conflict("this discovery is already running")


@router.post("", status_code=202)
def create_discovery(body: DiscoveryIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    pr = load_problem(db, user, body.problem_id, "editor")
    settings = request.app.state.settings
    weights = body.weights.model_dump() if body.weights else None
    config = {"weights": weights, "threshold": body.threshold or 0.0, "top_k": body.top_k, "provider": body.provider or settings.ai_provider}
    validate_config(config)
    inp = _problem_input(db, pr)
    s = DiscoverySession(problem_id=pr.id, project_id=pr.project_id, created_by=user.id, status="queued", input={}, config=config,
                         weights=weights, threshold=config["threshold"])
    db.add(s)
    db.commit()
    orch = request.app.state.orchestrator
    run_id = str(s.id)
    orch.create_run(text=inp["text"], problem=inp["problem"], title=pr.title, config=config, run_id=run_id)
    _submit(request, run_id, lambda cancel: orch.run(run_id, cancel))
    return {"id": run_id, "status": "queued"}


@router.get("")
def list_discoveries(problem_id: Optional[uuid.UUID] = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user),
                     p: dict = Depends(pagination)):
    stmt = select(DiscoverySession).where(DiscoverySession.deleted_at.is_(None), DiscoverySession.project_id.in_(visible_project_ids(user)))
    if problem_id:
        stmt = stmt.where(DiscoverySession.problem_id == problem_id)
    return page(db, stmt.order_by(DiscoverySession.created_at.desc(), DiscoverySession.id), p,
                lambda r: row_dict(r, ("deleted_at", "input")))


@router.get("/{session_id}")
def get_discovery(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = load_owned(db, user, DiscoverySession, session_id, "viewer", "discovery")
    d = row_dict(s, ("deleted_at", "input"))
    run = request.app.state.orchestrator.store.get(str(s.id))
    d["progress"] = run.progress() if run else None
    return d


@router.get("/{session_id}/matches")
def discovery_matches(session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user), p: dict = Depends(pagination)):
    s = load_owned(db, user, DiscoverySession, session_id, "viewer", "discovery")
    stmt = select(CandidateMatch).where(CandidateMatch.discovery_session_id == s.id).order_by(CandidateMatch.rank)
    return page(db, stmt, p, lambda m: {"id": str(m.id), "rank": m.rank, "system_key": m.system_key, "score": m.score,
                                        "domain_distance": m.domain_distance, "domain": (m.breakdown or {}).get("domain"),
                                        "system_name": (m.breakdown or {}).get("system_name")})


@router.post("/{session_id}/cancel")
def cancel_discovery(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = load_owned(db, user, DiscoverySession, session_id, "editor", "discovery")
    if s.status in ("done", "failed", "cancelled"):
        raise Conflict(f"discovery already {s.status}")
    request.app.state.jobs.cancel(str(s.id))
    return {"id": str(s.id), "status": "cancelling"}


# ------------------------------------------------------------- inspectable stages
@router.get("/{session_id}/stages")
def list_stages(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = load_owned(db, user, DiscoverySession, session_id, "viewer", "discovery")
    run = request.app.state.orchestrator.store.get(str(s.id))
    return {"stages": [st.to_dict(include_output=False) for st in run.stages.values()], "order": list(STAGES)}


@router.get("/{session_id}/stages/{stage}")
def get_stage(session_id: uuid.UUID, stage: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = load_owned(db, user, DiscoverySession, session_id, "viewer", "discovery")
    return request.app.state.orchestrator.get_stage(str(s.id), stage).to_dict()


@router.put("/{session_id}/stages/{stage}")
def edit_stage(session_id: uuid.UUID, stage: str, body: StageEditIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    """Replace a stage output. Later stages become stale until /rerun is called."""
    s = load_owned(db, user, DiscoverySession, session_id, "editor", "discovery")
    if request.app.state.jobs.is_active(str(s.id)):
        raise Conflict("discovery is currently running")
    run = request.app.state.orchestrator.edit_stage(str(s.id), stage, body.output)
    return run.progress()


@router.post("/{session_id}/stages/{stage}/rerun", status_code=202)
def rerun_stage(session_id: uuid.UUID, stage: str, request: Request, mode: Literal["downstream", "from"] = Query("downstream"),
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    """mode=downstream keeps the (possibly edited) stage and recomputes everything after it. mode=from recomputes the stage too."""
    s = load_owned(db, user, DiscoverySession, session_id, "editor", "discovery")
    if stage not in STAGES:
        raise NotFound(f"unknown stage '{stage}'")
    orch, run_id = request.app.state.orchestrator, str(s.id)
    fn = orch.rerun_downstream if mode == "downstream" else orch.rerun_from
    _submit(request, run_id, lambda cancel: fn(run_id, stage, cancel))
    return {"id": run_id, "status": "queued"}


@router.get("/{session_id}/events")
def events(session_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Server-sent events: `progress` on every change, `end` when the run reaches a terminal status."""
    s = load_owned(db, user, DiscoverySession, session_id, "viewer", "discovery")
    store, run_id = request.app.state.orchestrator.store, str(s.id)

    def snapshot():
        run = store.get(run_id)
        return run.progress() if run else None
    return StreamingResponse(progress_stream(snapshot), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
