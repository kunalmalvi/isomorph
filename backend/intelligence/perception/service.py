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
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..schemas import Problem, Graph, Node, Edge, Constraint, Variable, Provenance

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
    "lidar": "detector", "accelerometer": "sensor", "pipeline": "pipe", "hose": "pipe", "tube": "pipe", "artery": "pipe",
    "vein": "pipe", "highway": "road", "street": "road", "motorway": "road", "lane": "road", "power line": "wire",
    "river": "channel", "canal": "channel", "grid": "network", "internet": "network", "vendor": "supplier",
    "shopper": "customer", "buyer": "customer", "subscriber": "customer", "patron": "customer", "cistern": "tank",
    "silo": "tank", "pool": "reservoir", "lake": "reservoir", "dam": "gate", "faucet": "valve", "tap": "valve",
    "microcontroller": "controller", "supervisor": "manager", "coordinator": "manager", "switchboard": "switch",
    "fuse": "breaker", "dynamo": "generator", "grinder": "mill", "crusher": "mill", "blower": "fan", "propeller": "turbine",
    "router": "hub", "crossroad": "intersection", "roundabout": "intersection", "pile": "stockpile", "stockroom": "warehouse",
    "depot": "warehouse", "pantry": "warehouse", "sunlight": "sun", "gasoline": "fuel", "petrol": "fuel", "diesel": "fuel",
    "coal": "fuel", "electricity": "energy", "liquid": "fluid", "gas": "fluid", "goods": "product", "cargo": "product",
    "parcel": "product", "resistance": "friction", "viscosity": "drag",
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
LIMITATIONS = ("Lexicon, synonym table and verb cue based. Passive voice, pronouns, implicit entities and non-English text are "
               "not handled reliably. Output needs human review.")


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
    return _add_unknown_nouns(tokens, found)


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
            while j < len(tokens) and len(words) < 2:
                w = tokens[j][0].lower()
                if j in taken or w in NP_STOP or w in DETERMINERS or w in QUANTITIES or _verb_stem(w) is not None \
                        or w.endswith("ing") or w.endswith("ly"):
                    break
                words.append(j)
                j += 1
            if words:
                label = " ".join(_norm(tokens[k][0]) for k in words)
                found.append({"key": label, "role": None, "start_tok": words[0], "end_tok": words[-1],
                              "start": tokens[words[0]][1], "end": tokens[words[-1]][2]})
                taken.update(words)
            i = j
        else:
            i += 1
    found.sort(key=lambda e: e["start_tok"])
    return found


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


def perceive_text(text: str, title: str = "") -> PerceptionResult:
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
        for e in ents:
            nid = _slug(e["key"])
            if nid not in nodes:
                known = e["role"] is not None
                nodes[nid] = Node(nid, e["key"], "entity", e["role"], {}, Provenance.USER, span=text[e["start"]:e["end"]],
                                  confidence=0.7 if known else 0.3)
                res.facts.append({"statement": f"'{e['key']}' is mentioned", "span": [e["start"], e["end"]], "provenance": "user"})
                if known:
                    res.inferences.append({"statement": f"Role of '{e['key']}' inferred as {e['role']} from keyword lexicon",
                                           "provenance": "computation", "confidence": 0.7})
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
