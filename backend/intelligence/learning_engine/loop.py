"""Self-improving loop core: evidence log, versioned learned-config registry, proposal builders. Stdlib only.

The loop learns ONLY from recorded evidence (user role corrections, hypothesis feedback, mapping edits and
experiment outcomes). The frozen held-out and tuning files are read by the regression gate (gate.py) and by the
leak guard in this module, never to derive a role or a prior. Every change is a new version in a registry. A
version is activated only if the gate shows no metric below the active config. Rejections, accepts and rollbacks
are written to an append-only audit log. Time is injected (no hidden clock) so tests are reproducible.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover (non-POSIX)
    fcntl = None

from ..schemas import ROLES

EVIDENCE_KINDS = ("role_correction", "hypothesis_feedback", "experiment_outcome", "mapping_edit")
# Mirrors services.annotations.DECISIONS (the engine must not import from services; a test keeps them equal).
DECISIONS = ("none", "saved", "rejected", "promoted")
OUTCOMES = ("supported", "refuted", "inconclusive")
MAPPING_ACTIONS = ("accept", "reject", "edit")
VERSION_STATUSES = ("active", "rejected", "rolled_back", "superseded")
PRIOR_CAP = 0.1
MIN_PRIOR_N = 3
MIN_TERM_SUPPORT = 2
MIN_TERM_AGREEMENT = 0.8
_TERM_RE = re.compile(r"^[a-z]+( [a-z]+){0,3}$")
_COND_TYPES = (str, int, float, bool)


def empty_config() -> dict:
    return {"lexicon_overlay": {}, "priors": []}


# ------------------------------------------------------------------ validation helpers

def validate_term(term) -> str:
    if not isinstance(term, str) or not _TERM_RE.match(term):
        raise ValueError("term must be 1 to 4 lowercase alphabetic words separated by single spaces")
    return term


def validate_role(role) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {list(ROLES)}")
    return role


def _validate_conditions(cond) -> dict:
    if cond is None:
        return {}
    if not isinstance(cond, dict) or not all(isinstance(k, str) and isinstance(v, _COND_TYPES) for k, v in cond.items()):
        raise ValueError("conditions must be a dict of string keys to scalar values")
    return dict(cond)


def _cond_key(cond: dict) -> str:
    return json.dumps(cond, sort_keys=True)


def validate_config(config: dict) -> dict:
    """Check shape, roles, terms and prior bounds. Returns a normalized deep copy."""
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    overlay = config.get("lexicon_overlay", {})
    priors = config.get("priors", [])
    if not isinstance(overlay, dict) or not isinstance(priors, list):
        raise ValueError("config needs lexicon_overlay (dict) and priors (list)")
    out_overlay = {validate_term(t): validate_role(r) for t, r in overlay.items()}
    out_priors = []
    for p in priors:
        if not isinstance(p, dict) or not isinstance(p.get("key"), str) or not p["key"]:
            raise ValueError("each prior needs a non-empty key")
        n, value = p.get("n"), p.get("value")
        if not isinstance(n, int) or n < MIN_PRIOR_N:
            raise ValueError(f"a prior needs n >= {MIN_PRIOR_N}")
        if not isinstance(value, (int, float)) or abs(value) > PRIOR_CAP + 1e-12:
            raise ValueError(f"prior value must be within [-{PRIOR_CAP}, {PRIOR_CAP}]")
        q = dict(p)
        q["conditions"] = _validate_conditions(p.get("conditions"))
        out_priors.append(q)
    return {"lexicon_overlay": dict(sorted(out_overlay.items())),
            "priors": sorted(out_priors, key=lambda p: (p["key"], _cond_key(p["conditions"])))}


def _atomic_write(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _read_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _append_jsonl(path: str, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")


@contextlib.contextmanager
def _file_lock(path: str):
    """Exclusive inter-process lock on path + '.lock' (no-op where fcntl is unavailable)."""
    if fcntl is None:
        yield
        return
    with open(path + ".lock", "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ------------------------------------------------------------------ evidence log

class EvidenceLog:
    """Append-only evidence. In memory when path is None, otherwise a JSONL file. Invalid input raises ValueError."""

    def __init__(self, path: Optional[str] = None, clock: Callable[[], int] = lambda: 0):
        self.path = path
        self.clock = clock
        self._events: List[dict] = _read_jsonl(path) if path else []

    @property
    def events(self) -> List[dict]:
        """All events. With a file, re-read each time so events written by another process are visible."""
        if self.path:
            self._events = _read_jsonl(self.path)
        return self._events

    def append(self, kind: str, payload: dict, provenance: Optional[str] = None) -> dict:
        if kind not in EVIDENCE_KINDS:
            raise ValueError(f"kind must be one of {list(EVIDENCE_KINDS)}")
        expected = "experiment" if kind == "experiment_outcome" else "user"
        if provenance is not None and provenance != expected:
            raise ValueError(f"provenance for {kind} must be '{expected}'")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        clean = self._clean(kind, payload)
        if not self.path:
            ev = {"id": f"ev-{len(self._events) + 1}", "timestamp": self.clock(), "kind": kind, "payload": clean,
                  "provenance": expected}
            self._events.append(ev)
            return ev
        with _file_lock(self.path):  # re-read under the lock so ids stay unique across processes
            existing = _read_jsonl(self.path)
            ev = {"id": f"ev-{len(existing) + 1}", "timestamp": self.clock(), "kind": kind, "payload": clean,
                  "provenance": expected}
            _append_jsonl(self.path, ev)
            self._events = existing + [ev]
        return ev

    @staticmethod
    def _clean(kind: str, p: dict) -> dict:
        run_id = p.get("run_id")
        if run_id is not None and not isinstance(run_id, str):
            raise ValueError("run_id must be a string")
        out: dict = {} if run_id is None else {"run_id": run_id}
        if kind == "role_correction":
            out.update(term=validate_term(p.get("term")), role=validate_role(p.get("role")))
        elif kind in ("hypothesis_feedback", "experiment_outcome"):
            ct = p.get("concept_type")
            if not isinstance(ct, str) or not ct:
                raise ValueError("concept_type is required")
            out["concept_type"] = ct
            out["conditions"] = _validate_conditions(p.get("conditions"))
            if kind == "hypothesis_feedback":
                if p.get("decision") not in DECISIONS:
                    raise ValueError(f"decision must be one of {list(DECISIONS)}")
                out["decision"] = p["decision"]
                hid = p.get("hypothesis_id")
                if hid is not None:
                    if not isinstance(hid, str) or not hid:
                        raise ValueError("hypothesis_id must be a non-empty string")
                    out["hypothesis_id"] = hid
            else:
                if p.get("outcome") not in OUTCOMES:
                    raise ValueError(f"outcome must be one of {list(OUTCOMES)}")
                if p.get("evidence_level", "simulation") not in ("none", "simulation"):
                    raise ValueError("experiment outcomes are simulations and cannot be recorded as real_world")
                out["outcome"] = p["outcome"]
                out["evidence_level"] = "simulation"
        else:  # mapping_edit
            if p.get("action") not in MAPPING_ACTIONS:
                raise ValueError(f"action must be one of {list(MAPPING_ACTIONS)}")
            for k in ("source", "target"):
                if not isinstance(p.get(k), str) or not p[k]:
                    raise ValueError(f"{k} is required")
                out[k] = p[k]
            out["action"] = p["action"]
        return out

    def by_kind(self, *kinds: str) -> List[dict]:
        return [e for e in self.events if e["kind"] in kinds]


# ------------------------------------------------------------------ leak guard

def _words(text: str) -> List[str]:
    return [_stem(w) for w in re.findall(r"[a-z]+", str(text).lower())]


def _stem(w: str) -> str:
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def heldout_vocabulary(data_root: Optional[str] = None) -> Tuple[Set[str], List[List[str]]]:
    """(head-word set of perception held-out phrases, word sequences of all frozen texts). Read only by the leak guard."""
    from knowledge_base.loader import data_dir
    base = os.path.join(data_dir(data_root), "benchmark_problems")
    phrase_words: Set[str] = set()
    sequences: List[List[str]] = []
    with open(os.path.join(base, "perception_heldout.json"), encoding="utf-8") as f:
        for prob in json.load(f)["problems"]:
            for g in prob["entities"]:
                ws = _words(g["phrase"])
                phrase_words.update(ws)
                sequences.append(ws)
            sequences.append(_words(prob.get("text", "")))

    def query_texts(q: dict) -> Iterable[str]:
        yield from (str(q.get(k, "")) for k in ("title", "statement", "goal"))
        for n in q.get("graph", {}).get("nodes", []):
            yield str(n.get("label", ""))

    with open(os.path.join(base, "heldout_labels.json"), encoding="utf-8") as f:
        for item in json.load(f)["items"]:
            sequences.extend(_words(t) for t in query_texts(item["query"]))
    with open(os.path.join(base, "benchmarks.json"), encoding="utf-8") as f:
        for pair in json.load(f)["pairs"]:
            sequences.extend(_words(t) for t in query_texts(pair["query"]))
    return phrase_words, sequences


def heldout_overlap(term: str, vocab: Tuple[Set[str], List[List[str]]]) -> bool:
    """True if the term occurs in a frozen phrase or query text, or its head word is a head of a held-out phrase word."""
    phrase_words, sequences = vocab
    t = _words(term)
    if not t:
        return False
    if t[-1] in phrase_words:
        return True
    n = len(t)
    return any(seq[i:i + n] == t for seq in sequences for i in range(len(seq) - n + 1))


# ------------------------------------------------------------------ proposal builders (evidence only)

def propose_lexicon(events: List[dict], base: Optional[dict] = None,
                    vocab: Optional[Tuple[Set[str], List[List[str]]]] = None) -> Tuple[dict, dict]:
    """Candidate config plus a report. A term needs >= 2 distinct runs/events and >= 80% agreement on one role."""
    base = validate_config(base or empty_config())
    vocab = vocab if vocab is not None else heldout_vocabulary()
    # one vote per (run or event, term); a later correction in the same run replaces the earlier one
    votes: Dict[Tuple[str, str], str] = {}
    for ev in events:
        if ev["kind"] != "role_correction":
            continue
        p = ev["payload"]
        votes[(p.get("run_id") or ev["id"], p["term"])] = p["role"]
    support: Dict[str, Dict[str, Set[str]]] = {}
    for (distinct, term), role in votes.items():
        support.setdefault(term, {}).setdefault(role, set()).add(distinct)
    overlay = dict(base["lexicon_overlay"])
    learned, skipped = [], []
    for term in sorted(support):
        roles = support[term]
        total = sum(len(v) for v in roles.values())
        role, keys = sorted(roles.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0]
        agreement = len(keys) / total
        if len(keys) < MIN_TERM_SUPPORT:
            skipped.append({"term": term, "reason": "insufficient_evidence", "support": len(keys)})
        elif agreement < MIN_TERM_AGREEMENT:
            skipped.append({"term": term, "reason": "conflict", "roles": {r: len(v) for r, v in sorted(roles.items())}})
        elif heldout_overlap(term, vocab):
            skipped.append({"term": term, "reason": "heldout_overlap"})
        elif overlay.get(term) != role:
            overlay[term] = role
            learned.append({"term": term, "role": role, "support": len(keys), "agreement": round(agreement, 4)})
    cand = {"lexicon_overlay": dict(sorted(overlay.items())), "priors": base["priors"]}
    return cand, {"learned": learned, "skipped": skipped}


def propose_priors(events: List[dict], base: Optional[dict] = None) -> Tuple[dict, dict]:
    """Conditional priors from hypothesis feedback and experiment outcomes, grouped by (concept_type, conditions)."""
    base = validate_config(base or empty_config())
    groups: Dict[Tuple[str, str], dict] = {}
    # feedback on the same hypothesis of the same run counts once: the latest decision wins
    latest: Dict[Tuple[str, str], str] = {}
    for ev in events:
        p = ev["payload"]
        if ev["kind"] == "hypothesis_feedback" and p.get("run_id") and p.get("hypothesis_id"):
            latest[(p["run_id"], p["hypothesis_id"])] = ev["id"]
    for ev in events:
        p = ev["payload"]
        if ev["kind"] == "hypothesis_feedback" and p.get("run_id") and p.get("hypothesis_id") \
                and latest[(p["run_id"], p["hypothesis_id"])] != ev["id"]:
            continue
        if ev["kind"] == "hypothesis_feedback":
            if p["decision"] == "none":
                continue
            bucket = "accepted" if p["decision"] in ("saved", "promoted") else "rejected"
            basis = "user_feedback"
        elif ev["kind"] == "experiment_outcome":
            bucket = {"supported": "accepted", "refuted": "rejected", "inconclusive": "neutral"}[p["outcome"]]
            basis = "simulation"
        else:
            continue
        g = groups.setdefault((p["concept_type"], _cond_key(p["conditions"])),
                              {"conditions": p["conditions"], "accepted": 0, "rejected": 0, "neutral": 0, "bases": set()})
        g[bucket] += 1
        g["bases"].add(basis)
    priors, skipped = [], []
    for (ct, ck), g in sorted(groups.items()):
        n = g["accepted"] + g["rejected"] + g["neutral"]
        if n < MIN_PRIOR_N:
            skipped.append({"key": ct, "conditions": g["conditions"], "n": n, "reason": "insufficient_evidence"})
            continue
        value = round(max(-PRIOR_CAP, min(PRIOR_CAP, PRIOR_CAP * (g["accepted"] - g["rejected"]) / (n + 2))), 6)
        priors.append({"key": ct, "conditions": g["conditions"], "n": n, "accepted": g["accepted"],
                       "rejected": g["rejected"], "neutral": g["neutral"], "value": value,
                       "basis": "+".join(sorted(g["bases"]))})
    cand = {"lexicon_overlay": base["lexicon_overlay"], "priors": priors}
    return validate_config(cand), {"priors": len(priors), "skipped": skipped}


def build_candidate(log: EvidenceLog, active: Optional[dict] = None,
                    vocab: Optional[Tuple[Set[str], List[List[str]]]] = None) -> Tuple[dict, dict, List[str]]:
    """Lexicon and priors candidate from the whole evidence log. Returns (config, report, evidence ids used)."""
    lex, lex_report = propose_lexicon(log.events, active, vocab)
    pri, pri_report = propose_priors(log.events, active)
    cand = {"lexicon_overlay": lex["lexicon_overlay"], "priors": pri["priors"]}
    used = [e["id"] for e in log.events if e["kind"] != "mapping_edit"]
    return validate_config(cand), {"lexicon": lex_report, "priors": pri_report}, used


def learned_prior(config: Optional[dict], concept_type: str, conditions: Optional[dict]) -> float:
    """Prior value for concept_type under the run's conditions. A prior applies only when ALL of its recorded
    conditions equal the run's values and n >= MIN_PRIOR_N; otherwise 0.0. The most specific match wins."""
    best = None
    cond = conditions or {}
    for p in (config or {}).get("priors", []):
        if p["key"] != concept_type or p["n"] < MIN_PRIOR_N:
            continue
        if not all(k in cond and cond[k] == v for k, v in p["conditions"].items()):
            continue
        rank = (len(p["conditions"]), p["n"])
        if best is None or rank > best[0]:
            best = (rank, p["value"])
    return 0.0 if best is None else max(-PRIOR_CAP, min(PRIOR_CAP, float(best[1])))


# ------------------------------------------------------------------ registry

class ModelRegistry:
    """Versioned learned configs in a directory: versions/<id>.json, active.json, audit.jsonl (append-only)."""

    def __init__(self, directory: str, clock: Callable[[], int] = lambda: 0):
        self.dir = directory
        self.clock = clock
        os.makedirs(os.path.join(directory, "versions"), exist_ok=True)
        self._audit_path = os.path.join(directory, "audit.jsonl")
        self._active_path = os.path.join(directory, "active.json")
        if not os.path.exists(self._active_path):
            v0 = {"id": "v0", "parent": None, "created": clock(), "config": empty_config(), "evidence_ids": [],
                  "status": "active", "gate": None, "reason": "empty baseline config"}
            self._save(v0)
            _atomic_write(self._active_path, {"active": "v0"})

    def _vpath(self, vid: str) -> str:
        if not re.match(r"^v\d+$", vid):
            raise ValueError("invalid version id")
        return os.path.join(self.dir, "versions", vid + ".json")

    def _save(self, v: dict) -> None:
        _atomic_write(self._vpath(v["id"]), v)

    def get(self, vid: str) -> dict:
        try:
            with open(self._vpath(vid), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise ValueError(f"unknown version {vid}") from None

    def active(self) -> dict:
        with open(self._active_path, encoding="utf-8") as f:
            return self.get(json.load(f)["active"])

    def _set_active(self, vid: str) -> None:
        _atomic_write(self._active_path, {"active": vid})

    def history(self) -> List[dict]:
        names = [n for n in os.listdir(os.path.join(self.dir, "versions")) if n.endswith(".json")]
        ids = sorted((n[:-5] for n in names), key=lambda i: int(i[1:]))
        return [self.get(i) for i in ids]

    def audit(self) -> List[dict]:
        return _read_jsonl(self._audit_path)

    def _log(self, action: str, version: str, reason: str, detail: Optional[dict] = None) -> dict:
        with _file_lock(self._audit_path):
            entry = {"seq": len(self.audit()) + 1, "timestamp": self.clock(), "action": action, "version": version,
                     "reason": reason, "detail": detail or {}}
            _append_jsonl(self._audit_path, entry)
        return entry

    def last_rejected_for(self, config: dict, evidence_ids: List[str]) -> Optional[dict]:
        """The latest rejected version with exactly this config and evidence, or None."""
        config = validate_config(config)
        ids = sorted(evidence_ids)
        for v in reversed(self.history()):
            if v["status"] == "rejected" and v["config"] == config and v["evidence_ids"] == ids:
                return v
        return None

    def propose(self, config: dict, evidence_ids: Optional[List[str]] = None, reason: str = "",
                gate_fn: Optional[Callable[..., dict]] = None) -> Optional[dict]:
        """Create a version from config and gate it against the active one. Accepted versions become active; rejected
        versions are stored with their gate report and the active version is unchanged. Returns None when the
        candidate equals the active config."""
        config = validate_config(config)
        current = self.active()
        if config == current["config"]:
            return None
        if gate_fn is None:
            from .gate import run_gate as gate_fn  # noqa: F811
        vid = f"v{len(self.history())}"
        v = {"id": vid, "parent": current["id"], "created": self.clock(), "config": config,
             "evidence_ids": sorted(evidence_ids or []), "status": "rejected", "gate": None, "reason": reason}
        self._log("propose", vid, reason, {"parent": current["id"], "evidence_ids": v["evidence_ids"]})
        report = gate_fn(config, current["config"], vid, current["id"])
        v["gate"] = report
        if report["accepted"]:
            v["status"] = "active"
            current["status"] = "superseded"
            self._save(current)
            self._save(v)
            self._set_active(vid)
            self._log("accept", vid, report["note"], {"metrics": report["metrics"], "sensitive": report["sensitive"]})
        else:
            self._save(v)
            self._log("reject", vid, report["note"], {"metrics": report["metrics"], "regressions": report["regressions"]})
        return v

    def activate(self, vid: str, reason: str = "") -> dict:
        """Reactivate a previously accepted version (superseded or rolled back)."""
        v = self.get(vid)
        if v["status"] not in ("superseded", "rolled_back") or not (v["gate"] or v["id"] == "v0"):
            raise ValueError(f"version {vid} cannot be activated from status {v['status']}")
        if v["gate"] and not v["gate"]["accepted"]:
            raise ValueError(f"version {vid} failed the gate")
        current = self.active()
        current["status"] = "superseded"
        self._save(current)
        v["status"] = "active"
        self._save(v)
        self._set_active(vid)
        self._log("activate", vid, reason, {"from": current["id"]})
        return v

    def rollback(self, to: Optional[str] = None, reason: str = "") -> dict:
        """Make `to` (default: the parent of the active version) active again. The rolled-back version stays on record."""
        current = self.active()
        target_id = to or current["parent"]
        if target_id is None:
            raise ValueError("the active version has no parent to roll back to")
        if target_id == current["id"]:
            raise ValueError("version is already active")
        target = self.get(target_id)
        if target["status"] == "rejected":
            raise ValueError("cannot roll back to a rejected version")
        current["status"] = "rolled_back"
        self._save(current)
        target["status"] = "active"
        self._save(target)
        self._set_active(target_id)
        self._log("rollback", target_id, reason, {"from": current["id"]})
        return target

    def diff(self, a: str, b: str) -> dict:
        ca, cb = self.get(a)["config"], self.get(b)["config"]
        la, lb = ca["lexicon_overlay"], cb["lexicon_overlay"]
        pa = {(p["key"], _cond_key(p["conditions"])): p for p in ca["priors"]}
        pb = {(p["key"], _cond_key(p["conditions"])): p for p in cb["priors"]}
        return {
            "lexicon_added": {t: lb[t] for t in sorted(lb) if t not in la},
            "lexicon_removed": {t: la[t] for t in sorted(la) if t not in lb},
            "lexicon_changed": {t: {"from": la[t], "to": lb[t]} for t in sorted(la) if t in lb and la[t] != lb[t]},
            "priors_added": [pb[k] for k in sorted(pb) if k not in pa],
            "priors_removed": [pa[k] for k in sorted(pa) if k not in pb],
            "priors_changed": [{"from": pa[k], "to": pb[k]} for k in sorted(pa) if k in pb and pa[k] != pb[k]],
        }
