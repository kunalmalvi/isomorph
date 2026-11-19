"""End-to-end orchestration of the engine for ANY problem (text or structured). Stdlib only."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

from .schemas import Problem, ScoreWeights, System
from .perception import perceive_text, PerceptionResult
from .structural_model import build_model
from .domain_engine import DomainRegistry
from .analogy_engine import AnalogyEngine
from .transformation_engine import derive_concepts, select_distinct
from .hypothesis_engine import generate
from .validation_engine import validate
from .learning_engine import MemoryStore, learned_prior


def investigate(problem_or_text, systems: Sequence[System], domains: DomainRegistry, title: str = "",
                query_domain: Optional[str] = None, cross_domain_only: bool = True, top_n: int = 15, pool_size: int = 40, min_concepts: int = 3,
                weights: Optional[ScoreWeights] = None, threshold: float = 0.0,
                problem_hook: Optional[Callable[[Problem], Problem]] = None,
                concept_overrides: Optional[Dict[str, Dict[str, float]]] = None,
                experiment_context: Optional[dict] = None, memory: Optional[MemoryStore] = None,
                seeds: Sequence[int] = tuple(range(20)), learned: Optional[dict] = None) -> dict:
    """Run perception, matching, transformation, hypotheses, validation and learning.

    problem_or_text: a free text string or a Problem. problem_hook may enrich the perceived Problem
    (for example with user supplied parameters and checked constraints).
    learned: an active learned version dict (id and config from the ModelRegistry). Its lexicon overlay is passed to
    perception and its priors are applied only when their recorded conditions match this run (query_domain).
    """
    if isinstance(problem_or_text, Problem):
        perception = None
        problem = problem_or_text
    else:
        perception: PerceptionResult = perceive_text(
            problem_or_text, title, overlay=(learned["config"]["lexicon_overlay"] or None) if learned else None,
            overlay_version=learned["id"] if learned else None)
        problem = perception.problem
    if problem_hook:
        problem = problem_hook(problem)
    qd = query_domain or domains.detect_domain(problem.statement + " " + problem.title)
    pmodel = build_model(problem, qd)
    engine = AnalogyEngine(systems, domains, weights)
    report = engine.search(pmodel, qd, top_n=max(top_n, pool_size), threshold=threshold, cross_domain_only=cross_domain_only)
    pool = list(report.matches)
    report.matches = pool[:top_n]  # displayed matches
    concepts_all = []
    for i, m in enumerate(pool):
        if i >= top_n and len({c.concept_type for c in concepts_all}) >= min_concepts:
            break  # pool is only expanded below the displayed matches when too few distinct concepts were found
        analog = engine.by_id[m.system_id]
        concepts_all += derive_concepts(problem, pmodel, analog, engine.models[m.system_id], m.mapping, m.score,
                                        concept_overrides)
    concepts = select_distinct(concepts_all)
    if memory is not None or learned is not None:  # priors nudge order only among close scores
        run_conditions = {"query_domain": qd}

        def adjust(c) -> float:
            a = memory.prior_adjustment(c.concept_type) if memory is not None else 0.0
            if learned is not None:
                a = max(-0.1, min(0.1, a + learned_prior(learned["config"], c.concept_type, run_conditions)))
            return a
        concepts.sort(key=lambda c: (-(round(c.analog_score / 100.0 + adjust(c), 6)), c.id))
    hypotheses = generate(concepts, problem, experiment_context)
    validations = [validate(h, seeds) for h in hypotheses]
    for h, v in zip(hypotheses, validations):
        h.status = v.outcome
        if memory is not None:
            memory.record_validation(h, v, h.based_on[0].split(":")[0], {"query_domain": qd})
    return {"problem": problem, "perception": perception, "query_domain": qd, "model": pmodel, "search": report,
            "learned_version": learned["id"] if learned else None,
            "concepts": concepts, "hypotheses": hypotheses, "validations": validations, "engine": engine}
