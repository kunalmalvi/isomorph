"""Validation of hypotheses by seeded baseline-vs-proposed simulation.

Outcome rules (documented, deterministic):
- untested: no applicable experiment or no baseline.
- supported: proposed wins in at least `min_win_rate` of seeds AND mean relative improvement >= min_effect.
- refuted: mean improvement <= 0 or win rate below 0.5.
- inconclusive: everything else.
'supported' always carries a caveat that the evidence is simulation under stated assumptions only.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from experiments import run_experiment, CODE_VERSION, MODEL_DISCLAIMER
from experiments.runners import LIMITATIONS
from ..schemas import Hypothesis, Validation


def _improvement(b: float, p: float, direction: str) -> float:
    denom = abs(b) if abs(b) > 1e-12 else 1.0
    return (b - p) / denom if direction == "lower" else (p - b) / denom


def validate(h: Hypothesis, seeds: Sequence[int] = tuple(range(20)), min_win_rate: float = 0.9) -> Validation:
    spec = h.experiment
    if not spec or not spec.get("baseline") or not spec.get("proposed"):
        why = "no applicable experiment" if not spec else "baseline arm missing"
        return Validation(h.id, "untested", f"Not tested: {why}. No claim about this hypothesis is made.", "none",
                          {"reason": why})
    kind, metric, direction = spec["kind"], spec["metric"], spec["direction"]
    min_effect = spec.get("min_effect", 0.05)
    seeds = [0] if spec.get("deterministic") else list(seeds)
    imps, wins, bvals, pvals = [], 0, [], []
    all_b: Dict[str, List[float]] = {}
    all_p: Dict[str, List[float]] = {}
    hashes = None
    for s in seeds:
        rb = run_experiment(kind, spec["baseline"], s)
        rp = run_experiment(kind, spec["proposed"], s)
        hashes = hashes or (rb.config_hash, rp.config_hash)
        b, p = rb.metrics[metric], rp.metrics[metric]
        bvals.append(b)
        pvals.append(p)
        imp = _improvement(b, p, direction)
        imps.append(imp)
        wins += 1 if imp > 0 else 0
        for k, v in rb.metrics.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                all_b.setdefault(k, []).append(v)
        for k, v in rp.metrics.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                all_p.setdefault(k, []).append(v)
    n = len(seeds)
    mean_imp = sum(imps) / n
    sd = math.sqrt(sum((x - mean_imp) ** 2 for x in imps) / (n - 1)) if n > 1 else 0.0
    ci = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    win_rate = wins / n
    if win_rate >= min_win_rate and mean_imp >= min_effect:
        outcome = "supported"
    elif mean_imp <= 0 or win_rate < 0.5:
        outcome = "refuted"
    else:
        outcome = "inconclusive"
    other_changes = []  # other metrics that moved by more than 5% in either direction
    for k in sorted(all_b):
        mb, mp = sum(all_b[k]) / n, sum(all_p[k]) / n
        if k != metric and abs(mb) > 1e-12 and abs(mp - mb) / abs(mb) > 0.05:
            other_changes.append({"metric": k, "baseline_mean": mb, "proposed_mean": mp})
    caveats = [MODEL_DISCLAIMER, LIMITATIONS[kind]]
    if outcome == "supported":
        caveats.insert(0, "SUPPORTED IN SIMULATION ONLY under the stated model assumptions; not confirmed by real-world evidence.")
    if spec.get("deterministic"):
        caveats.append("Experiment is deterministic, so a single run is reported; win rate is not a statistical measure here.")
    caveats += list(spec.get("notes", []))
    evidence = {"experiment_kind": kind, "metric": metric, "direction": direction, "seeds": seeds, "n": n,
                "config_hashes": list(hashes) if hashes else [], "code_version": CODE_VERSION,
                "baseline_mean": sum(bvals) / n, "proposed_mean": sum(pvals) / n,
                "mean_relative_improvement": mean_imp, "ci95_half_width": ci, "win_rate": win_rate,
                "min_effect": min_effect, "min_win_rate": min_win_rate, "other_metric_changes": other_changes}
    return Validation(h.id, outcome, " ".join(caveats), f"seeded simulation: {kind}", evidence)
