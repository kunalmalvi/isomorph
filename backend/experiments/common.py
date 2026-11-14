"""Shared experiment helpers: config hashing, run records. Stdlib only."""
import hashlib
import json
from typing import Any, Dict

CODE_VERSION = "isomorph-experiments-0.1.0"
MODEL_DISCLAIMER = ("Simulation results come from simplified models with stated assumptions. "
                    "They are not real-world validation.")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(config: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode()).hexdigest()[:16]
