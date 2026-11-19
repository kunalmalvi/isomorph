"""Deterministic rule and keyword perception of problem text and CSV.

This is NOT language understanding. It is a lexicon lookup plus verb-cue patterns. It separates
facts (stated), inferences (derived by rule, e.g. a role from a keyword), assumptions (defaults the
extractor had to make), unknowns and clarification questions, and records source spans.
Passive voice, coreference and implicit entities are not handled; see `limitations`.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import contextvars
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..schemas import Problem, Graph, Node, Edge, Constraint, Variable, Provenance, ROLES

ROLE_LEXICON: Dict[str, List[str]] = {
    "source": ["supply", "source", "feed", "inflow", "inlet", "input", "supplier", "mains", "raw material", "sun", "fuel"],
    "producer": ["producer", "generator", "factory", "engine", "manufacturer", "farm", "plant growth"],
    "sink": ["sink", "outlet", "drain", "exit", "outflow", "discharge", "destination", "environment", "ground"],
    "consumer": ["consumer", "customer", "user", "demand", "client", "household", "patient"],
    "load": ["load", "roll force", "force", "weight", "stress", "payload"],
    "dissipater": ["friction", "damper", "drag", "wear", "heat loss", "resistor", "loss"],
    "buffer": ["buffer", "tank", "reservoir", "inventory", "stock", "queue", "battery", "storage", "cache",
               "capacitor", "backlog", "warehouse", "accumulator", "spring", "stockpile"],
    "conduit": ["pipe", "road", "channel", "line", "wire", "belt", "conveyor", "link", "corridor", "cable", "route",
                "track", "duct", "network"],
    "junction": ["junction", "node", "hub", "intersection", "manifold", "interchange"],
    "medium": ["strip", "sheet", "metal", "fluid", "water", "air", "temperature", "traffic", "material", "pressure",
               "product", "workpiece", "packet", "price", "energy", "heat", "wafer"],
    "regulator": ["valve", "regulator", "throttle", "limiter", "gate", "gap", "roll gap", "quota", "tariff"],
    "controller": ["controller", "thermostat", "governor", "scheduler", "algorithm", "manager", "planner", "operator",
                   "policy", "autopilot", "computer", "dispatcher"],
    "switch": ["switch", "relay", "breaker", "trigger"],
    "sensor": ["sensor", "gauge", "detector", "thermometer", "monitor", "meter", "camera", "probe", "scale"],
    "actuator": ["actuator", "motor", "heater", "pump", "cylinder", "screwdown", "fan", "compressor",
                 "cooler", "servo", "valve actuator"],
    "transformer": ["roller", "rolls", "roll", "mill", "rolling mill", "press", "converter", "reactor", "furnace",
                    "machine", "enzyme", "inverter", "turbine", "lathe", "oven"],
}
LEXICON: Dict[str, str] = {}
for _role, _terms in ROLE_LEXICON.items():
    for _t in _terms:
        LEXICON[_t] = _role

# Unfamiliar wording -> a lexicon term. Lookup is on the lowercased, singularised phrase. A synonym hit gives the
# entity the role of the lexicon term but keeps the user's own words as its label.
SYNONYMS: Dict[str, str] = {
    "boiler": "furnace", "kiln": "furnace", "heating element": "heater", "radiator": "cooler", "refrigerator": "cooler",
    "air conditioner": "cooler", "thermocouple": "thermometer", "thermistor": "thermometer", "radar": "detector",
    "lidar": "detector", "accelerometer": "sensor", "pipeline": "pipe", "hose": "pipe", "artery": "pipe",
    "vein": "pipe", "highway": "road", "street": "road", "motorway": "road", "power line": "wire",
    "river": "channel", "canal": "channel", "internet": "network", "vendor": "supplier",
    "shopper": "customer", "buyer": "customer", "subscriber": "customer", "patron": "customer", "cistern": "tank",
    "silo": "tank", "lake": "reservoir", "faucet": "valve",
    "microcontroller": "controller", "supervisor": "manager", "coordinator": "manager", "switchboard": "switch",
    "dynamo": "generator", "grinder": "mill", "crusher": "mill", "blower": "fan", "propeller": "turbine",
    "crossroad": "intersection", "roundabout": "intersection", "stockroom": "warehouse",
    "depot": "warehouse", "pantry": "warehouse", "sunlight": "sun", "gasoline": "fuel", "petrol": "fuel", "diesel": "fuel",
    "electricity": "energy", "liquid": "fluid", "goods": "product", "cargo": "product",
    "parcel": "product", "viscosity": "drag",
}

# cue stem -> (relation, reverse). reverse=True means object -> subject.
VERB_CUES: Dict[str, Tuple[str, bool]] = {
    "drive": ("transmits", False), "power": ("transmits", False), "transmit": ("transmits", False),
    "control": ("controls", False), "adjust": ("controls", False), "regulate": ("controls", False),
    "manage": ("controls", False), "set": ("controls", False), "command": ("controls", False),
    "measure": ("observed_by", True), "monitor": ("observed_by", True), "detect": ("observed_by", True),
    "sense": ("observed_by", True), "read": ("observed_by", True),
    "signal": ("signals", False), "report": ("signals", False), "inform": ("signals", False),
    "limit": ("constrains", False), "restrict": ("constrains", False), "constrain": ("constrains", False),
    "bound": ("constrains", False), "cap": ("constrains", False), "prevent": ("constrains", False),
    "reduce": ("inhibits", False), "lower": ("inhibits", False), "decrease": ("inhibits", False),
    "inhibit": ("inhibits", False), "suppress": ("inhibits", False), "block": ("inhibits", False), "slow": ("inhibits", False),
    "increase": ("activates", False), "raise": ("activates", False), "amplify": ("activates", False),
    "activate": ("activates", False), "trigger": ("activates", False), "boost": ("activates", False),
    "produce": ("produces", False), "generate": ("produces", False), "create": ("produces", False), "yield": ("produces", False),
    "consume": ("consumes", False), "use": ("consumes", False), "deplete": ("consumes", False),
    "feed": ("flows_to", False), "supply": ("flows_to", False), "deliver": ("flows_to", False), "carry": ("flows_to", False),
    "send": ("flows_to", False), "move": ("flows_to", False), "transport": ("flows_to", False), "flow": ("flows_to", False),
    "pass": ("flows_to", False), "push": ("flows_to", False), "route": ("flows_to", False),
    "store": ("stores_in", True), "hold": ("stores_in", True), "accumulate": ("stores_in", True),
    "dissipate": ("dissipates_to", False), "waste": ("dissipates_to", False),
    "compete": ("competes_with", False), "convert": ("converts", False), "transform": ("converts", False),
    "deform": ("converts", False), "squeeze": ("converts", False), "compress": ("converts", False),
    "support": ("supports", False), "couple": ("couples_to", False),
    "decide": ("controls", False), "assign": ("controls", False), "return": ("flows_to", False),
    "dispatch": ("flows_to", False), "take": ("flows_to", False), "go": ("flows_to", False),
}
DETERMINERS = {"the", "a", "an", "each", "every", "this", "that", "its", "their", "our", "my"}
NP_STOP = {"is", "are", "was", "were", "be", "been", "must", "should", "can", "may", "will", "would", "not", "no", "to",
           "of", "in", "on", "at", "by", "for", "with", "from", "and", "or", "but", "so", "as", "than", "then", "that",
           "which", "when", "while", "where", "if", "goal", "number", "thing", "way", "hour", "time", "day", "problem",
           "amount", "rest", "one", "other", "all", "some", "many", "most", "more", "less", "each", "every", "same",
           "company", "people", "case", "part", "kind", "type", "lot", "end", "start"}
QUANTITIES = ["width", "thickness", "length", "force", "speed", "temperature", "pressure", "flow", "rate", "reduction",
              "capacity", "load", "demand", "cost", "time", "voltage", "current", "mass", "diameter", "height",
              "variation", "tolerance", "number", "budget", "power", "radius", "stock", "price", "throughput", "latency", "area"]
UNIT_RE = (r"(?:mm|cm|km|m/s|m|um|kg|g|kN|N|MPa|GPa|kPa|Pa|%|percent|ms|s|min|hours?|h|days?|C|K|V|A|kW|MW|W|Hz|rpm|"
           r"units?|items?|vehicles?|requests?|EUR|USD|dollars?)")
NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(" + UNIT_RE + r")?(?![\w])")
GOAL_CUES = ("goal", "aim", "objective", "we want", "i want", "need to", "so that", "in order to", "achieve", "maximi", "minimi", "improve", "optimi")
HARD_CUES = ("must not", "cannot", "can not", "never", "shall not", "may not", "no more than", "at most", "at least",
             "not exceed", "not vary", "maximum", "minimum", "upper limit", "lower limit", "must stay", "must remain")
SOFT_CUES = ("should", "prefer", "ideally", "try to", "would like")
LE_WORDS = {"the", "a", "an", "is", "are", "of", "and", "to", "in", "with", "by", "for", "must", "should", "that"}
LIMITATIONS = ("Lexicon, synonym table and verb cue based. For words outside the lexicon it also guesses a role from the "
               "head noun, hyphen and compound parts, word overlap with the seed knowledge base, and the linking verb; those "
               "roles are low-confidence inferences, can be wrong, and are marked in node attrs. Entities without a determiner "
               "('Depositors supply funds'), passive voice, pronouns, implicit entities and non-English text are not handled "
               "reliably. Output needs human review.")


@dataclass
class PerceptionResult:
    problem: Problem
    facts: List[dict] = field(default_factory=list)
    inferences: List[dict] = field(default_factory=list)
    assumptions: List[dict] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    clarification_questions: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    limitations: str = LIMITATIONS
    available: bool = True

    def to_dict(self) -> dict:
        return {"problem": self.problem.to_dict(), "facts": self.facts, "inferences": self.inferences,
                "assumptions": self.assumptions, "unknowns": self.unknowns,
                "clarification_questions": self.clarification_questions, "flags": self.flags,
                "limitations": self.limitations, "available": self.available}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _norm(tok: str) -> str:
    t = tok.lower()
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("es") and t[:-2] in LEXICON:
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3 and t[:-1] in LEXICON:
        return t[:-1]
    return t


def _singulars(tok: str) -> List[str]:
    """Lowercased token plus its plausible singular forms (simple suffix rules, no dictionary)."""
    t = tok.lower()
    if t.endswith("'s"):
        t = t[:-2]
    out = [t]
    if t.endswith("ies") and len(t) > 4:
        out.append(t[:-3] + "y")
    if t.endswith(("ches", "shes", "xes", "sses", "zes")) and len(t) > 4:
        out.append(t[:-2])
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        out.append(t[:-1])
    return out


def _lookup_role(tokens: List[Tuple[str, int, int]]) -> Optional[Tuple[str, str]]:
    """Normalised lexicon or synonym lookup for a token window. Returns (label, role) or None."""
    forms: List[List[str]] = [[""]]
    for t in tokens:
        forms.append([(p + " " + f).strip() for p in forms[-1] for f in _singulars(t[0])])
    for phrase in forms[-1]:
        if phrase in LEXICON:
            return phrase, LEXICON[phrase]
    for phrase in forms[-1]:
        if phrase in SYNONYMS:
            return phrase, LEXICON[SYNONYMS[phrase]]
    return None


def _verb_stem(tok: str) -> Optional[str]:
    t = tok.lower()
    cands = [t]
    for suf in ("ing", "ed", "es", "s", "d"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            cands.append(t[: -len(suf)])
            if suf in ("ing", "ed", "es", "d"):
                cands.append(t[: -len(suf)] + "e")
    for c in cands:
        if c in VERB_CUES:
            return c
    if t.endswith("ting") and t[:-4] in ("se", "se"):
        return None
    return None


# ------------------------------------------------------------------ role resolution beyond the lexicon
# Each mechanism below is an INFERENCE with its own lower confidence and a recorded source; none is a stated fact.
ROLE_SOURCE_CONFIDENCE = {"lexicon": 0.7, "head_noun": 0.5, "morphology": 0.45, "knowledge_index": 0.35,
                          "context": 0.25, "ai_provider": 0.4, "learned": 0.6}
ROLE_SOURCE_TEXT = {
    "head_noun": "the last word of the phrase matches a lexicon or synonym term",
    "morphology": "a hyphenated part or compound tail matches a lexicon or synonym term",
    "knowledge_index": "word overlap with role-labelled entities in the seed knowledge base",
    "context": "the verb that links it to other entities",
    "learned": "a term confirmed by repeated user role corrections in the active learned config",
    "ai_provider": "classification by the configured AI provider (a hypothesis)",
}
INDEX_MIN_SCORE = 1.2
INDEX_MIN_MARGIN = 0.4
_INDEX_STOP = NP_STOP | DETERMINERS | LE_WORDS
_role_index_cache: Optional[Dict[str, Dict[str, int]]] = None

# verb cue stem -> (role of the subject, role of the object). Only unknown (None) entities receive these roles.
CONTEXT_ROLES: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    "control": ("controller", None), "adjust": ("controller", None), "regulate": ("controller", None),
    "manage": ("controller", None), "command": ("controller", None), "decide": ("controller", None),
    "assign": ("controller", None),
    "measure": ("sensor", None), "monitor": ("sensor", None), "detect": ("sensor", None), "sense": ("sensor", None),
    "read": ("sensor", None),
    "drive": ("actuator", None), "power": ("actuator", None),
    "produce": ("producer", None), "generate": ("producer", None), "create": ("producer", None),
    "consume": ("consumer", None), "deplete": ("consumer", None),
    "store": ("buffer", None), "hold": ("buffer", None), "accumulate": ("buffer", None),
    "convert": ("transformer", None), "transform": ("transformer", None),
    "dissipate": ("dissipater", None),
    "limit": ("regulator", None), "restrict": ("regulator", None), "constrain": ("regulator", None),
    "carry": ("conduit", None), "deliver": ("conduit", None), "transport": ("conduit", None), "pass": ("conduit", None),
    "feed": ("source", None), "supply": ("source", None),
}


def _stem_token(tok: str) -> str:
    t = tok.lower()
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("s") and not t.endswith(("ss", "us", "is")) and len(t) > 3:
        return t[:-1]
    return t


def _lex_role(word: str) -> Optional[str]:
    for f in _singulars(word):
        if f in LEXICON:
            return LEXICON[f]
        if f in SYNONYMS:
            return LEXICON[SYNONYMS[f]]
    return None


def _morphology_role(word: str) -> Optional[str]:
    """Hyphenated parts (last first), then the longest compound tail (4+ letters) found in the lexicon."""
    parts = [p for p in word.lower().split("-") if p]
    if len(parts) > 1:
        for part in reversed(parts):
            r = _lex_role(part)
            if r:
                return r
    w = parts[-1] if parts else word.lower()
    for k in range(1, len(w) - 3):
        tail = w[k:]
        r = _lex_role(tail) if len(tail) >= 4 else None
        if r:
            return r
    return None


def _role_index() -> Dict[str, Dict[str, int]]:
    """token -> role -> count, learned from role-labelled node labels in data/seed_knowledge. Empty if unreadable."""
    global _role_index_cache
    if _role_index_cache is not None:
        return _role_index_cache
    idx: Dict[str, Dict[str, int]] = {}
    try:
        import glob
        import json
        import os
        from knowledge_base.loader import data_dir
        for path in sorted(glob.glob(os.path.join(data_dir(), "seed_knowledge", "*.json"))):
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            for sysd in doc.get("systems", []):
                for n in sysd.get("graph", {}).get("nodes", []):
                    role = n.get("role")
                    if role is None or n.get("kind", "entity") != "entity":
                        continue
                    for tok in re.findall(r"[a-z]{3,}", str(n.get("label", "")).lower()):
                        if tok in _INDEX_STOP:
                            continue
                        c = idx.setdefault(_stem_token(tok), {})
                        c[role] = c.get(role, 0) + 1
    except (OSError, ValueError, ImportError):
        idx = {}
    _role_index_cache = idx
    return idx


def _index_role(words: List[str]) -> Optional[str]:
    idx = _role_index()
    scores: Dict[str, float] = {}
    for k, w in enumerate(words):
        counts = idx.get(_stem_token(w))
        if not counts:
            continue
        total = sum(counts.values())
        weight = 2.0 if k == len(words) - 1 else 1.0
        for role, c in counts.items():
            scores[role] = scores.get(role, 0.0) + weight * (c / total) * (total / (total + 1.0))
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    if top[1] >= INDEX_MIN_SCORE and top[1] - runner >= INDEX_MIN_MARGIN:
        return top[0]
    return None


# Learned lexicon overlay for the current perceive_text call (term -> role) and the config version that supplied it.
# A ContextVar is set and reset inside perceive_text, so nothing leaks between calls or threads.
_OVERLAY: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar("perception_overlay", default=None)
_OVERLAY_VERSION: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("perception_overlay_version", default=None)


def _same_term(a: List[str], b: List[str]) -> bool:
    """Word by word match where plural and singular forms of either side may meet ('flumoxes' = 'flumox')."""
    return len(a) == len(b) and all(set(_singulars(x)) & set(_singulars(y)) for x, y in zip(a, b))


def _overlay_role(words: List[str]) -> Optional[str]:
    overlay = _OVERLAY.get()
    if not overlay:
        return None
    terms = sorted(overlay.items())
    for term, role in terms:
        if _same_term(term.lower().split(), words):
            return role
    for term, role in terms:
        if _same_term(term.lower().split(), words[-1:]):
            return role
    return None


def resolve_unknown_role(words: List[str]) -> Optional[Tuple[str, str]]:
    """Role for a phrase the lexicon missed: learned overlay, head noun, then morphology, then the seed knowledge index.
    Returns (role, source) or None. None means nothing matched; the caller must leave the role unknown.
    The learned overlay never overrides a head word that the lexicon or synonyms already resolve."""
    words = [w.lower() for w in words if w]
    if not words:
        return None
    head = words[-1]
    if _lex_role(head) is None:
        r = _overlay_role(words)
        if r:
            return r, "learned"
    r = _lex_role(head)
    if r:
        return r, ("head_noun" if len(words) > 1 else "morphology")
    r = _morphology_role(head)
    if r:
        return r, "morphology"
    r = _index_role([w for part in words for w in part.split("-") if w])
    if r:
        return r, "knowledge_index"
    return None


def _apply_role(e: dict, role: str, source: str) -> None:
    e["role"], e["role_source"], e["conf"] = role, source, ROLE_SOURCE_CONFIDENCE[source]


def split_sentences(text: str) -> List[Tuple[str, int]]:
    """Split on . ; ! ? and newlines, but not on decimal points."""
    out = []
    for m in re.finditer(r"(?:[^.;!?\n]|(?<=\d)\.(?=\d))+", text):
        seg = m.group(0)
        stripped = seg.strip()
        if stripped:
            out.append((stripped, m.start() + (len(seg) - len(seg.lstrip()))))
    return out


def _entities_in(tokens: List[Tuple[str, int, int]]) -> List[dict]:
    """Longest-match lexicon lookup. tokens: (text, start, end)."""
    found, i = [], 0
    while i < len(tokens):
        hit = None
        for n in (3, 2, 1):
            if i + n > len(tokens):
                continue
            phrase = " ".join(_norm(t[0]) for t in tokens[i:i + n])
            if phrase in LEXICON:
                hit = (phrase, n, LEXICON[phrase])
                break
            alt = _lookup_role(tokens[i:i + n])
            if alt is not None:
                hit = (alt[0], n, alt[1])
                break
        if hit:
            phrase, n, role = hit
            found.append({"key": phrase, "role": role, "start_tok": i, "end_tok": i + n - 1,
                          "start": tokens[i][1], "end": tokens[i + n - 1][2]})
            i += n
        else:
            i += 1
    _extend_compounds(tokens, found)
    return _add_unknown_nouns(tokens, found)


def _plain_word(tokens, j, taken) -> bool:
    if j >= len(tokens) or j in taken:
        return False
    w = tokens[j][0].lower()
    return not (w in NP_STOP or w in DETERMINERS or w in QUANTITIES or _verb_stem(w) is not None or w in LEXICON
                or w.endswith(("ing", "ly", "ed", "s")) or len(w) < 3)


def _extend_compounds(tokens, found) -> None:
    """'the load shedder': a lexicon word after a determiner followed by a plain word is a compound whose HEAD is the
    last word. It is merged only when the head resolves to a role; otherwise the old single-word entity is kept."""
    taken = set()
    for e in found:
        taken.update(range(e["start_tok"], e["end_tok"] + 1))
    for e in list(found):
        # modifiers before a lexicon head ('the coolant circulation pump'): the head decides the role. The entity keeps
        # the head's key so later mentions of 'the pump' are the same node; the span covers the whole phrase.
        k = e["start_tok"]
        mods = 0
        while mods < 2 and k - 1 - mods >= 0 and _plain_word(tokens, k - 1 - mods, taken):
            mods += 1
        while mods and not (k - mods == 0 or tokens[k - mods - 1][0].lower() in DETERMINERS):
            mods -= 1
        is_verb = _verb_stem(tokens[e["end_tok"]][0]) is not None or tokens[e["end_tok"]][0].lower().endswith("s")
        if mods and e["role"] is not None and not is_verb:
            e["start_tok"], e["start"] = k - mods, tokens[k - mods][1]
            e["absorbed"] = True
            taken.update(range(k - mods, k))
    for e in list(found):
        if e["start_tok"] != e["end_tok"] or e["role"] is None or e.get("absorbed"):
            continue
        i, j = e["start_tok"], e["end_tok"] + 1
        if not (i == 0 or tokens[i - 1][0].lower() in DETERMINERS) or not _plain_word(tokens, j, taken):
            continue
        words = [tokens[i][0], tokens[j][0]]
        res = resolve_unknown_role(words)
        if res is None:
            continue
        e.update(key=" ".join(_norm(w) for w in words), end_tok=j, end=tokens[j][2])
        _apply_role(e, res[0], res[1])
        taken.add(j)


def _add_unknown_nouns(tokens, found):
    """Fallback for vocabulary outside the lexicon: a determiner followed by up to two plain words becomes an
    entity with UNKNOWN role (role None, low confidence). The user is asked to confirm its role."""
    taken = set()
    for e in found:
        taken.update(range(e["start_tok"], e["end_tok"] + 1))
    i = 0
    while i < len(tokens):
        if tokens[i][0].lower() in DETERMINERS:
            j, words = i + 1, []
            while j < len(tokens) and len(words) < 3:
                w = tokens[j][0].lower()
                if j in taken or w in NP_STOP or w in DETERMINERS or w in QUANTITIES or _verb_stem(w) is not None \
                        or w.endswith("ing") or w.endswith("ly"):
                    break
                words.append(j)
                j += 1
            # a trailing plural-looking word after a modifier is usually a verb ('the dough rises')
            if len(words) >= 2 and tokens[words[-1]][0].lower().endswith("s") \
                    and not tokens[words[-1]][0].lower().endswith(("ss", "us", "is")):
                words.pop()
                j = words[-1] + 1
            if words:
                label = " ".join(_norm(tokens[k][0]) for k in words)
                ent = {"key": label, "role": None, "start_tok": words[0], "end_tok": words[-1],
                       "start": tokens[words[0]][1], "end": tokens[words[-1]][2]}
                res = resolve_unknown_role([tokens[k][0] for k in words])
                if res is not None:
                    _apply_role(ent, res[0], res[1])
                found.append(ent)
                taken.update(words)
            i = j
        else:
            i += 1
    found.sort(key=lambda e: e["start_tok"])
    return found


def _context_roles(toks, ents, sent) -> None:
    """Give still-unknown entities a role from the verb that links them (subject of 'controls' -> controller).
    Weakest evidence, recorded with source 'context'; only entities whose role is None are touched."""
    for i, t in enumerate(toks):
        stem = _verb_stem(t[0])
        if stem not in CONTEXT_ROLES:
            continue
        subj = [e for e in ents if e["end_tok"] < i]
        obj = [e for e in ents if e["start_tok"] > i]
        if not subj or not obj:
            continue
        for e, role in ((subj[-1], CONTEXT_ROLES[stem][0]), (obj[0], CONTEXT_ROLES[stem][1])):
            if role is not None and e["role"] is None:
                _apply_role(e, role, "context")
                e["role_note"] = f"verb '{t[0]}'"


def _is_english(text: str) -> bool:
    toks = re.findall(r"[a-zA-Z]+", text.lower())
    if len(toks) < 4:
        return True
    ratio = sum(1 for t in toks if t in LE_WORDS) / len(toks)
    non_ascii = sum(1 for ch in text if ord(ch) > 127) / max(len(text), 1)
    return ratio >= 0.08 and non_ascii < 0.2


def _num(s: str) -> float:
    return float(s)


def _quantities(sentence: str, base: int) -> List[dict]:
    out = []
    low = sentence.lower()
    for m in NUM_RE.finditer(sentence):
        unit = m.group(2)
        if unit is None:
            # bare numbers are only used when a quantity word is adjacent
            pass
        before = re.findall(r"[a-z]+", low[:m.start()])[-6:]
        after = re.findall(r"[a-z]+", low[m.end():])[:2]
        name = after[0] if after and after[0] in QUANTITIES else None
        if name is None:
            name = next((w for w in reversed(before) if w in QUANTITIES), None)
        if name is None:
            name = next((w for w in after if w in QUANTITIES), None)
        if name is None and unit is None and after and after[0] not in NP_STOP and after[0] not in LE_WORDS:
            unit, name = after[0], "count"  # bare number followed by a counted noun, for example '20 bikes'
        if name is None and unit is None:
            continue
        out.append({"name": name, "value": _num(m.group(1)), "unit": unit, "span": [base + m.start(), base + m.end()],
                    "sentence": sentence})
    return out


def perceive_text(text: str, title: str = "", overlay: Optional[Dict[str, str]] = None,
                  overlay_version: Optional[str] = None) -> PerceptionResult:
    """Perceive free text. overlay (term -> role, from a learned config) is optional; None keeps the built-in behaviour."""
    tok = _OVERLAY.set(dict(overlay) if overlay else None)
    tok_v = _OVERLAY_VERSION.set(overlay_version)
    try:
        return _perceive_text(text, title)
    finally:
        _OVERLAY.reset(tok)
        _OVERLAY_VERSION.reset(tok_v)


def _perceive_text(text: str, title: str = "") -> PerceptionResult:
    pid = _slug(title) or "problem"
    problem = Problem(id=pid, title=title or "Untitled problem", statement=text)
    res = PerceptionResult(problem)
    if not text or not text.strip():
        res.unknowns.append("input is empty")
        res.clarification_questions.append("Please describe the problem, its parts and what you want to achieve.")
        res.flags.append("empty_input")
        return res
    if not _is_english(text):
        res.flags.append("low_confidence_non_english")
    g = problem.graph
    nodes: Dict[str, Node] = {}
    constraints: List[Constraint] = []
    goal: List[str] = []
    var_seen: Dict[str, Variable] = {}
    cue_unused: List[str] = []
    for sent, base in split_sentences(text):
        toks = [(m.group(0), base + m.start(), base + m.end()) for m in re.finditer(r"[A-Za-z][A-Za-z\-']*", sent)]
        # shift token starts to absolute offsets computed above; sentence-local search used for entities
        ents = _entities_in(toks)
        # a lexicon noun that is also a verb cue between two entities is a verb ("feeds", "supplies")
        keep = []
        for k, e in enumerate(ents):
            single = e["start_tok"] == e["end_tok"]
            if single and e["role"] is not None and _verb_stem(toks[e["start_tok"]][0]) is not None and any(x["end_tok"] < e["start_tok"] for x in ents) \
                    and any(x["start_tok"] > e["end_tok"] for x in ents) and toks[e["start_tok"]][0].lower().endswith(("s", "ed")):
                continue
            keep.append(e)
        ents_all, ents = ents, keep
        _context_roles(toks, ents, sent)
        for e in ents:
            nid = _slug(e["key"])
            if nid not in nodes:
                known = e["role"] is not None
                src = e.get("role_source", "lexicon") if known else None
                attrs = {"role_source": src} if src and src != "lexicon" else {}
                nodes[nid] = Node(nid, e["key"], "entity", e["role"], attrs, Provenance.USER, span=text[e["start"]:e["end"]],
                                  confidence=ROLE_SOURCE_CONFIDENCE.get(src, 0.7) if known else 0.3)
                res.facts.append({"statement": f"'{e['key']}' is mentioned", "span": [e["start"], e["end"]], "provenance": "user"})
                if known and src == "lexicon":
                    res.inferences.append({"statement": f"Role of '{e['key']}' inferred as {e['role']} from keyword lexicon",
                                           "provenance": "computation", "confidence": 0.7})
                elif known:
                    note = f" ({e['role_note']})" if e.get("role_note") else ""
                    if src == "learned":
                        note += f" (learned config version {_OVERLAY_VERSION.get() or 'unversioned'})"
                    res.inferences.append({"statement": f"Role of '{e['key']}' inferred as {e['role']}: {ROLE_SOURCE_TEXT[src]}{note}. "
                                                        "This is a guess, not a stated fact.",
                                           "provenance": "computation", "confidence": ROLE_SOURCE_CONFIDENCE[src],
                                           "source": src, "span": [e["start"], e["end"]]})
                    res.clarification_questions.append(f"Is '{e['key']}' really a {e['role']} (role guessed by {src.replace('_', ' ')})?")
                else:
                    res.unknowns.append(f"role of '{e['key']}' is unknown (word not in lexicon)")
                    res.clarification_questions.append(f"What function does '{e['key']}' serve (supply, storage, control, sensing, load, ...)?")
        # relation cues
        cues = []
        for i, t in enumerate(toks):
            stem = _verb_stem(t[0])
            if stem is not None:
                cues.append((i, stem))
        used_cue = False
        for ci, stem in cues:
            subj = [e for e in ents if e["end_tok"] < ci]
            obj = [e for e in ents if e["start_tok"] > ci]
            if not subj or not obj:
                continue
            s_e, o_e = subj[-1], obj[0]
            if s_e["key"] == o_e["key"]:
                continue
            rel, rev = VERB_CUES[stem]
            if stem == "reduce" and s_e["role"] == "transformer":
                rel = "converts"
            a, b = _slug(s_e["key"]), _slug(o_e["key"])
            if rev:
                a, b = b, a
            span_txt = sent
            dup = any(e.source == a and e.target == b and e.relation == rel for e in g.edges)
            if not dup:
                g.add_edge(a, b, rel, 1.0, Provenance.USER, span=span_txt, confidence=0.6)
            used_cue = True
        if not used_cue and len(ents) >= 2:
            first, second = ents[0], ents[1]
            if first["key"] != second["key"]:
                a, b = _slug(first["key"]), _slug(second["key"])
                if not any({e.source, e.target} == {a, b} for e in g.edges):
                    g.add_edge(a, b, "couples_to", 0.5, Provenance.COMPUTATION, span=sent, confidence=0.3,
                               flags=["assumed_relation"])
                    res.assumptions.append({"statement": f"Assumed '{first['key']}' couples to '{second['key']}' (no relation verb recognised)",
                                            "span": sent, "provenance": "computation", "confidence": 0.3})
        low = sent.lower()
        is_constraint = False
        # constraints
        hard = any(c in low for c in HARD_CUES) or ("must" in low and bool(_quantities(sent, base)))
        soft = any(c in low for c in SOFT_CUES)
        if hard or soft:
            qs = _quantities(sent, base)
            expr = None
            if qs:
                q = qs[0]
                op = ">=" if any(w in low for w in ("at least", "minimum", "lower limit")) else "<="
                expr = {"var": q["name"] or "unknown_quantity", "op": op, "value": q["value"], "unit": q["unit"]}
                if q["name"] is None:
                    expr = None
            is_constraint = True
            kind = "hard" if hard else "soft"
            constraints.append(Constraint(f"c{len(constraints) + 1}", sent, kind, expr, Provenance.USER))
            if expr is None:
                res.unknowns.append(f"constraint '{sent}' has no numeric limit or the quantity could not be identified")
        # quantities
        for q in ([] if is_constraint else _quantities(sent, base)):
            nm = q["name"] or f"value_{len(var_seen) + 1}"
            if nm not in var_seen:
                v = Variable(name=nm, unit=q["unit"], role="parameter", value=q["value"])
                var_seen[nm] = v
                res.facts.append({"statement": f"{nm} = {q['value']} {q['unit'] or ''}".strip(), "span": q["span"], "provenance": "user"})
                if q["name"] is None:
                    res.unknowns.append(f"number {q['value']} {q['unit'] or ''} has no recognised quantity name".replace("  ", " "))
        # goal
        if any(c in low for c in GOAL_CUES):
            goal.append(sent)
    problem.graph = g
    for nid, n in nodes.items():
        g.nodes.append(n)
    # node order stable by first appearance (dict preserves insertion)
    problem.constraints = constraints
    problem.variables = list(var_seen.values())
    problem.goal = " ".join(goal)
    # unknowns and questions
    if not goal:
        res.unknowns.append("no goal or objective statement found")
        res.clarification_questions.append("What outcome do you want to achieve, and how will you measure it?")
    if not nodes:
        res.unknowns.append("no known entities recognised in the text")
        res.clarification_questions.append("Which parts or actors are involved? Name the main components.")
    connected = {e.source for e in g.edges} | {e.target for e in g.edges}
    for nid, n in nodes.items():
        if nid not in connected and len(nodes) > 1:
            res.unknowns.append(f"'{n.label}' has no recognised relationship to other elements")
            res.clarification_questions.append(f"How does '{n.label}' interact with the other components?")
    if not var_seen:
        res.unknowns.append("no numeric quantities found")
        res.clarification_questions.append("What are the key quantities (sizes, rates, capacities, limits) and their units?")
    for c in constraints:
        if c.expression is None:
            res.clarification_questions.append(f"What numeric limit applies to: '{c.description}'?")
    if not constraints:
        res.unknowns.append("no explicit constraints found")
        res.clarification_questions.append("Which limits must never be violated (hard) and which are preferences (soft)?")
    # de-duplicate keep order
    res.unknowns = list(dict.fromkeys(res.unknowns))
    res.clarification_questions = list(dict.fromkeys(res.clarification_questions))
    return res


# ------------------------------------------------------------------ optional AI classification (off by default)
def classify_unknown_roles(result: PerceptionResult, provider) -> PerceptionResult:
    """Ask `provider` to classify ONLY the entities still without a role into the fixed ROLES set.

    Never called by perceive_text. Any provider failure propagates (no fallback, no invented roles). The reply is
    validated first: it must match the schema, name only labels that were asked about, and use roles inside
    ROLES, otherwise ProviderSchemaError is raised and the result is left unchanged. Accepted roles are recorded
    as inferences with provenance 'ai_hypothesis' and low confidence; they are never facts."""
    from ai_providers.base import CompletionRequest, ProviderSchemaError, validate_schema
    nodes = [n for n in result.problem.graph.nodes if n.kind == "entity" and n.role is None]
    if not nodes:
        return result
    statement = result.problem.statement or ""
    sentences = [x for x, _ in split_sentences(statement)]
    items = []
    for n in nodes:
        ctx = next((x for x in sentences if n.label.lower() in x.lower()), "")
        items.append({"label": n.label, "sentence": ctx})
    schema = {"type": "object", "required": ["roles"], "properties": {"roles": {"type": "array", "items": {
        "type": "object", "required": ["label", "role"],
        "properties": {"label": {"type": "string"}, "role": {"type": "string", "enum": list(ROLES)}}}}}}
    prompt = ("Classify each entity into exactly one functional role from this list: " + ", ".join(ROLES) +
              ". Answer only for the labels given. If unsure, omit the label.\nEntities (JSON): " + json.dumps(items))
    out = provider.complete(CompletionRequest(prompt=prompt, task="classify_roles", schema=schema, temperature=0.0))
    errs = validate_schema(out.parsed, schema)
    if errs:
        raise ProviderSchemaError("; ".join(errs[:5]))
    by_label = {n.label: n for n in nodes}
    seen = set()
    for item in out.parsed["roles"]:
        if item["label"] not in by_label:
            raise ProviderSchemaError(f"provider named an entity that was not asked about: {item['label']!r}")
        if item["label"] in seen:
            raise ProviderSchemaError(f"provider returned the label {item['label']!r} twice")
        seen.add(item["label"])
    for item in out.parsed["roles"]:
        n = by_label[item["label"]]
        n.role = item["role"]
        n.attrs["role_source"] = "ai_provider"
        n.confidence = ROLE_SOURCE_CONFIDENCE["ai_provider"]
        result.inferences.append({"statement": f"Role of '{n.label}' classified as {n.role} by {out.provider} ({out.model}): "
                                               "an AI hypothesis, not a stated fact.",
                                  "provenance": "ai_hypothesis", "confidence": n.confidence, "source": "ai_provider",
                                  "span": n.span})
        result.unknowns = [u for u in result.unknowns if u != f"role of '{n.label}' is unknown (word not in lexicon)"]
    return result


# ------------------------------------------------------------------ CSV
def _pearson(a: List[float], b: List[float]) -> Optional[float]:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def perceive_csv(text: str, title: str = "csv data") -> PerceptionResult:
    problem = Problem(id=_slug(title) or "csv", title=title, statement=f"Tabular data: {title}")
    res = PerceptionResult(problem)
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as e:  # pragma: no cover
        res.flags.append("csv_parse_error")
        res.unknowns.append(f"CSV could not be parsed: {e}")
        return res
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        res.unknowns.append("CSV has no data rows")
        res.clarification_questions.append("Provide a header row and at least a few data rows.")
        res.flags.append("empty_input")
        return res
    header, data = [h.strip() for h in rows[0]], rows[1:]
    cols: Dict[str, List[float]] = {}
    for j, h in enumerate(header):
        vals, bad = [], 0
        for r in data:
            cell = r[j].strip() if j < len(r) else ""
            try:
                vals.append(float(cell))
            except ValueError:
                bad += 1
        if vals and bad == 0:
            cols[h] = vals
        else:
            res.unknowns.append(f"column '{h}' is non-numeric or has {bad} missing or invalid cells; not analysed")
    res.facts.append({"statement": f"{len(data)} rows and {len(header)} columns: {', '.join(header)}", "provenance": "user"})
    for h, vals in cols.items():
        mean = sum(vals) / len(vals)
        problem.variables.append(Variable(h, None, min(vals), max(vals), "observed", mean))
        problem.graph.nodes.append(Node(_slug(h), h, "variable", "medium", {"mean": mean, "min": min(vals), "max": max(vals)},
                                        Provenance.USER, confidence=0.5))
        res.facts.append({"statement": f"{h}: min {min(vals):g}, max {max(vals):g}, mean {mean:g}", "provenance": "computation"})
    names = list(cols)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = _pearson(cols[a], cols[b])
            if r is not None and abs(r) >= 0.7:
                problem.graph.add_edge(_slug(a), _slug(b), "couples_to", abs(r), Provenance.COMPUTATION, confidence=abs(r),
                                       flags=["correlation_not_causation"])
                res.inferences.append({"statement": f"{a} and {b} correlate (r={r:.2f}); correlation is not causation",
                                       "provenance": "computation", "confidence": abs(r)})
    res.assumptions.append({"statement": "Columns treated as independent variables; time order and causality are unknown",
                            "provenance": "computation"})
    res.unknowns.append("no goal stated for the data")
    res.clarification_questions.append("Which column is the outcome you want to improve, and which columns can you change?")
    res.unknowns = list(dict.fromkeys(res.unknowns))
    return res


# ------------------------------------------------------------------ hooks
def perceive_pdf(path: str) -> PerceptionResult:
    """PDF hook. Requires the optional `pypdf` package, unavailable in the sandbox."""
    res = PerceptionResult(Problem(id="pdf", title=path, statement=""))
    if importlib.util.find_spec("pypdf") is None:
        res.available = False
        res.flags.append("pdf_unavailable")
        res.unknowns.append("PDF extraction needs the optional dependency pypdf, which is not installed")
        return res
    from pypdf import PdfReader  # pragma: no cover  (UNVERIFIED: not run in sandbox)
    text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)  # pragma: no cover
    return perceive_text(text, path)  # pragma: no cover


def perceive_image(path: str) -> PerceptionResult:
    """Image hook. OCR or vision models are not available; always reports unavailable."""
    res = PerceptionResult(Problem(id="image", title=path, statement=""))
    res.available = False
    res.flags.append("image_unavailable")
    res.unknowns.append("Image understanding needs an OCR or vision provider that is not configured")
    return res
