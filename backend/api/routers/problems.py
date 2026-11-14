from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFound, ValidationFailed
from core.uploads import validate_upload
from database.models import (Assumption, Constraint, Evidence, Problem, ProblemEntity, ProblemRelationship, Source, User, Variable)
from intelligence.perception import perceive_csv, perceive_text
from intelligence.schemas import RELATIONS
from ..deps import current_user, get_db, load_problem, load_project, page, pagination, row_dict
from ..schemas import (AssumptionIn, ConstraintIn, EntityIn, EvidenceIn, ProblemIn, ProblemPatch, RelationshipIn, VariableIn)

router = APIRouter(prefix="/problems", tags=["problems"])


def _detail(db: Session, p: Problem) -> dict:
    d = row_dict(p, ("deleted_at",))
    for key, model in (("entities", ProblemEntity), ("relationships", ProblemRelationship), ("constraints", Constraint),
                       ("variables", Variable), ("assumptions", Assumption), ("evidence", Evidence)):
        rows = db.execute(select(model).where(model.problem_id == p.id).order_by(model.created_at, model.id)).scalars().all()
        d[key] = [row_dict(r) for r in rows]
    return d


@router.get("")
def list_problems(project_id: Optional[uuid.UUID] = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user),
                  p: dict = Depends(pagination)):
    from ..deps import visible_project_ids
    stmt = select(Problem).where(Problem.deleted_at.is_(None), Problem.project_id.in_(visible_project_ids(user)))
    if project_id:
        stmt = stmt.where(Problem.project_id == project_id)
    return page(db, stmt.order_by(Problem.created_at.desc(), Problem.id), p, lambda r: row_dict(r, ("deleted_at",)))


@router.post("", status_code=201)
def create_problem(body: ProblemIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_project(db, user, body.project_id, "editor")
    pr = Problem(project_id=body.project_id, title=body.title, statement=body.statement, goal=body.goal, status="draft", created_by=user.id)
    db.add(pr)
    db.commit()
    return row_dict(pr, ("deleted_at",))


@router.get("/{problem_id}")
def get_problem(problem_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _detail(db, load_problem(db, user, problem_id))


@router.patch("/{problem_id}")
def update_problem(problem_id: uuid.UUID, body: ProblemPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    pr = load_problem(db, user, problem_id, "editor")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k in ("title", "statement", "status"):
            raise ValidationFailed(f"{k} cannot be null")
        setattr(pr, k, v)
    db.commit()
    return row_dict(pr, ("deleted_at",))


@router.delete("/{problem_id}", status_code=204)
def delete_problem(problem_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    pr = load_problem(db, user, problem_id, "editor")
    pr.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


def _add(db, user, problem_id, model, **fields):
    pr = load_problem(db, user, problem_id, "editor")
    row = model(problem_id=pr.id, **fields)
    db.add(row)
    db.commit()
    return row_dict(row)


@router.post("/{problem_id}/entities", status_code=201)
def add_entity(problem_id: uuid.UUID, body: EntityIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _add(db, user, problem_id, ProblemEntity, **body.model_dump())


@router.post("/{problem_id}/relationships", status_code=201)
def add_relationship(problem_id: uuid.UUID, body: RelationshipIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_problem(db, user, problem_id, "editor")  # authorize first so non-members always get 404
    if body.relation_type not in RELATIONS:
        raise ValidationFailed(f"unknown relation_type '{body.relation_type}'", [sorted(RELATIONS)])
    for eid in (body.source_entity_id, body.target_entity_id):  # both entities must belong to this problem
        e = db.get(ProblemEntity, eid)
        if e is None or e.problem_id != problem_id:
            raise ValidationFailed("entity does not belong to this problem")
    return _add(db, user, problem_id, ProblemRelationship, **body.model_dump())


@router.post("/{problem_id}/constraints", status_code=201)
def add_constraint(problem_id: uuid.UUID, body: ConstraintIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _add(db, user, problem_id, Constraint, **body.model_dump())


@router.post("/{problem_id}/variables", status_code=201)
def add_variable(problem_id: uuid.UUID, body: VariableIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _add(db, user, problem_id, Variable, **body.model_dump())


@router.post("/{problem_id}/assumptions", status_code=201)
def add_assumption(problem_id: uuid.UUID, body: AssumptionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _add(db, user, problem_id, Assumption, **body.model_dump())


@router.post("/{problem_id}/evidence", status_code=201)
def add_evidence(problem_id: uuid.UUID, body: EvidenceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load_problem(db, user, problem_id, "editor")  # authorize before looking up the source
    if body.source_id is not None and db.get(Source, body.source_id) is None:
        raise ValidationFailed("source_id does not exist")
    return _add(db, user, problem_id, Evidence, **body.model_dump())


@router.post("/{problem_id}/uploads")
async def upload(problem_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    """Validate an upload and, for text-like files, return proposed structure. Nothing is stored automatically."""
    load_problem(db, user, problem_id, "editor")
    max_bytes = request.app.state.settings.max_upload_bytes
    data = await file.read(max_bytes + 1)  # never read more than the limit plus one byte
    up = validate_upload(file.filename or "", data, max_bytes, file.content_type)
    res = {"filename": up.filename, "kind": up.kind, "size": up.size, "processed": False, "proposal": None}
    if up.kind in ("text", "csv"):
        text = up.data.decode("utf-8")
        per = perceive_csv(text, up.filename) if up.kind == "csv" else perceive_text(text, up.filename)
        res.update(processed=True, proposal=per.to_dict())
    else:
        res["reason"] = f"{up.kind} content is validated but not interpreted in this version"
    return res
