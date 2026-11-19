"""Regression gate for learned configs. Stdlib only.

Metrics are computed for the active config and for a candidate on the frozen sets (perception held-out set,
retrieval held-out set, tuning benchmarks). A candidate is accepted only if NO metric is lower than the active
config by more than TOLERANCE. These files are read here only to evaluate; learning never derives anything from them.

Honesty: a learned lexicon overlay can change the perception metrics. Learned priors and retrieval do not
interact today, so retrieval metrics are constant and priors are metric-neutral. The report says so
(`sensitive` is False) instead of presenting a pass as proof of improvement.
"""
from __future__ import annotations

from typing import Dict, Optional

TOLERANCE = 1e-9
METRIC_NAMES = ("perception.role_accuracy", "perception.precision_when_assigned", "perception.detection_recall",
                "heldout.mrr_strong", "heldout.ndcg_at_10", "tuning.mrr_primary")


def compute_metrics(config: Optional[dict], version_id: Optional[str] = None) -> Dict[str, float]:
    """Frozen-set metrics with the config's lexicon overlay applied to perception."""
    from evaluation import benchmarks, heldout, perception
    overlay = dict((config or {}).get("lexicon_overlay") or {}) or None
    pm, _ = perception.evaluate(overlay=overlay, overlay_version=version_id)
    _, hs = heldout.run()
    _, bs = benchmarks.run()
    prec = pm["precision_when_assigned"]
    return {
        "perception.role_accuracy": pm["role_accuracy"],
        "perception.precision_when_assigned": 0.0 if prec is None else prec,
        "perception.detection_recall": pm["detection_recall"],
        "heldout.mrr_strong": hs["mrr_strong"],
        "heldout.ndcg_at_10": hs["ndcg_at_10"],
        "tuning.mrr_primary": bs["mrr_primary"],
    }


def run_gate(candidate: dict, active: Optional[dict] = None, candidate_version: Optional[str] = None,
             active_version: Optional[str] = None) -> dict:
    """Compare candidate against active. Returns a report with the full before/after table."""
    before = compute_metrics(active, active_version)
    after = compute_metrics(candidate, candidate_version)
    table = {}
    regressions = []
    for name in METRIC_NAMES:
        delta = round(after[name] - before[name], 6)
        table[name] = {"before": before[name], "after": after[name], "delta": delta}
        if after[name] < before[name] - TOLERANCE:
            regressions.append(name)
    sensitive = any(abs(row["delta"]) > TOLERANCE for row in table.values())
    accepted = not regressions
    if not accepted:
        note = "rejected: lower than active on " + ", ".join(regressions)
    elif sensitive:
        note = "accepted: no metric dropped and at least one changed"
    else:
        note = ("accepted but gate not sensitive to this change: every metric is identical to the active config, "
                "so the gate gives no evidence that it helps")
    return {"accepted": accepted, "sensitive": sensitive, "regressions": regressions, "metrics": table, "note": note}
