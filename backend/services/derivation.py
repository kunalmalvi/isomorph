"""On-demand derivation steps used by the API after a discovery run. Stdlib only.

These wrap engine calls so that each step (mapping, transformation, hypothesis, experiment, validation) can be
requested individually from stored outputs. Nothing here invents content: if the engine yields nothing the
functions return empty results or raise ValidationFailed.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.errors import ValidationFailed
from experiments import CODE_VERSION, config_hash, run_experiment
from experiments.common import MODEL_DISCLAIMER
from intelligence.hypothesis_engine import generate
from intelligence.schemas import Problem, ScoreWeights
from intelligence.transformation_engine import Concept, derive_concepts
from intelligence.validation_engine import validate

from .knowledge import KnowledgeBase
from .orchestrator import _hypothesis_from_dict, _mapping_from_dict, _model_from_output


def concepts_for_mapping(kb: KnowledgeBase, weights: Optional[dict], problem: dict, extraction: dict, system_id: str,
                         mapping: dict, score: float, overrides: Optional[dict] = None) -> List[Concept]:
    if system_id not in kb.by_id:
        raise ValidationFailed(f"unknown knowledge system '{system_id}'")
    eng = kb.engine(ScoreWeights(**weights) if weights else None)
    return derive_concepts(Problem.from_dict(problem), _model_from_output(extraction), eng.by_id[system_id],
                           eng.models[system_id], _mapping_from_dict(mapping), float(score), overrides)


def hypothesis_for_concept(concept: dict, problem: dict, context: Optional[dict] = None) -> dict:
    hyps = generate([Concept(**concept)], Problem.from_dict(problem), context)
    return hyps[0].to_dict()


def run_arms(spec: dict, seed: int) -> dict:
    """Run baseline and proposed arms with the same seed. Same seed and spec give identical output."""
    if not spec or not spec.get("kind") or not spec.get("baseline") or not spec.get("proposed"):
        raise ValidationFailed("hypothesis has no applicable experiment model; define the metric and model first")
    try:
        base = run_experiment(spec["kind"], spec["baseline"], seed)
        prop = run_experiment(spec["kind"], spec["proposed"], seed)
    except KeyError as e:
        raise ValidationFailed(str(e))
    return {"metric": spec.get("metric"), "direction": spec.get("direction"), "seed": seed,
            "baseline": base.metrics, "proposed": prop.metrics, "config_hash": config_hash({"spec": spec, "seed": seed}),
            "code_version": CODE_VERSION, "limitations": prop.limitations, "disclaimer": MODEL_DISCLAIMER}


def validate_hypothesis(hypothesis: dict, seeds: int = 20) -> dict:
    h = _hypothesis_from_dict(hypothesis)
    v = validate(h, tuple(range(seeds)))
    return v.to_dict()
