// Pure helpers shared by app.js and the node tests. No DOM access here.

export const STAGES = [
  ["perception", "Perception", "Reads the text and builds a first problem graph"],
  ["structural_extraction", "Structure", "Roles, dynamics and constraints of the problem"],
  ["structural_dna", "Structural DNA", "Numeric fingerprint of the structure"],
  ["cross_domain_search", "Cross-domain search", "Finds candidate systems in other domains"],
  ["structural_matching", "Matching", "Scores candidates on six structural dimensions"],
  ["mechanism_mapping", "Mechanism mapping", "Maps elements and relations to each analog"],
  ["transformation", "Transformations", "Design concepts transferred from the analogs"],
  ["hypothesis_generation", "Hypotheses", "Testable statements with falsifiers"],
  ["validation", "Validation", "Seeded simulations, capped when illustrative"],
];

export const TERMINAL = ["done", "failed", "cancelled"];

export const PROVENANCE = {
  source: "From a cited source in the knowledge base",
  computation: "Computed deterministically by the engine",
  user: "Stated or edited by you",
  ai_hypothesis: "Proposed by an AI provider, unverified",
};

export const DISCLAIMER =
  "Everything here is a hypothesis from structural analogy. Nothing is proven, and simulation results are not real-world evidence.";

export const EXAMPLES = [
  {
    id: "roller",
    title: "Roller demo: thin metal strip",
    text: "Strip made of copper or silver must be reduced in thickness. The strip is 50 mm width and 2 mm thickness. The motor drives the rolls. The rolls reduce the strip. The operator sets the screwdown once per coil. The screwdown sets the roll gap. The roll gap constrains the rolls. Friction dissipates energy at the bite. The thickness variation must not exceed 0.02 mm. The goal is to achieve the target reduction with minimal thickness variation.",
  },
  {
    id: "pump",
    title: "Pump and pipe energy loss",
    text: "A pump moves fluid. The pipe constrains the fluid flow. Friction dissipates energy at the wall. The goal is to minimise energy loss.",
  },
  {
    id: "queue",
    title: "Support queue overload",
    text: "Customers send requests to the support desk. Agents answer requests. The queue holds waiting requests. Demand peaks cause the queue to overflow. The goal is to reduce the number of abandoned requests.",
  },
];

export const UPLOAD_MAX_BYTES = 200 * 1024;
export const UPLOAD_TYPES = [".txt", ".md", ".json"];

/** Check a file chosen for upload. Returns an error string or null. */
export function checkUpload(name, size) {
  const lower = String(name || "").toLowerCase();
  if (!UPLOAD_TYPES.some((t) => lower.endsWith(t))) {
    return "Only .txt, .md and .json files can be read. PDF and images are not interpreted.";
  }
  if (size > UPLOAD_MAX_BYTES) return "That file is larger than 200 KB. Paste the relevant part instead.";
  return null;
}

/** Turn an uploaded file body into problem text. JSON may be {"statement"|"text": "..."} or a plain string. */
export function textFromUpload(name, body) {
  if (!String(name).toLowerCase().endsWith(".json")) return String(body).trim();
  let doc;
  try {
    doc = JSON.parse(body);
  } catch (e) {
    throw new Error("That file is not valid JSON.");
  }
  if (typeof doc === "string") return doc.trim();
  if (doc && typeof doc === "object") {
    for (const k of ["statement", "text", "description", "problem"]) {
      if (typeof doc[k] === "string" && doc[k].trim()) return doc[k].trim();
    }
  }
  throw new Error('JSON files need a "statement" or "text" string field.');
}

/** Message a person can act on, from an HTTP status and parsed error envelope. */
export function errorMessage(status, body) {
  const detail = body && body.error && body.error.message ? body.error.message : "";
  if (status === 0) return "Cannot reach the ISOMORPH server. Is it still running?";
  if (status === 401) return "This server needs an access token.";
  if (status === 404) return detail || "That item no longer exists.";
  if (status === 409) return detail || "That action conflicts with the current state.";
  if (status === 413) return "That input is too large for the server.";
  if (status === 422 || status === 400) return detail || "The input was not accepted.";
  if (status >= 500) return "The server hit an internal error. Check its terminal output.";
  return detail || `Request failed (HTTP ${status}).`;
}

/** Incremental SSE parser. Feed text, get complete events and the unparsed rest. */
export function parseSse(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop();
  for (const block of parts) {
    let event = "message";
    let id = null;
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("id:")) id = line.slice(3).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    try {
      events.push({ event, id, data: JSON.parse(data.join("\n")) });
    } catch (e) {
      /* ignore malformed event */
    }
  }
  return { events, rest };
}

export function stageIndex(name) {
  return STAGES.findIndex((s) => s[0] === name);
}

export function stageLabel(name) {
  const i = stageIndex(name);
  return i < 0 ? name : STAGES[i][1];
}

/** Share of stages that are done, 0..1. */
export function progressFraction(stages) {
  if (!stages || !stages.length) return 0;
  return stages.filter((s) => s.status === "done").length / stages.length;
}

export function statusTone(status) {
  return { done: "ok", running: "run", queued: "run", failed: "bad", cancelled: "mute", stale: "warn", pending: "mute" }[status] || "mute";
}

/** Bands for a 0..100 match score. Thresholds are display only and do not change scoring. */
export function scoreBand(score) {
  if (score >= 70) return "strong";
  if (score >= 45) return "moderate";
  if (score >= 25) return "weak";
  return "very weak";
}

export function fmtScore(n, digits = 1) {
  return typeof n === "number" && isFinite(n) ? n.toFixed(digits) : "n/a";
}

export function fmtPercent(n) {
  return typeof n === "number" && isFinite(n) ? Math.round(n * 100) + "%" : "n/a";
}

export function fmtTime(epochSeconds) {
  if (typeof epochSeconds !== "number") return "";
  const d = new Date(epochSeconds * 1000);
  return d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function relTime(epochSeconds, now = Date.now() / 1000) {
  if (typeof epochSeconds !== "number") return "";
  const s = Math.max(0, now - epochSeconds);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return Math.floor(s / 86400) + " d ago";
}

/** Dimension breakdown rows sorted by contribution, with width fractions of the weight. */
export function breakdownRows(components) {
  return Object.entries(components || {})
    .map(([name, c]) => ({
      name,
      score: c.score,
      weight: c.weight,
      contribution: c.contribution,
      explanation: c.explanation || "",
      fill: c.weight ? Math.min(1, Math.max(0, c.contribution / c.weight)) : 0,
    }))
    .sort((a, b) => b.contribution - a.contribution);
}

/** Two column layout for the mapping graph. Returns node and link geometry for an SVG of the given width. */
export function layoutMapping(mapping, width = 640, rowH = 34, pad = 20) {
  const pairs = (mapping && mapping.node_pairs) || [];
  const left = [];
  const right = [];
  for (const [s, t] of pairs) {
    if (!left.includes(s)) left.push(s);
    if (!right.includes(t)) right.push(t);
  }
  const unL = ((mapping && mapping.unmapped_source) || []).filter((x) => !left.includes(x));
  const unR = ((mapping && mapping.unmapped_target) || []).filter((x) => !right.includes(x));
  const L = left.concat(unL);
  const R = right.concat(unR);
  const rows = Math.max(L.length, R.length, 1);
  const lx = pad + 110;
  const rx = width - pad - 110;
  const nodes = [];
  const pos = { L: {}, R: {} };
  L.forEach((id, i) => {
    const y = pad + i * rowH + rowH / 2;
    pos.L[id] = y;
    nodes.push({ id, side: "L", x: lx, y, mapped: i < left.length });
  });
  R.forEach((id, i) => {
    const y = pad + i * rowH + rowH / 2;
    pos.R[id] = y;
    nodes.push({ id, side: "R", x: rx, y, mapped: i < right.length });
  });
  const links = pairs.map(([s, t, score]) => ({ from: s, to: t, score, x1: lx, y1: pos.L[s], x2: rx, y2: pos.R[t] }));
  return { width, height: pad * 2 + rows * rowH, nodes, links };
}

/** Case-insensitive filter over knowledge systems. */
export function filterSystems(items, text, domain) {
  const q = String(text || "").trim().toLowerCase();
  return items.filter(
    (s) => (!domain || s.domain === domain) && (!q || (s.name + " " + s.summary + " " + s.domain).toLowerCase().includes(q))
  );
}

/** Hypotheses with their validation outcome and your decision merged into one list. */
export function mergeHypotheses(validationOutput, generationOutput, annotations) {
  const base = (validationOutput && validationOutput.hypotheses) || (generationOutput && generationOutput.hypotheses) || [];
  const vals = {};
  for (const v of (validationOutput && validationOutput.validations) || []) vals[v.hypothesis_id] = v;
  const notes = annotations || {};
  return base.map((h) => ({
    hypothesis: h,
    validation: vals[h.id] || null,
    decision: (notes[h.id] && notes[h.id].decision) || "none",
    note: (notes[h.id] && notes[h.id].note) || "",
  }));
}

/** Parse the hash route. */
export function parseRoute(hash) {
  const parts = String(hash || "").replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (!parts.length) return { name: "home" };
  if (parts[0] === "new") return { name: "new" };
  if (parts[0] === "knowledge") return { name: "knowledge", id: parts[1] || null };
  if (parts[0] === "settings") return { name: "settings" };
  if (parts[0] === "learning") return { name: "learning" };
  if (parts[0] === "run" && parts[1]) return { name: "run", id: parts[1], tab: parts[2] || "progress" };
  return { name: "notfound" };
}

export const LEARNING_LIMITS =
  "Learning is limited to a lexicon overlay (words you corrected to a role) and conditional priors (small nudges that apply only under the recorded conditions). " +
  "A gate on frozen sets rejects any candidate that lowers a metric. The gate cannot detect harm those sets do not cover, " +
  "and a pass on metrics that did not change is not evidence that a change helps.";

/** Rows for the gate before/after table. Delta sign and a text verdict are included so color is never the only signal. */
export function gateRows(metrics) {
  return Object.entries(metrics || {}).map(([name, r]) => ({
    name,
    before: r.before,
    after: r.after,
    delta: r.delta,
    verdict: r.delta < -1e-9 ? "dropped" : r.delta > 1e-9 ? "improved" : "unchanged",
  }));
}

/** Plain words for a version status. */
export function versionStatusText(status) {
  return { active: "active", superseded: "superseded (kept in history)", rejected: "rejected by the gate", rolled_back: "rolled back" }[status] || String(status);
}

/** Entities of a perception output whose role is a guess or unknown, so the user can correct them. */
export function correctableEntities(perceptionOutput) {
  const nodes = (((perceptionOutput || {}).problem || {}).graph || {}).nodes || [];
  return nodes
    .filter((n) => !n.role || (n.attrs && n.attrs.role_source))
    .map((n) => ({ id: n.id, label: n.label, role: n.role || null, source: (n.attrs && n.attrs.role_source) || null }));
}

/** Lower-case a label the way the server does, and say whether it can be learned (1 to 4 alphabetic words). */
export function learnableTerm(label) {
  const t = String(label || "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  return /^[a-z]+( [a-z]+){0,3}$/.test(t) ? t : null;
}
