"""Staged discovery pipeline with persisted, inspectable stage outputs and downstream rerun. Stdlib only.

Stages (linear): perception, structural_extraction, structural_dna, cross_domain_search, structural_matching,
mechanism_mapping, transformation, hypothesis_generation, validation.

Semantics
- Every stage output is a JSON dict stored in the RunStore after the stage finishes.
- `run` executes stages that are not "done" (pending or stale) in order. A failing stage stops the run; later
  stages stay pending. Nothing is fabricated to fill a gap.
- `edit_stage` replaces a stage output (source becomes "user"), keeps it "done" and marks all later stages "stale".
- `rerun_downstream` recomputes the stale stages after an edit and keeps the edited stage as it is.
- `rerun_from` recomputes a stage itself (discarding any edit) and every later stage.
- Cancellation is checked between stages.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable, Dict, List, Optional

from ai_providers import CompletionRequest, LocalProvider, Provider, ProviderError
from core.errors import AppError, Conflict, NotFound, ValidationFailed
from intelligence.constraint_engine import ConstraintReport  # noqa: F401  (re-exported for type reference)
from intelligence.fingerprint import compute_fingerprint, vector_similarity
from intelligence.hypothesis_engine import generate
from intelligence.mapping_engine import Mapping, map_graphs
from intelligence.schemas import (Fingerprint, Graph, Hypothesis, Problem, Provenance, SchemaError, ScoreWeights)
from intelligence.structural_model import StructuralModel, build_model
from intelligence.transformation_engine import Concept, derive_concepts, select_distinct
from intelligence.validation_engine import validate

from .knowledge import KnowledgeBase, default_knowledge
from .run_store import RunRecord, RunStore, StageRecord

STAGES = ("perception", "structural_extraction", "structural_dna", "cross_domain_search", "structural_matching",
          "mechanism_mapping", "transformation", "hypothesis_generation", "validation")

DEFAULT_CONFIG = {"weights": None, "threshold": 0.0, "top_k": 10, "mapping_k": 5, "cross_domain_only": True,
                  "query_domain": None, "seeds": 20, "concept_overrides": None, "experiment_context": None,
                  "provider": "local"}

PERCEPTION_SCHEMA = {"type": "object", "required": ["problem"],
                     "properties": {"problem": {"type": "object", "required": ["id", "graph"],
                                                "properties": {"graph": {"type": "object", "required": ["nodes", "edges"]}}}}}


class StageFailed(AppError):
    status = 500
    code = "stage_failed"


class Cancelled(Exception):
    pass


def _model_from_output(out: dict) -> StructuralModel:
    m = out["model"]
    return StructuralModel(m["id"], m["name"], m["domain"], Graph.from_dict(m["graph"]), out.get("text", ""),
                           list(m.get("behaviours", [])), list(m.get("dynamics", [])), list(m.get("constraint_tags", [])),
                           dict(m.get("metrics", {})), dict(m.get("role_counts", {})), list(m.get("flags", [])))


def _mapping_from_dict(d: dict) -> Mapping:
    return Mapping(node_pairs=[(a, b, float(s)) for a, b, s in d["node_pairs"]], edge_pairs=list(d.get("edge_pairs", [])),
                   lost_edges=list(d.get("lost_edges", [])), unmatched_target_edges=list(d.get("unmatched_target_edges", [])),
                   unmapped_source=list(d.get("unmapped_source", [])), unmapped_target=list(d.get("unmapped_target", [])),
                   confidence=float(d.get("confidence", 0.0)), edge_recall=float(d.get("edge_recall", 0.0)),
                   edge_precision=float(d.get("edge_precision", 0.0)), edge_f1=float(d.get("edge_f1", 0.0)),
                   node_coverage=float(d.get("node_coverage", 0.0)))


def _hypothesis_from_dict(d: dict) -> Hypothesis:
    d = dict(d)
    d["provenance"] = Provenance(d.get("provenance", "computation"))
    return Hypothesis(**d)


def validate_config(config: Optional[dict]) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    unknown = set(config or {}) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValidationFailed("unknown config keys", sorted(unknown))
    cfg.update({k: v for k, v in (config or {}).items()})
    if cfg["weights"] is not None:
        try:
            ScoreWeights(**cfg["weights"]).validate()
        except (TypeError, SchemaError) as e:
            raise ValidationFailed(f"invalid weights: {e}")
    if not isinstance(cfg["top_k"], int) or not 1 <= cfg["top_k"] <= 100:
        raise ValidationFailed("top_k must be an integer between 1 and 100")
    if not isinstance(cfg["mapping_k"], int) or not 1 <= cfg["mapping_k"] <= 20:
        raise ValidationFailed("mapping_k must be an integer between 1 and 20")
    if not isinstance(cfg["seeds"], int) or not 1 <= cfg["seeds"] <= 200:
        raise ValidationFailed("seeds must be an integer between 1 and 200")
    thr = cfg["threshold"]
    if isinstance(thr, bool) or not isinstance(thr, (int, float)) or not 0 <= thr <= 100:
        raise ValidationFailed("threshold must be a number between 0 and 100")
    return cfg


class Orchestrator:
    def __init__(self, store: RunStore, knowledge: Optional[KnowledgeBase] = None, provider: Optional[Provider] = None,
                 clock: Callable[[], float] = time.time, provider_factory: Optional[Callable[[str], Provider]] = None):
        self.store = store
        self.kb = knowledge or default_knowledge()
        self.provider = provider or LocalProvider()
        self.provider_factory = provider_factory
        self.clock = clock
        self._impl: Dict[str, Callable] = {
            "perception": self._perception, "structural_extraction": self._extraction, "structural_dna": self._dna,
            "cross_domain_search": self._search, "structural_matching": self._matching,
            "mechanism_mapping": self._mapping, "transformation": self._transformation,
            "hypothesis_generation": self._hypotheses, "validation": self._validation}

    # ------------------------------------------------------------------ lifecycle
    def create_run(self, text: Optional[str] = None, problem: Optional[dict] = None, title: str = "",
                   config: Optional[dict] = None, run_id: Optional[str] = None) -> RunRecord:
        if bool(text) == bool(problem):
            raise ValidationFailed("provide exactly one of text or problem")
        if problem is not None:
            try:
                Problem.from_dict(problem)
            except (SchemaError, KeyError, TypeError, ValueError) as e:
                raise ValidationFailed(f"invalid problem: {e}")
        cfg = validate_config(config)
        now = self.clock()
        run = RunRecord(run_id or uuid.uuid4().hex, {"text": text, "problem": problem, "title": title}, cfg,
                        "queued", None, {n: StageRecord(n) for n in STAGES}, now, now)
        self.store.save(run)
        return run

    def _get(self, run_id: str) -> RunRecord:
        run = self.store.get(run_id)
        if run is None:
            raise NotFound("run not found")
        return run

    def get_stage(self, run_id: str, stage: str) -> StageRecord:
        run = self._get(run_id)
        if stage not in run.stages:
            raise NotFound(f"unknown stage '{stage}'")
        return run.stages[stage]

    def _save(self, run: RunRecord) -> None:
        run.updated_at = self.clock()
        self.store.save(run)

    def run(self, run_id: str, should_cancel: Optional[Callable[[], bool]] = None) -> RunRecord:
        run = self._get(run_id)
        run.status, run.error = "running", None
        self._save(run)
        try:
            for name in STAGES:
                st = run.stages[name]
                if st.status == "done":
                    continue
                if should_cancel and should_cancel():
                    raise Cancelled()
                self._execute(run, name)
                if run.stages[name].status != "done":
                    run.status = "failed"
                    run.error = f"stage '{name}' failed: {run.stages[name].error}"
                    self._save(run)
                    return run
            run.status = "done"
        except Cancelled:
            run.status = "cancelled"
            for st in run.stages.values():
                if st.status == "running":
                    st.status = "pending"
        self._save(run)
        return run

    def _execute(self, run: RunRecord, name: str) -> None:
        st = run.stages[name]
        st.status, st.error, st.started_at, st.finished_at = "running", None, self.clock(), None
        self._save(run)
        ctx = {n: s.output for n, s in run.stages.items() if s.status == "done" and s.output is not None}
        try:
            out, source = self._impl[name](run, ctx)
            st.output, st.source, st.status = out, source, "done"
            st.version += 1
        except (AppError, ProviderError, SchemaError, KeyError, ValueError, TypeError) as e:
            st.status, st.error, st.output = "failed", f"{type(e).__name__}: {e}", None
        st.finished_at = self.clock()
        self._save(run)

    def edit_stage(self, run_id: str, stage: str, output: dict) -> RunRecord:
        run = self._get(run_id)
        if stage not in run.stages:
            raise NotFound(f"unknown stage '{stage}'")
        if run.status == "running":
            raise Conflict("run is currently executing")
        st = run.stages[stage]
        if st.status != "done":
            raise Conflict(f"stage '{stage}' has no output to edit (status {st.status})")
        if not isinstance(output, dict):
            raise ValidationFailed("output must be an object")
        self._validate_output(stage, output)
        st.output, st.source, st.version = output, "user", st.version + 1
        st.finished_at = self.clock()
        self._mark_downstream(run, stage)
        self._save(run)
        return run

    def _validate_output(self, stage: str, out: dict) -> None:
        try:
            if stage == "perception":
                Problem.from_dict(out["problem"])
            elif stage == "structural_extraction":
                _model_from_output(out)
            elif stage == "structural_dna":
                Fingerprint.from_dict(out["fingerprint"])
            elif stage == "cross_domain_search":
                [c["system_id"] for c in out["candidates"]]
            elif stage == "structural_matching":
                [(m["system_id"], m["score"]) for m in out["matches"]]
            elif stage == "mechanism_mapping":
                for m in out["mappings"]:
                    _mapping_from_dict(m["mapping"])
            elif stage == "transformation":
                [Concept(**c) for c in out["concepts"]]
            elif stage == "hypothesis_generation":
                [_hypothesis_from_dict(h) for h in out["hypotheses"]]
            elif stage == "validation":
                out["validations"]
        except (KeyError, TypeError, ValueError, SchemaError) as e:
            raise ValidationFailed(f"edited output for '{stage}' is invalid: {type(e).__name__}: {e}")

    @staticmethod
    def _mark_downstream(run: RunRecord, stage: str) -> None:
        idx = STAGES.index(stage)
        for n in STAGES[idx + 1:]:
            s = run.stages[n]
            if s.status in ("done", "failed", "running"):
                s.status = "stale"
            s.error = None

    def rerun_downstream(self, run_id: str, stage: str, should_cancel=None) -> RunRecord:
        run = self._get(run_id)
        if stage not in run.stages:
            raise NotFound(f"unknown stage '{stage}'")
        self._mark_downstream(run, stage)
        self._save(run)
        return self.run(run_id, should_cancel)

    def rerun_from(self, run_id: str, stage: str, should_cancel=None) -> RunRecord:
        run = self._get(run_id)
        if stage not in run.stages:
            raise NotFound(f"unknown stage '{stage}'")
        run.stages[stage].status = "stale"
        self._mark_downstream(run, stage)
        self._save(run)
        return self.run(run_id, should_cancel)

    # ------------------------------------------------------------------ stages
    def _problem(self, ctx) -> Problem:
        return Problem.from_dict(ctx["perception"]["problem"])

    def _weights(self, run) -> Optional[ScoreWeights]:
        w = run.config.get("weights")
        return ScoreWeights(**w) if w else None

    def _provider_for(self, run) -> Provider:
        name = run.config.get("provider", "local")
        if name == "local":
            return self.provider if self.provider.name == "local" else LocalProvider()
        if self.provider.name == name:
            return self.provider
        if self.provider_factory is None:
            raise ValidationFailed(f"provider '{name}' is not available")
        return self.provider_factory(name)

    def _perception(self, run, ctx):
        inp = run.input
        if inp.get("problem"):
            problem = Problem.from_dict(inp["problem"])
            return {"problem": problem.to_dict(), "facts": [], "inferences": [], "assumptions": [], "unknowns": [],
                    "clarification_questions": [], "flags": ["structured input supplied by the user, perception skipped"],
                    "limitations": "", "available": True, "provider": "user"}, "user"
        provider = self._provider_for(run)
        res = provider.complete(CompletionRequest(prompt=inp["text"], task="extract_structure", system=inp.get("title") or None,
                                                  schema=PERCEPTION_SCHEMA))
        out = dict(res.parsed)
        problem = Problem.from_dict(out["problem"])  # raises SchemaError on a malformed model answer
        if res.provenance != "computation":
            for n in problem.graph.nodes:
                n.provenance = Provenance.AI_HYPOTHESIS
            for e in problem.graph.edges:
                e.provenance = Provenance.AI_HYPOTHESIS
            out["problem"] = problem.to_dict()
        out["provider"] = {"name": res.provider, "model": res.model, "usage": res.usage}
        return out, res.provenance

    def _extraction(self, run, ctx):
        problem = self._problem(ctx)
        qd = run.config.get("query_domain") or self.kb.registry.detect_domain(problem.statement + " " + problem.title)
        model = build_model(problem, qd)
        return {"query_domain": qd, "model": model.to_dict(), "text": model.text,
                "domain_candidates": self.kb.registry.classify_text(problem.statement + " " + problem.title)}, "computation"

    def _dna(self, run, ctx):
        model = _model_from_output(ctx["structural_extraction"])
        fp = compute_fingerprint(model, self.kb.engine(self._weights(run)).idf)
        return {"fingerprint": fp.to_dict(), "note": "Fingerprint of the problem model. Components: functional, relational, topological, dynamic, constraint, semantic."}, "computation"

    def _search(self, run, ctx):
        eng = self.kb.engine(self._weights(run))
        qd = ctx["structural_extraction"]["query_domain"]
        fp = Fingerprint.from_dict(ctx["structural_dna"]["fingerprint"])
        cross = bool(run.config.get("cross_domain_only", True))
        excluded, pool = [], []
        for s in eng.systems:
            if cross and s.domain == qd:
                excluded.append({"system_id": s.id, "stage": "cross_domain_filter", "reason": "same domain as problem"})
            else:
                pool.append(s)
        ranked = sorted(((vector_similarity(fp, eng.fps[s.id]), s) for s in pool), key=lambda t: (-round(t[0], 12), t[1].id))
        keep = ranked[: eng.top_k]
        for _, s in ranked[eng.top_k:]:
            excluded.append({"system_id": s.id, "stage": "retrieval", "reason": f"outside top {eng.top_k} by fingerprint similarity"})
        cands = [{"rank": i, "system_id": s.id, "name": s.name, "domain": s.domain, "similarity": round(sim, 6)}
                 for i, (sim, s) in enumerate(keep, 1)]
        return {"query_domain": qd, "cross_domain_only": cross, "knowledge_base_size": len(eng.systems),
                "candidates": cands, "excluded": excluded}, "computation"

    def _matching(self, run, ctx):
        eng = self.kb.engine(self._weights(run))
        model = _model_from_output(ctx["structural_extraction"])
        qd = ctx["structural_extraction"]["query_domain"]
        keep = {c["system_id"] for c in ctx["cross_domain_search"]["candidates"]}
        exclude = [s.id for s in eng.systems if s.id not in keep]
        report = eng.search(model, qd, top_n=run.config["top_k"], threshold=float(run.config["threshold"]),
                            cross_domain_only=bool(run.config["cross_domain_only"]), exclude_ids=exclude)
        out = report.to_dict()
        out["query_domain"] = qd
        return out, "computation"

    def _mapping(self, run, ctx):
        model = _model_from_output(ctx["structural_extraction"])
        eng = self.kb.engine(self._weights(run))
        res = []
        for m in ctx["structural_matching"]["matches"][: run.config["mapping_k"]]:
            amodel = eng.models[m["system_id"]]
            mp = map_graphs(model.graph, amodel.graph)
            labels = {n.id: n.label for n in amodel.graph.nodes}
            res.append({"match_id": m["id"], "system_id": m["system_id"], "system_name": m["system_name"], "score": m["score"],
                        "mapping": mp.to_dict(),
                        "transferable_elements": [{"id": n.id, "label": labels[n.id], "role": n.role}
                                                  for n in amodel.graph.nodes if n.id in set(mp.unmapped_target)]})
        return {"mappings": res}, "computation"

    def _transformation(self, run, ctx):
        problem = self._problem(ctx)
        model = _model_from_output(ctx["structural_extraction"])
        eng = self.kb.engine(self._weights(run))
        found: List[Concept] = []
        for m in ctx["mechanism_mapping"]["mappings"]:
            sid = m["system_id"]
            found += derive_concepts(problem, model, eng.by_id[sid], eng.models[sid], _mapping_from_dict(m["mapping"]),
                                     float(m["score"]), run.config.get("concept_overrides"))
        concepts = select_distinct(found)
        return {"concepts": [c.to_dict() for c in concepts], "considered": len(found),
                "note": "Concepts are analogy transfers, not proven designs. Blocked concepts violate a hard constraint."}, "computation"

    def _hypotheses(self, run, ctx):
        problem = self._problem(ctx)
        concepts = [Concept(**c) for c in ctx["transformation"]["concepts"]]
        hyps = generate(concepts, problem, run.config.get("experiment_context"))
        return {"hypotheses": [h.to_dict() for h in hyps]}, "computation"

    def _validation(self, run, ctx):
        seeds = tuple(range(int(run.config["seeds"])))
        hyps, vals = [], []
        for hd in ctx["hypothesis_generation"]["hypotheses"]:
            h = _hypothesis_from_dict(hd)
            v = validate(h, seeds)
            h.status = v.outcome
            hyps.append(h.to_dict())
            vals.append(v.to_dict())
        return {"hypotheses": hyps, "validations": vals,
                "note": "Outcomes come from seeded simulation under stated assumptions. They are not real world evidence."}, "computation"
