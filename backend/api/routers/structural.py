from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import ValidationFailed
from database.models import (Constraint, ProblemEntity, ProblemRelationship, StructuralFingerprint, StructuralModel, User, Variable)
from intelligence.fingerprint import closeness, compute_fingerprint, cosine, jaccard_vec, vector_similarity
from intelligence.schemas import Fingerprint, SchemaError
from intelligence.structural_model import build_model
from services.orchestrator import _model_from_output
from services.problem_builder import build_problem
from ..deps import current_user, get_db, load_owned, load_problem, row_dict
from ..schemas import CompareIn, StructuralModelIn

router = APIRouter(tags=["structural"])


@router.post("/structural-models", status_code=201)
def create_model(body: StructuralModelIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    pr = load_problem(db, user, body.problem_id, "editor")
    ents = db.execute(select(ProblemEntity).where(ProblemEntity.problem_id == pr.id)).scalars().all()
    if not ents:
        raise ValidationFailed("problem has no entities. Add entities and relationships, or run a discovery to extract them from text")
    rels = db.execute(select(ProblemRelationship).where(ProblemRelationship.problem_id == pr.id)).scalars().all()
    cons = db.execute(select(Constraint).where(Constraint.problem_id == pr.id)).scalars().all()
    vs = db.execute(select(Variable).where(Variable.problem_id == pr.id)).scalars().all()
    try:
        problem = build_problem(str(pr.id), pr.title, pr.statement, pr.goal or "", [row_dict(e) for e in ents],
                                [row_dict(r) for r in rels], [row_dict(c) for c in cons], [row_dict(v) for v in vs])
    except SchemaError as e:
        raise ValidationFailed(f"problem model is invalid: {e}")
    kb = request.app.state.kb
    qd = kb.registry.detect_domain(problem.statement + " " + problem.title)
    model = build_model(problem, qd)
    prev = db.execute(select(StructuralModel).where(StructuralModel.problem_id == pr.id, StructuralModel.discovery_session_id.is_(None))).scalars().all()
    row = StructuralModel(problem_id=pr.id, project_id=pr.project_id, graph={"query_domain": qd, "model": model.to_dict(), "text": model.text},
                          version=len(prev) + 1, provenance="computation")
    db.add(row)
    db.commit()
    return row_dict(row, ("deleted_at",))


@router.get("/structural-models/{model_id}")
def get_model(model_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, StructuralModel, model_id, "viewer", "structural model"), ("deleted_at",))


@router.get("/structural-models/{model_id}/graph")
def get_graph(model_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = load_owned(db, user, StructuralModel, model_id, "viewer", "structural model")
    m = row.graph["model"]
    return {"id": str(row.id), "domain": m["domain"], "graph": m["graph"], "metrics": m["metrics"], "dynamics": m["dynamics"],
            "constraint_tags": m["constraint_tags"], "flags": m["flags"]}


def _fingerprint(db: Session, request: Request, row: StructuralModel) -> StructuralFingerprint:
    fp = db.execute(select(StructuralFingerprint).where(StructuralFingerprint.structural_model_id == row.id)
                    .order_by(StructuralFingerprint.created_at.desc())).scalars().first()
    if fp is None:
        f = compute_fingerprint(_model_from_output(row.graph), request.app.state.kb.engine().idf)
        fp = StructuralFingerprint(structural_model_id=row.id, schema_version=f.schema_version, functional=f.functional,
                                   relational=f.relational, topological=f.topological, dynamic=f.dynamic,
                                   constraint=f.constraint, semantic=f.semantic, hash=f.hash)
        db.add(fp)
        db.commit()
    return fp


def _to_fp(fp: StructuralFingerprint) -> Fingerprint:
    return Fingerprint(fp.schema_version, fp.functional, fp.relational, fp.topological, fp.dynamic, fp.constraint, fp.semantic, fp.hash)


@router.get("/structural-dna/{model_id}")
def get_dna(model_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = load_owned(db, user, StructuralModel, model_id, "viewer", "structural model")
    fp = _fingerprint(db, request, row)
    return {"model_id": str(row.id), "fingerprint": _to_fp(fp).to_dict(), "provenance": "computation"}


@router.post("/structural-dna/compare")
def compare_dna(body: CompareIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = load_owned(db, user, StructuralModel, body.model_id_a, "viewer", "structural model")
    b = load_owned(db, user, StructuralModel, body.model_id_b, "viewer", "structural model")
    fa, fb = _to_fp(_fingerprint(db, request, a)), _to_fp(_fingerprint(db, request, b))
    return {"overall": round(vector_similarity(fa, fb), 6), "same_hash": fa.hash == fb.hash,
            "components": {"functional": round(cosine(fa.functional, fb.functional), 6),
                           "relational": round(cosine(fa.relational, fb.relational), 6),
                           "topological": round(closeness(fa.topological, fb.topological), 6),
                           "dynamic": round(jaccard_vec(fa.dynamic, fb.dynamic), 6),
                           "constraint": round(jaccard_vec(fa.constraint, fb.constraint), 6),
                           "semantic": round(cosine(fa.semantic, fb.semantic), 6)},
            "note": "Component similarities are heuristic measures on feature vectors."}
