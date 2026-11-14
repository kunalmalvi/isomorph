"""mappings, transformations, hypotheses, experiments, validation. Each step derives from stored upstream rows."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFound, ValidationFailed
from database.models import (CandidateMatch, DiscoverySession, Experiment, ExperimentConfiguration, ExperimentResult, ExperimentRun,
                             Hypothesis, StructuralMapping, Transformation, User, ValidationRecord)
from experiments import CODE_VERSION, config_hash
from services.derivation import concepts_for_mapping, hypothesis_for_concept, run_arms, validate_hypothesis
from ..deps import current_user, get_db, load_owned, page, pagination, row_dict, visible_project_ids
from ..schemas import (ExperimentIn, HypothesisIn, HypothesisPatch, MappingIn, RunIn, TransformationIn, ValidationIn)

router = APIRouter(tags=["pipeline"])


def _run_outputs(request: Request, session_id: uuid.UUID) -> dict:
    run = request.app.state.orchestrator.store.get(str(session_id))
    if run is None or run.stages["perception"].output is None or run.stages["structural_extraction"].output is None:
        raise NotFound("discovery outputs are not available")
    return {"problem": run.stages["perception"].output["problem"], "extraction": run.stages["structural_extraction"].output, "config": run.config}


# ------------------------------------------------------------------ mappings
@router.post("/mappings", status_code=201)
def create_mapping(body: MappingIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = load_owned(db, user, CandidateMatch, body.match_id, "editor", "match")
    mp = (m.breakdown or {}).get("mapping")
    if not mp:
        raise ValidationFailed("match has no stored mapping")
    existing = db.execute(select(StructuralMapping).where(StructuralMapping.candidate_match_id == m.id)).scalars().first()
    if existing:
        return row_dict(existing)
    row = StructuralMapping(candidate_match_id=m.id, project_id=m.project_id, node_pairs=mp["node_pairs"],
                            edge_pairs=mp["edge_pairs"],
                            unmapped_source=mp["unmapped_source"], unmapped_target=mp["unmapped_target"], confidence=mp["confidence"])
    db.add(row)
    db.commit()
    return row_dict(row)


@router.get("/mappings/{mapping_id}")
def get_mapping(mapping_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, StructuralMapping, mapping_id, "viewer", "mapping"))


# ------------------------------------------------------------------ transformations
@router.post("/transformations", status_code=201)
def create_transformation(body: TransformationIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    mp = load_owned(db, user, StructuralMapping, body.mapping_id, "editor", "mapping")
    match = db.get(CandidateMatch, mp.candidate_match_id)
    ctx = _run_outputs(request, match.discovery_session_id)
    mapping = {"node_pairs": mp.node_pairs, "edge_pairs": mp.edge_pairs, "unmapped_source": mp.unmapped_source,
               "unmapped_target": mp.unmapped_target, "confidence": mp.confidence}
    concepts = concepts_for_mapping(request.app.state.kb, ctx["config"].get("weights"), ctx["problem"], ctx["extraction"], match.system_key,
                                    mapping, match.score, ctx["config"].get("concept_overrides"))
    types = [c.concept_type for c in concepts]
    if not concepts:
        raise ValidationFailed("this mapping yields no grounded transformation concept")
    if body.concept_type:
        chosen = next((c for c in concepts if c.concept_type == body.concept_type), None)
        if chosen is None:
            raise ValidationFailed(f"concept_type must be one of {types}")
    else:
        chosen = concepts[0]
    row = Transformation(structural_mapping_id=mp.id, project_id=mp.project_id, concept=chosen.to_dict(), steps=chosen.steps,
                         constraint_report=chosen.constraint_report, status=chosen.status, confidence=mp.confidence)
    db.add(row)
    db.commit()
    return dict(row_dict(row), available_concept_types=types)


@router.get("/transformations/{transformation_id}")
def get_transformation(transformation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, Transformation, transformation_id, "viewer", "transformation"))


# ------------------------------------------------------------------ hypotheses
@router.get("/hypotheses")
def list_hypotheses(transformation_id: Optional[uuid.UUID] = Query(None), status: Optional[str] = Query(None, max_length=20),
                    db: Session = Depends(get_db), user: User = Depends(current_user), p: dict = Depends(pagination)):
    stmt = select(Hypothesis).where(Hypothesis.deleted_at.is_(None), Hypothesis.project_id.in_(visible_project_ids(user)))
    if transformation_id:
        stmt = stmt.where(Hypothesis.transformation_id == transformation_id)
    if status:
        stmt = stmt.where(Hypothesis.status == status)
    return page(db, stmt.order_by(Hypothesis.created_at.desc(), Hypothesis.id), p, lambda h: row_dict(h, ("deleted_at",)))


@router.post("/hypotheses", status_code=201)
def create_hypothesis(body: HypothesisIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = load_owned(db, user, Transformation, body.transformation_id, "editor", "transformation")
    mp = db.get(StructuralMapping, t.structural_mapping_id)
    match = db.get(CandidateMatch, mp.candidate_match_id)
    ctx = _run_outputs(request, match.discovery_session_id)
    h = hypothesis_for_concept(t.concept, ctx["problem"], ctx["config"].get("experiment_context"))
    row = Hypothesis(transformation_id=t.id, project_id=t.project_id, statement=h["statement"], prediction=h["prediction"],
                     falsifier=h["falsifier"], experiment=h["experiment"], provenance=h["provenance"], status="untested")
    db.add(row)
    db.commit()
    return row_dict(row, ("deleted_at",))


@router.get("/hypotheses/{hypothesis_id}")
def get_hypothesis(hypothesis_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, Hypothesis, hypothesis_id, "viewer", "hypothesis"), ("deleted_at",))


@router.patch("/hypotheses/{hypothesis_id}")
def update_hypothesis(hypothesis_id: uuid.UUID, body: HypothesisPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Edit text. An edited hypothesis becomes provenance=user and goes back to untested, because the old evidence no longer applies."""
    h = load_owned(db, user, Hypothesis, hypothesis_id, "editor", "hypothesis")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("statement") is None and "statement" in changes:
        raise ValidationFailed("statement cannot be null")
    for k, v in changes.items():
        setattr(h, k, v)
    if changes:
        h.provenance, h.status = "user", "untested"
    db.commit()
    return row_dict(h, ("deleted_at",))


# ------------------------------------------------------------------ experiments
@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    h = load_owned(db, user, Hypothesis, body.hypothesis_id, "editor", "hypothesis")
    spec = h.experiment
    if not spec or not spec.get("kind"):
        raise ValidationFailed("hypothesis has no applicable experiment model; define the metric and model first")
    exp = Experiment(hypothesis_id=h.id, project_id=h.project_id, name=body.name, description=body.description)
    db.add(exp)
    db.flush()
    cfg = ExperimentConfiguration(experiment_id=exp.id, parameters=spec, config_hash=config_hash({"spec": spec, "seed": body.seed}), seed=body.seed)
    db.add(cfg)
    db.commit()
    return dict(row_dict(exp, ("deleted_at",)), configuration=row_dict(cfg))


def _config(db: Session, exp: Experiment) -> ExperimentConfiguration:
    return db.execute(select(ExperimentConfiguration).where(ExperimentConfiguration.experiment_id == exp.id)
                      .order_by(ExperimentConfiguration.created_at.desc())).scalars().first()


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    exp = load_owned(db, user, Experiment, experiment_id, "viewer", "experiment")
    cfg = _config(db, exp)
    runs = db.execute(select(ExperimentRun).where(ExperimentRun.experiment_configuration_id == cfg.id).order_by(ExperimentRun.created_at)).scalars().all()
    return dict(row_dict(exp, ("deleted_at",)), configuration=row_dict(cfg), runs=[row_dict(r) for r in runs])


@router.post("/experiments/{experiment_id}/runs", status_code=201)
def run_experiment_endpoint(experiment_id: uuid.UUID, body: RunIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    exp = load_owned(db, user, Experiment, experiment_id, "editor", "experiment")
    cfg = _config(db, exp)
    now = datetime.now(timezone.utc)
    metrics = run_arms(cfg.parameters, body.seed)  # deterministic: identical seed and configuration give identical metrics
    run = ExperimentRun(experiment_configuration_id=cfg.id, status="done", code_version=CODE_VERSION, started_at=now, finished_at=now)
    db.add(run)
    db.flush()
    res = ExperimentResult(experiment_run_id=run.id, metrics=metrics, notes=metrics["disclaimer"])
    db.add(res)
    db.commit()
    return dict(row_dict(run), result=row_dict(res))


@router.get("/experiments/{experiment_id}/runs/{run_id}")
def get_run(experiment_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    exp = load_owned(db, user, Experiment, experiment_id, "viewer", "experiment")
    cfg = _config(db, exp)
    run = db.get(ExperimentRun, run_id)
    if run is None or cfg is None or run.experiment_configuration_id != cfg.id:
        raise NotFound("run not found")
    res = db.execute(select(ExperimentResult).where(ExperimentResult.experiment_run_id == run.id)).scalars().first()
    return dict(row_dict(run), result=row_dict(res) if res else None)


# ------------------------------------------------------------------ validation
@router.post("/validation", status_code=201)
def create_validation(body: ValidationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    h = load_owned(db, user, Hypothesis, body.hypothesis_id, "editor", "hypothesis")
    v = validate_hypothesis({"id": str(h.id), "statement": h.statement, "prediction": h.prediction or "", "falsifier": h.falsifier or "",
                             "category": "efficiency", "provenance": h.provenance, "status": h.status, "experiment": h.experiment,
                             "based_on": []}, body.seeds)
    rec = ValidationRecord(hypothesis_id=h.id, project_id=h.project_id, outcome=v["outcome"], caveats=v["caveats"], validated_by=user.id,
                           method=v["method"])
    h.status = v["outcome"]
    db.add(rec)
    db.commit()
    return dict(row_dict(rec), evidence=v["evidence"])


@router.get("/validation")
def list_validation(hypothesis_id: Optional[uuid.UUID] = Query(None), db: Session = Depends(get_db), user: User = Depends(current_user),
                    p: dict = Depends(pagination)):
    stmt = select(ValidationRecord).where(ValidationRecord.project_id.in_(visible_project_ids(user)))
    if hypothesis_id:
        stmt = stmt.where(ValidationRecord.hypothesis_id == hypothesis_id)
    return page(db, stmt.order_by(ValidationRecord.created_at.desc(), ValidationRecord.id), p, row_dict)


@router.get("/validation/{validation_id}")
def get_validation(validation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row_dict(load_owned(db, user, ValidationRecord, validation_id, "viewer", "validation record"))
