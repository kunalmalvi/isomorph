"""General sensitivity analysis over any experiment kind in REGISTRY. Stdlib only, deterministic for a seed.

ranges: {path: (low, nominal, high)}. A path is a key of the params dict, or 'material.K' style to override one
entry of a copied material dict (a string material name is looked up in MATERIALS first).

Monte Carlo sampling: each parameter is drawn independently from a triangular distribution with mode at the
nominal value between low and high. This puts more weight near the nominal than a uniform draw and never leaves
[low, high]. It is a modelling choice, not a measured distribution. Pass sampling='uniform' for a flat draw.
"""
import copy
import random
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .runners import MATERIALS, run_experiment

Range = Tuple[float, float, float]


def _set_path(params: dict, path: str, value: float) -> None:
    if "." not in path:
        params[path] = value
        return
    head, key = path.split(".", 1)
    obj = params.get(head)
    if isinstance(obj, str):
        obj = MATERIALS[obj]
    obj = dict(obj or {})
    obj[key] = value
    params[head] = obj


def _with(base: dict, values: Dict[str, float]) -> dict:
    p = copy.deepcopy(base)
    for path, v in values.items():
        _set_path(p, path, v)
    return p


def _metric(kind: str, params: dict, metric: str, seed: int) -> float:
    return float(run_experiment(kind, params, seed).metrics[metric])


def one_at_a_time(kind: str, base_params: dict, ranges: Dict[str, Range], metric: str, seed: int = 0) -> List[Dict[str, Any]]:
    """Vary one parameter at a time to low and high. Returns rows sorted by swing, largest first (tornado)."""
    nominal = {k: r[1] for k, r in ranges.items()}
    rows = []
    for path, (lo, nom, hi) in ranges.items():
        vals = {}
        for tag, v in (("low", lo), ("nominal", nom), ("high", hi)):
            vals[tag] = _metric(kind, _with(base_params, dict(nominal, **{path: v})), metric, seed)
        rows.append({"parameter": path, "low_input": lo, "nominal_input": nom, "high_input": hi,
                     "metric_at_low": vals["low"], "metric_at_nominal": vals["nominal"], "metric_at_high": vals["high"],
                     "swing": abs(vals["high"] - vals["low"])})
    rows.sort(key=lambda r: (-r["swing"], r["parameter"]))
    return rows


def _pct(sorted_vals: Sequence[float], q: float) -> float:
    i = q * (len(sorted_vals) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def monte_carlo(kind: str, base_params: dict, ranges: Dict[str, Range], metric_names: Sequence[str], n: int = 500, seed: int = 0,
                predicate: Optional[Callable[[Dict[str, Any]], bool]] = None, sampling: str = "triangular",
                run_seed: Optional[int] = None) -> Dict[str, Any]:
    """Sample parameters inside [low, high], run the experiment, summarise each metric.
    The raw per-sample metric columns are returned under 'values' so callers can pair runs that share a seed.

    `predicate(metrics)` returns True for a passing sample; the result carries `pass_fraction` (None without a predicate).
    Sample order and values depend only on `seed`. The experiment's own seed is `run_seed` (default: the sample index).
    """
    if sampling not in ("triangular", "uniform"):
        raise ValueError("sampling must be 'triangular' or 'uniform'")
    rng = random.Random(seed)
    cols: Dict[str, List[float]] = {m: [] for m in metric_names}
    samples: List[Dict[str, float]] = []
    passed = 0
    for i in range(n):
        vals = {}
        for path in sorted(ranges):
            lo, nom, hi = ranges[path]
            if hi <= lo:
                vals[path] = nom
            elif sampling == "uniform":
                vals[path] = rng.uniform(lo, hi)
            else:
                vals[path] = rng.triangular(lo, hi, nom)
        samples.append(vals)
        metrics = run_experiment(kind, _with(base_params, vals), i if run_seed is None else run_seed).metrics
        for m in metric_names:
            cols[m].append(float(metrics[m]))
        if predicate is not None and predicate(metrics):
            passed += 1
    summary = {}
    for m, v in cols.items():
        s = sorted(v)
        summary[m] = {"min": s[0], "p05": _pct(s, 0.05), "median": _pct(s, 0.5), "p95": _pct(s, 0.95), "max": s[-1]}
    return {"n": n, "seed": seed, "sampling": sampling, "metrics": summary, "values": cols,
            "pass_fraction": (passed / n) if predicate is not None else None, "samples": samples}
