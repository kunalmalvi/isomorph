"""SQLAlchemy backed RunStore: discovery_sessions plus pipeline_stages. UNVERIFIED in the authoring sandbox."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select

from database.models import (CandidateMatch, DiscoverySession, PipelineStage, StructuralFingerprint, StructuralModel)
from services.orchestrator import STAGES
from services.run_store import ACTIVE_STATUSES, RunRecord, RunStore, StageRecord


def _dt(ts: Optional[float]):
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def _ts(dt) -> Optional[float]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class SqlRunStore(RunStore):
    """Each call uses its own short session, so it is safe to use from worker threads."""

    def __init__(self, session_factory):
        self.sf = session_factory

    def get(self, run_id: str) -> Optional[RunRecord]:
        try:
            sid = uuid.UUID(run_id)
        except ValueError:
            return None
        with self.sf() as db:
            s = db.get(DiscoverySession, sid)
            if s is None:
                return None
            rows = db.execute(select(PipelineStage).where(PipelineStage.discovery_session_id == sid)
                              .order_by(PipelineStage.ordinal)).scalars().all()
            stages = {r.name: StageRecord(r.name, r.status, r.output, r.error, r.source, r.version, _ts(r.started_at),
                                          _ts(r.finished_at)) for r in rows}
            for n in STAGES:
                stages.setdefault(n, StageRecord(n))
            stages = {n: stages[n] for n in STAGES}
            return RunRecord(run_id, s.input or {}, s.config or {}, s.status, s.error, stages, _ts(s.created_at) or 0.0,
                             _ts(s.updated_at) or 0.0)

    def active_run_ids(self):
        with self.sf() as db:
            rows = db.execute(select(DiscoverySession.id).where(DiscoverySession.status.in_(ACTIVE_STATUSES))).scalars().all()
            return sorted(str(r) for r in rows)

    def save(self, run: RunRecord) -> None:
        sid = uuid.UUID(run.id)
        with self.sf() as db:
            s = db.get(DiscoverySession, sid)
            if s is None:
                raise KeyError("discovery session row must exist before its run is saved")
            s.status, s.error, s.input, s.config = run.status, run.error, run.input, run.config
            if run.status == "running" and s.started_at is None:
                s.started_at = datetime.now(timezone.utc)
            if run.status in ("done", "failed", "cancelled"):
                s.finished_at = datetime.now(timezone.utc)
            existing = {r.name: r for r in db.execute(select(PipelineStage).where(PipelineStage.discovery_session_id == sid)).scalars()}
            for i, n in enumerate(STAGES):
                st = run.stages[n]
                row = existing.get(n)
                if row is None:
                    row = PipelineStage(discovery_session_id=sid, name=n, ordinal=i)
                    db.add(row)
                row.status, row.source, row.version = st.status, st.source, st.version
                row.output, row.error = st.output, st.error
                row.started_at, row.finished_at = _dt(st.started_at), _dt(st.finished_at)
            db.commit()


def persist_results(session_factory, run_id: str) -> None:
    """Project a finished run into structural_models, structural_fingerprints and candidate_matches (idempotent)."""
    sid = uuid.UUID(run_id)
    store = SqlRunStore(session_factory)
    run = store.get(run_id)
    if run is None:
        return
    ext, dna, mat = run.stages["structural_extraction"], run.stages["structural_dna"], run.stages["structural_matching"]
    with session_factory() as db:
        s = db.get(DiscoverySession, sid)
        if s is None:
            return
        if ext.status == "done":
            old = db.execute(select(StructuralModel).where(StructuralModel.discovery_session_id == sid)).scalars().all()
            for m in old:
                db.execute(delete(StructuralFingerprint).where(StructuralFingerprint.structural_model_id == m.id))
                db.delete(m)
            db.flush()
            model = StructuralModel(problem_id=s.problem_id, project_id=s.project_id, discovery_session_id=sid,
                                    graph=ext.output, version=ext.version, provenance="computation")
            db.add(model)
            db.flush()
            if dna.status == "done":
                fp = dna.output["fingerprint"]
                db.add(StructuralFingerprint(structural_model_id=model.id, schema_version=fp["schema_version"],
                                             functional=fp["functional"], relational=fp["relational"],
                                             topological=fp["topological"], dynamic=fp["dynamic"],
                                             constraint=fp["constraint"], semantic=fp["semantic"], hash=fp["hash"]))
        if mat.status == "done":
            db.execute(delete(CandidateMatch).where(CandidateMatch.discovery_session_id == sid))
            for rank, m in enumerate(mat.output["matches"], 1):
                db.add(CandidateMatch(discovery_session_id=sid, project_id=s.project_id, system_key=m["system_id"],
                                      score=m["score"], breakdown=m, domain_distance=m["domain_distance"], rank=rank))
        db.commit()
