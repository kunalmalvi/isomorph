"""Parameter records: a value plus where it came from and how uncertain it is. Stdlib only, domain independent.

A record never certifies anything. `verification` defaults to 'unverified_no_network' because values recalled
without access to the source cannot be checked. Ranges are either from a source or an analyst's judgment, and
`range_basis` says which.
"""
import math
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Mapping, Optional, Tuple

KINDS = ("user_input", "handbook", "assumption", "measured")
RANGE_BASES = ("source", "analyst_judgment", "none")
CONFIDENCES = ("high", "medium", "low")
DEFAULT_VERIFICATION = "unverified_no_network"


@dataclass
class ParameterRecord:
    name: str
    unit: str
    nominal: float
    low: float
    high: float
    kind: str
    source: str = ""
    range_basis: str = "none"
    confidence: str = "low"
    verification: str = DEFAULT_VERIFICATION
    notes: str = ""
    # Optional, user supplied: {other record name: rho}. Never defaulted. Empty means independent.
    correlations: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        for f in ("nominal", "low", "high"):
            v = getattr(self, f)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"{self.name}: {f} must be a finite number, got {v!r}")
            setattr(self, f, float(v))
        if not (self.low <= self.nominal <= self.high):
            raise ValueError(f"{self.name}: need low <= nominal <= high, got {self.low}, {self.nominal}, {self.high}")
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}")
        if self.range_basis not in RANGE_BASES:
            raise ValueError(f"{self.name}: range_basis must be one of {RANGE_BASES}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"{self.name}: confidence must be one of {CONFIDENCES}")
        if self.kind in ("handbook", "measured") and not self.source.strip():
            raise ValueError(f"{self.name}: a {self.kind} record needs a non-empty source")
        for other, rho in self.correlations.items():
            if other == self.name:
                raise ValueError(f"{self.name}: a parameter cannot be correlated with itself")
            if isinstance(rho, bool) or not isinstance(rho, (int, float)) or not math.isfinite(rho) or not -1.0 < rho < 1.0:
                raise ValueError(f"{self.name}: correlation with {other} must be strictly between -1 and 1, got {rho!r}")
        if not self.verification.strip():
            raise ValueError(f"{self.name}: verification must be stated")

    @property
    def has_range(self) -> bool:
        return self.high > self.low

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d["correlations"]:
            del d["correlations"]  # keep records without a declared correlation byte-identical to before
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParameterRecord":
        return cls(**d)


def correlations_from_records(records: Mapping[str, ParameterRecord],
                              paths: Optional[Mapping[str, str]] = None) -> Dict[Tuple[str, str], float]:
    """Collect user supplied correlations from records as {(path_a, path_b): rho} for monte_carlo.

    `paths` maps a record name to its sampling path (default: the name). Returns {} when no record declares one.
    A pair declared on both records must agree. Unknown partner names raise ValueError.
    """
    out: Dict[Tuple[str, str], float] = {}
    for name, r in records.items():
        for other, rho in r.correlations.items():
            if other not in records:
                raise ValueError(f"{name}: correlated with unknown parameter {other!r}")
            a, b = (paths or {}).get(name, name), (paths or {}).get(other, other)
            key = (a, b) if a <= b else (b, a)
            if key in out and out[key] != float(rho):
                raise ValueError(f"conflicting correlation declared for {key}")
            out[key] = float(rho)
    return out
