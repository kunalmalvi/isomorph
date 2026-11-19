"""Application layer for the self-improving loop: records evidence, runs gated improvement cycles, rolls back. Stdlib only.

No AI provider is called here. Learning is limited to the perception lexicon overlay and conditional priors, and a
regression gate on frozen sets protects against regressions. The gate cannot detect harm those sets do not cover.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from core.errors import ValidationFailed
from intelligence.learning_engine import EvidenceLog, ModelRegistry, build_candidate
from intelligence.learning_engine.loop import EVIDENCE_KINDS, validate_role, validate_term
from intelligence.schemas import ROLES

LIMITS = ("Learning is limited to two things: a lexicon overlay (words the user corrected to a role, used when perception "
          "cannot place a word) and conditional priors (small nudges of at most 0.1 that apply only under the recorded "
          "conditions). A gate on frozen sets (perception held-out, retrieval held-out, tuning benchmarks) rejects any "
          "candidate that lowers a metric. The gate cannot detect harm that those sets do not cover, and a pass on "
          "metrics that did not change is not evidence that a change helps. Conditional priors are stored and versioned "
          "but only the investigate pipeline reads them; the app's orchestrator does not, so a prior does not change "
          "an orchestrator run today. Learned words do apply to local perception.")


def normalize_term(label: str) -> str:
    if not isinstance(label, str):
        raise ValidationFailed("term must be a string")
    return " ".join(label.lower().split())


class LearningService:
    def __init__(self, directory: str, clock: Callable[[], int] = lambda: int(time.time())):
        import os
        os.makedirs(directory, exist_ok=True)
        self.evidence = EvidenceLog(os.path.join(directory, "evidence.jsonl"), clock)
        self.registry = ModelRegistry(directory, clock)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ reads
    def active(self) -> dict:
        return self.registry.active()

    def counts(self) -> dict:
        out = {k: 0 for k in EVIDENCE_KINDS}
        for e in self.evidence.events:
            out[e["kind"]] += 1
        out["total"] = len(self.evidence.events)
        return out

    @staticmethod
    def summarize(v: dict) -> dict:
        cfg = v["config"]
        return {"id": v["id"], "parent": v["parent"], "created": v["created"], "status": v["status"], "reason": v["reason"],
                "lexicon_terms": len(cfg["lexicon_overlay"]), "priors": len(cfg["priors"]),
                "evidence_count": len(v["evidence_ids"]), "gate": v["gate"], "config": cfg}

    def status(self) -> dict:
        with self._lock:
            active = self.registry.active()
            hist = self.registry.history()
            cand, report, used_ids = build_candidate(self.evidence, active["config"])
            repeat = pending = False
            if cand != active["config"]:
                repeat = self.registry.last_rejected_for(cand, used_ids) is not None
                pending = not repeat
            last_gate = next((self.summarize(v) for v in reversed(hist) if v["gate"]), None)
            return {"active": self.summarize(active), "evidence": self.counts(), "pending": {
                        "would_change": pending, "report": report,
                        "lexicon_terms": cand["lexicon_overlay"] if pending else {},
                        "already_rejected": repeat,
                        "note": "Preview from the recorded evidence only. Nothing changes until a cycle passes the gate."},
                    "last_gate": last_gate, "versions": len(hist), "limits": LIMITS}

    def versions(self) -> dict:
        with self._lock:
            return {"active": self.registry.active()["id"], "items": [self.summarize(v) for v in self.registry.history()],
                    "audit": self.registry.audit()[-50:], "limits": LIMITS}

    # ------------------------------------------------------------------ evidence
    def record_correction(self, term: str, role: str, run_id: Optional[str] = None) -> dict:
        t = normalize_term(term)
        try:
            validate_term(t)
            validate_role(role)
        except ValueError as e:
            raise ValidationFailed(str(e), {"roles": list(ROLES)})
        with self._lock:
            payload = {"term": t, "role": role}
            if run_id:
                payload["run_id"] = run_id
            ev = self.evidence.append("role_correction", payload)
        return ev

    def record_feedback(self, run_id: str, hypothesis_id: str, decision: str, concept_type: str, query_domain: Optional[str]) -> Optional[dict]:
        """Evidence from a reviewer decision. 'none' is not evidence. Returns None when nothing is recorded."""
        if decision == "none" or not concept_type:
            return None
        cond = {"query_domain": query_domain} if query_domain else {}
        with self._lock:
            return self.evidence.append("hypothesis_feedback", {"run_id": run_id, "hypothesis_id": hypothesis_id, "decision": decision,
                                                                 "concept_type": concept_type, "conditions": cond})

    def term_support(self, term: str) -> dict:
        roles: Dict[str, set] = {}
        for e in self.evidence.by_kind("role_correction"):
            p = e["payload"]
            if p["term"] == term:
                roles.setdefault(p["role"], set()).add(p.get("run_id") or e["id"])
        return {r: len(v) for r, v in sorted(roles.items())}

    # ------------------------------------------------------------------ cycle and rollback
    def cycle(self) -> dict:
        with self._lock:
            before = self.registry.active()
            cand, report, used = build_candidate(self.evidence, before["config"])
            base = {"before": before["id"], "proposal": report, "evidence_used": len(used)}
            if cand == before["config"]:
                return dict(base, changed=False, accepted=None, after=before["id"], metrics=None,
                            message="Nothing changed: the recorded evidence does not support any new lexicon term or prior "
                                    "(a term needs corrections from 2 distinct runs that agree, a prior needs 3 matching decisions).")
            prior = self.registry.last_rejected_for(cand, used)
            if prior is not None:
                return dict(base, changed=False, accepted=False, candidate=prior["id"], after=before["id"], metrics=None,
                            message=f"Skipped: the same candidate was already rejected as {prior['id']} on this evidence "
                                    f"({prior['gate']['note']}). Record new evidence to try again.")
            v = self.registry.propose(cand, used, reason=f"improvement cycle from {len(used)} evidence events")
            gate = v["gate"]
            if v["status"] == "active":
                msg = f"Accepted as {v['id']}: {gate['note']}."
            else:
                msg = f"Rejected candidate {v['id']}: {gate['note']}. The active version stays {before['id']}."
            return dict(base, changed=v["status"] == "active", accepted=v["status"] == "active", candidate=v["id"],
                        after=self.registry.active()["id"], metrics=gate["metrics"], sensitive=gate["sensitive"],
                        regressions=gate["regressions"], message=msg)

    def rollback(self, to: Optional[str] = None, reason: str = "") -> dict:
        with self._lock:
            before = self.registry.active()["id"]
            try:
                v = self.registry.rollback(to, reason or "rolled back by the user")
            except ValueError as e:
                raise ValidationFailed(str(e))
            return {"before": before, "active": v["id"], "message": f"Rolled back from {before} to {v['id']}. The version {before} stays in the history."}
