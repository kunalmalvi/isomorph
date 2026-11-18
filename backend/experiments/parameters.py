"""Parameter records: a value plus where it came from and how uncertain it is. Stdlib only, domain independent.

A record never certifies anything. `verification` defaults to 'unverified_no_network' because values recalled
without access to the source cannot be checked. Ranges are either from a source or an analyst's judgment, and
`range_basis` says which.
"""
import math
from dataclasses import dataclass, asdict
from typing import Any, Dict

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
        if not self.verification.strip():
            raise ValueError(f"{self.name}: verification must be stated")

    @property
    def has_range(self) -> bool:
        return self.high > self.low

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParameterRecord":
        return cls(**d)
