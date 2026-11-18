"""Constraint evaluation with deterministic validators.

Outcomes per constraint: satisfied, violated, insufficient_information (a needed value is missing).
Never guesses missing values. A transformation is 'blocked' if any hard constraint is violated and
'insufficient_information' if no hard constraint is violated but some cannot be evaluated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..schemas import Constraint

SATISFIED, VIOLATED, INSUFFICIENT = "satisfied", "violated", "insufficient_information"
OPS: Dict[str, Callable[[float, float], bool]] = {
    "<=": lambda a, b: a <= b + 1e-12, ">=": lambda a, b: a >= b - 1e-12,
    "<": lambda a, b: a < b, ">": lambda a, b: a > b, "==": lambda a, b: abs(a - b) <= 1e-9 * max(1.0, abs(b)),
}
Validator = Callable[[Dict[str, float], dict], Tuple[str, str]]
VALIDATORS: Dict[str, Validator] = {}


def register_validator(name: str):
    def deco(fn: Validator) -> Validator:
        VALIDATORS[name] = fn
        return fn
    return deco


@register_validator("bite_condition")
def _bite(values: Dict[str, float], params: dict) -> Tuple[str, str]:
    """Rolling bite condition: draft <= 2R * (1 - 1/sqrt(1 + mu^2)) for a two-roll mill. Needs h0, reduction fraction, R, mu."""
    need = ["thickness_mm", "reduction_fraction", "roll_radius_mm", "friction"]
    missing = [k for k in need if k not in values]
    if missing:
        return INSUFFICIENT, "missing values: " + ", ".join(missing)
    draft = values["thickness_mm"] * values["reduction_fraction"]
    # Same formula as experiments.runners.max_bite_draft (duplicated to avoid a package import cycle; a test keeps them equal).
    # The earlier limit lacked the factor 2, which is half the correct value (a conservative error).
    limit = 2.0 * values["roll_radius_mm"] * (1.0 - 1.0 / math.sqrt(1.0 + values["friction"] ** 2))
    ok = draft <= limit + 1e-12
    return (SATISFIED if ok else VIOLATED), f"draft {draft:.3f} mm vs maximum bite draft {limit:.3f} mm"


@register_validator("sum_at_most")
def _sum_at_most(values: Dict[str, float], params: dict) -> Tuple[str, str]:
    names, total = params["vars"], params["total"]
    missing = [n for n in names if n not in values]
    if missing:
        return INSUFFICIENT, "missing values: " + ", ".join(missing)
    s = sum(values[n] for n in names)
    return (SATISFIED if s <= total + 1e-12 else VIOLATED), f"sum {s:g} vs limit {total:g}"


@dataclass
class ConstraintResult:
    constraint_id: str
    kind: str
    outcome: str
    detail: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"constraint_id": self.constraint_id, "kind": self.kind, "outcome": self.outcome,
                "detail": self.detail, "description": self.description}


def _eval_expr(expr: dict, values: Dict[str, float]) -> Tuple[str, str]:
    if "all" in expr or "any" in expr:
        key = "all" if "all" in expr else "any"
        parts = [_eval_expr(e, values) for e in expr[key]]
        outs = [p[0] for p in parts]
        detail = "; ".join(p[1] for p in parts)
        if key == "all":
            if VIOLATED in outs:
                return VIOLATED, detail
            return (INSUFFICIENT if INSUFFICIENT in outs else SATISFIED), detail
        if SATISFIED in outs:
            return SATISFIED, detail
        return (INSUFFICIENT if INSUFFICIENT in outs else VIOLATED), detail
    if "validator" in expr:
        fn = VALIDATORS.get(expr["validator"])
        if fn is None:
            return INSUFFICIENT, f"unknown validator {expr['validator']}"
        return fn(values, expr.get("params", {}))
    var = expr.get("var")
    if var is None or var not in values:
        return INSUFFICIENT, f"value for '{var}' is not available"
    v = values[var]
    op = expr.get("op", "<=")
    if op == "between":
        ok = expr["min"] - 1e-12 <= v <= expr["max"] + 1e-12
        return (SATISFIED if ok else VIOLATED), f"{var}={v:g} within [{expr['min']:g}, {expr['max']:g}]: {ok}"
    if op not in OPS:
        return INSUFFICIENT, f"unsupported operator {op}"
    lim = expr["value"]
    ok = OPS[op](v, lim)
    return (SATISFIED if ok else VIOLATED), f"{var}={v:g} {op} {lim:g}: {ok}"


def evaluate(constraint: Constraint, values: Dict[str, float]) -> ConstraintResult:
    if not constraint.expression:
        return ConstraintResult(constraint.id, constraint.kind, INSUFFICIENT,
                                "constraint has no machine-checkable expression", constraint.description)
    out, detail = _eval_expr(constraint.expression, values)
    return ConstraintResult(constraint.id, constraint.kind, out, detail, constraint.description)


@dataclass
class ConstraintReport:
    status: str  # ok | blocked | insufficient_information
    results: List[ConstraintResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "results": [r.to_dict() for r in self.results], "warnings": self.warnings}


def check_all(constraints: Sequence[Constraint], values: Dict[str, float]) -> ConstraintReport:
    results = [evaluate(c, values) for c in constraints]
    warnings = []
    hard_v = [r for r in results if r.kind == "hard" and r.outcome == VIOLATED]
    hard_i = [r for r in results if r.kind == "hard" and r.outcome == INSUFFICIENT]
    for r in results:
        if r.kind == "soft" and r.outcome == VIOLATED:
            warnings.append(f"soft constraint {r.constraint_id} violated: {r.detail}")
    if hard_v:
        status = "blocked"
    elif hard_i:
        status = "insufficient_information"
    else:
        status = "ok"
    return ConstraintReport(status, results, warnings)
