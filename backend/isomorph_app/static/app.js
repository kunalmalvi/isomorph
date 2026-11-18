// ISOMORPH web UI. Vanilla ES modules, no build step, no network requests except to this server's /api/v1.
// All dynamic text is inserted with textContent or text nodes. innerHTML is never used.
import {
  STAGES, TERMINAL, PROVENANCE, DISCLAIMER, EXAMPLES, checkUpload, textFromUpload, errorMessage, parseSse, stageLabel,
  progressFraction, statusTone, scoreBand, fmtScore, fmtPercent, fmtTime, relTime, breakdownRows, layoutMapping,
  filterSystems, mergeHypotheses, parseRoute,
} from "./lib.js";

const API = "/api/v1";
const SVG_NS = "http://www.w3.org/2000/svg";
const root = document.getElementById("app");
let cleanup = [];

// ---------------------------------------------------------------- DOM helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, kids);
  return el;
}
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}
function mount(...nodes) {
  clear(root);
  append(root, nodes);
}
function toast(message, tone = "") {
  const t = h("div", { class: "toast " + tone, text: message });
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), tone === "bad" ? 7000 : 3500);
}
const pill = (text, tone = "mute") => h("span", { class: "pill " + tone, text });
const provLabel = (p) => h("span", { class: "pill prov", title: PROVENANCE[p] || "", text: p || "unlabelled" });
const disclaimer = () => h("p", { class: "disclaimer", text: DISCLAIMER });
const loading = () => h("div", {}, h("div", { class: "skeleton" }), h("div", { class: "skeleton" }), h("div", { class: "skeleton" }));
function notice(text, tone = "") {
  return h("div", { class: "notice " + tone, role: tone === "bad" ? "alert" : null, text });
}

// ---------------------------------------------------------------- API
class ApiError extends Error {
  constructor(status, body) {
    super(errorMessage(status, body));
    this.status = status;
  }
}
const tokenStore = {
  get: () => { try { return sessionStorage.getItem("isomorph_token") || ""; } catch (e) { return ""; } },
  set: (v) => { try { sessionStorage.setItem("isomorph_token", v); } catch (e) { /* storage blocked */ } },
};
function authHeaders(extra) {
  const t = tokenStore.get();
  return Object.assign({}, t ? { Authorization: "Bearer " + t } : {}, extra || {});
}
async function api(method, path, body, raw) {
  let res;
  try {
    res = await fetch(API + path, {
      method,
      headers: authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, null);
  }
  if (res.status === 204) return null;
  if (raw && res.ok) return res.text();
  let parsed = null;
  try { parsed = await res.json(); } catch (e) { /* not json */ }
  if (!res.ok) throw new ApiError(res.status, parsed);
  return parsed;
}

function tokenForm(retry) {
  const input = h("input", { type: "password", id: "tok", autocomplete: "off", style: "max-width:360px" });
  mount(
    h("h1", { text: "Access token required" }),
    h("p", { class: "sub", text: "This server was started with ISOMORPH_TOKEN. Enter it to continue. It is kept for this browser tab only." }),
    h("form", { onsubmit: (e) => { e.preventDefault(); tokenStore.set(input.value.trim()); retry(); } },
      h("label", { for: "tok", text: "Token" }), input, h("p", {}, h("button", { class: "primary", type: "submit", text: "Continue" })))
  );
  input.focus();
}

// ---------------------------------------------------------------- router
function setNav(name) {
  for (const a of document.querySelectorAll("#nav a")) {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}
async function route() {
  for (const f of cleanup) f();
  cleanup = [];
  const r = parseRoute(location.hash);
  setNav(r.name === "run" ? "home" : r.name);
  mount(loading());
  document.title = "ISOMORPH";
  try {
    if (r.name === "home") await viewHome();
    else if (r.name === "new") viewNew();
    else if (r.name === "run") await viewRun(r);
    else if (r.name === "knowledge") await viewKnowledge(r);
    else if (r.name === "settings") await viewSettings();
    else mount(h("h1", { text: "Page not found" }), h("p", {}, h("a", { href: "#/", text: "Back to investigations" })));
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return tokenForm(route);
    mount(h("h1", { text: "Something went wrong" }), notice(e.message || String(e), "bad"),
      h("p", {}, h("button", { onclick: route, text: "Try again" }), " ", h("a", { class: "btn", href: "#/", text: "Investigations" })));
  } finally {
    const main = document.getElementById("main");
    if (main && !location.hash.includes("/progress")) main.focus({ preventScroll: true });
  }
}
window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- home
function runTitle(run) {
  const inp = run.input || {};
  if (inp.title) return inp.title;
  const t = (inp.text || (inp.problem && inp.problem.statement) || "").trim();
  return t ? (t.length > 70 ? t.slice(0, 70) + "..." : t) : "Untitled investigation";
}

async function startRun(text, title) {
  const res = await api("POST", "/discoveries", { text, title });
  location.hash = "#/run/" + res.id + "/progress";
}

async function viewHome() {
  const data = await api("GET", "/discoveries?limit=50");
  document.title = "Investigations | ISOMORPH";
  const list = h("div", { class: "grid" });
  const body = h("div");
  const header = h("div", { class: "row spread" },
    h("div", {}, h("h1", { text: "Investigations" }), h("p", { class: "sub", text: "Each investigation turns a problem into ranked cross-domain analogies and testable hypotheses." })),
    h("a", { class: "btn primary", href: "#/new", text: "New discovery" }));
  mount(header, body, disclaimer());

  function draw(d) {
    clear(body);
    if (!d.items.length) {
      body.append(h("div", { class: "empty" },
        h("h2", { text: "Start with a worked example" }),
        h("p", { class: "muted", text: "Load the roller demo to see every stage on a real problem in a few seconds, or describe your own problem." }),
        h("div", { class: "row", style: "justify-content:center" },
          h("button", { class: "primary", id: "demo", text: "Load the roller demo", onclick: async (e) => {
            e.target.disabled = true;
            try { await startRun(EXAMPLES[0].text, EXAMPLES[0].title); } catch (err) { e.target.disabled = false; toast(err.message, "bad"); }
          } }),
          h("a", { class: "btn", href: "#/new", text: "Describe my problem" }))));
      return;
    }
    clear(list);
    for (const r of d.items) {
      list.append(h("a", { class: "card link", href: "#/run/" + encodeURIComponent(r.id) + "/progress" },
        h("div", { class: "row spread" }, pill(r.status, statusTone(r.status)), h("span", { class: "muted", title: fmtTime(r.created_at), text: relTime(r.created_at) })),
        h("h3", { text: r.title || "Untitled investigation" }),
        h("span", { class: "muted mono", text: r.id.slice(0, 8) })));
    }
    body.append(list, h("p", { class: "muted", text: d.total + " investigation" + (d.total === 1 ? "" : "s") }));
  }
  draw(data);
  const timer = setInterval(async () => {
    try {
      const d = await api("GET", "/discoveries?limit=50");
      if (d.items.some((i) => !TERMINAL.includes(i.status)) || d.total !== data.total) draw(d);
    } catch (e) { /* keep last view */ }
  }, 2500);
  cleanup.push(() => clearInterval(timer));
}

// ---------------------------------------------------------------- new discovery
function viewNew() {
  document.title = "New discovery | ISOMORPH";
  const title = h("input", { type: "text", id: "title", maxlength: "200", placeholder: "Optional name" });
  const text = h("textarea", { id: "text", maxlength: "50000", placeholder: "Describe the system, how its parts relate, and what you want to improve. Plain sentences work best: \"The pump moves fluid. Friction dissipates energy.\"" });
  const msg = h("div");
  const go = h("button", { class: "primary", type: "submit", text: "Run analysis" });
  const count = h("span", { class: "muted", text: "0 / 50000" });
  text.addEventListener("input", () => { count.textContent = text.value.length + " / 50000"; });
  const file = h("input", { type: "file", id: "file", accept: ".txt,.md,.json", "aria-label": "Upload a .txt, .md or .json file" });
  file.addEventListener("change", async () => {
    clear(msg);
    const f = file.files[0];
    if (!f) return;
    const bad = checkUpload(f.name, f.size);
    if (bad) return msg.append(notice(bad, "warn"));
    try {
      text.value = textFromUpload(f.name, await f.text());
      if (!title.value) title.value = f.name.replace(/\.[^.]+$/, "");
      text.dispatchEvent(new Event("input"));
    } catch (e) { msg.append(notice(e.message, "warn")); }
  });
  const examples = h("div", { class: "row" }, EXAMPLES.map((ex) => h("button", { type: "button", class: "small", text: ex.title, onclick: () => {
    text.value = ex.text; title.value = ex.title; text.dispatchEvent(new Event("input")); text.focus();
  } })));
  const form = h("form", { onsubmit: async (e) => {
    e.preventDefault();
    clear(msg);
    if (text.value.trim().length < 20) return msg.append(notice("Write at least a couple of sentences so there is structure to analyse.", "warn"));
    go.disabled = true; go.textContent = "Starting...";
    try { await startRun(text.value, title.value.trim()); } catch (err) { go.disabled = false; go.textContent = "Run analysis"; msg.append(notice(err.message, "bad")); }
  } },
    h("label", { for: "title", text: "Name" }), title,
    h("label", { for: "text", text: "Problem description" }), text,
    h("div", { class: "row spread" }, h("span", { class: "hint", text: "The default engine reads keywords and sentence patterns. It does not understand free-form prose deeply." }), count),
    h("h3", { text: "Try an example" }), examples,
    h("h3", { text: "Or upload a file" }), file,
    h("p", { class: "hint", text: ".txt, .md or .json (a \"statement\" or \"text\" field), up to 200 KB. PDF and images are not interpreted." }),
    msg, h("p", {}, go));
  mount(h("h1", { text: "New discovery" }), h("p", { class: "sub", text: "Describe a problem. ISOMORPH extracts its structure and searches other domains for similar systems." }), form, disclaimer());
  text.focus();
}

// ---------------------------------------------------------------- run view
const TABS = [["progress", "Progress"], ["matches", "Matches"], ["transformations", "Transformations"], ["hypotheses", "Hypotheses"], ["validation", "Validation"], ["report", "Report"]];

async function viewRun(r) {
  const id = r.id;
  let run = await api("GET", "/discoveries/" + encodeURIComponent(id) + "?outputs=1");
  const state = { run, selected: null, notes: null };
  const frame = h("div");
  const tabbody = h("div");
  let tab = r.tab;
  if (!TABS.some((t) => t[0] === tab)) tab = "progress";

  function stageOut(name) {
    const st = state.run.stages.find((s) => s.name === name);
    return st && st.status !== "pending" ? st.output : null;
  }
  async function reload() {
    state.run = await api("GET", "/discoveries/" + encodeURIComponent(id) + "?outputs=1");
    drawAll();
  }
  async function act(fn, okMsg) {
    try { await fn(); if (okMsg) toast(okMsg, "ok"); await reload(); watch(); } catch (e) { toast(e.message, "bad"); }
  }

  function drawAll() {
    const rn = state.run;
    document.title = runTitle(rn) + " | ISOMORPH";
    const active = !TERMINAL.includes(rn.status);
    clear(frame);
    frame.append(
      h("div", { class: "row spread" },
        h("div", {}, h("h1", { text: runTitle(rn) }), h("div", { class: "row" }, pill(rn.status, statusTone(rn.status)), h("span", { class: "muted mono", text: rn.id }))),
        h("div", { class: "row" },
          active ? h("button", { text: "Cancel", onclick: () => act(() => api("POST", "/discoveries/" + id + "/cancel"), "Cancel requested") }) : null,
          !active && rn.status !== "done" ? h("button", { text: "Resume", onclick: () => act(() => api("POST", "/discoveries/" + id + "/resume"), "Resumed") }) : null,
          h("button", { class: "danger", disabled: active, text: "Delete", onclick: async () => {
            if (!confirm("Delete this investigation and its notes? This cannot be undone.")) return;
            try { await api("DELETE", "/discoveries/" + id); location.hash = "#/"; } catch (e) { toast(e.message, "bad"); }
          } }))),
      rn.error ? notice("Run " + rn.status + ": " + rn.error, "bad") : null,
      h("nav", { class: "tabs", "aria-label": "Investigation sections" }, TABS.map(([k, label]) =>
        h("a", { href: "#/run/" + encodeURIComponent(id) + "/" + k, "aria-current": k === tab ? "page" : null, text: label }))),
      tabbody);
    drawTab();
  }

  async function drawTab() {
    clear(tabbody);
    const fn = { progress: tabProgress, matches: tabMatches, transformations: tabTransformations, hypotheses: tabHypotheses, validation: tabValidation, report: tabReport }[tab];
    try { await fn(tabbody, state, { stageOut, act, reload, id }); } catch (e) { clear(tabbody); tabbody.append(notice(e.message, "bad")); }
    tabbody.append(disclaimer());
  }

  mount(frame);
  drawAll();

  // live progress over SSE (fetch based so the bearer token can be sent), with polling as a fallback
  let stop = false;
  cleanup.push(() => { stop = true; });
  let watching = false;
  async function watch() {
    if (watching || TERMINAL.includes(state.run.status)) return;
    watching = true;
    let failures = 0;
    while (!stop && !TERMINAL.includes(state.run.status)) {
      try {
        const res = await fetch(API + "/discoveries/" + encodeURIComponent(id) + "/events", { headers: authHeaders() });
        if (!res.ok) throw new Error("stream " + res.status);
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        failures = 0;
        for (;;) {
          const { value, done } = await reader.read();
          if (done || stop) break;
          buf += dec.decode(value, { stream: true });
          const p = parseSse(buf);
          buf = p.rest;
          for (const ev of p.events) onProgress(ev);
        }
      } catch (e) {
        failures += 1;
        if (failures >= 3) { await pollOnce(); await sleep(1500); }
      }
      if (!stop && !TERMINAL.includes(state.run.status)) await sleep(500);
    }
    watching = false;
  }
  function onProgress(ev) {
    const p = ev.data;
    if (!p || !Array.isArray(p.stages)) return;
    for (const s of p.stages) {
      const cur = state.run.stages.find((x) => x.name === s.name);
      if (cur) { cur.status = s.status; cur.version = s.version; cur.source = s.source; }
    }
    state.run.status = p.status;
    state.run.error = p.error;
    if (TERMINAL.includes(p.status)) { reload(); return; }
    if (tab === "progress") drawAll();
  }
  async function pollOnce() {
    try { state.run = await api("GET", "/discoveries/" + encodeURIComponent(id) + "?outputs=1"); drawAll(); } catch (e) { /* retry next loop */ }
  }
  watch();
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function jsonBlock(obj) {
  return h("pre", { class: "md mono", tabindex: "0", text: JSON.stringify(obj, null, 2) });
}

async function tabProgress(body, state, ctx) {
  const rn = state.run;
  const frac = progressFraction(rn.stages);
  body.append(h("div", { class: "row spread" }, h("strong", { text: Math.round(frac * 100) + "% complete" }),
    h("span", { class: "muted", text: rn.stages.filter((s) => s.status === "done").length + " of " + rn.stages.length + " stages" })),
    h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": Math.round(frac * 100), "aria-label": "Run progress" }, h("i", { style: "width:" + frac * 100 + "%" })));
  const pipe = h("div", { class: "pipeline", style: "margin-top:16px" });
  for (const [name, label, blurb] of STAGES) {
    const st = rn.stages.find((s) => s.name === name) || { status: "pending" };
    const tone = statusTone(st.status);
    pipe.append(h("button", { class: "stage", "aria-current": state.selected === name ? "true" : "false", onclick: () => {
      state.selected = state.selected === name ? null : name; clear(body); tabProgress(body, state, ctx).then(() => body.append(disclaimer()));
    } },
      h("span", { class: "dot " + tone, "aria-hidden": "true" }),
      h("span", {}, h("b", { text: label }), h("small", { text: blurb })),
      h("span", { class: "row" }, st.status === "done" ? provLabel(st.source) : null, pill(st.status, tone))));
  }
  body.append(pipe);
  if (state.selected) body.append(inspector(state, ctx));
}

function inspector(state, ctx) {
  const name = state.selected;
  const st = state.run.stages.find((s) => s.name === name);
  const box = h("div", { class: "card", style: "margin-top:16px" });
  box.append(h("div", { class: "row spread" }, h("h3", { style: "margin:0", text: stageLabel(name) + " output" }),
    h("span", { class: "muted", text: "version " + (st.version || 0) + " | source " + (st.source || "none") })));
  if (st.error) box.append(notice(st.error, "bad"));
  if (st.status === "stale") box.append(notice("An earlier stage changed, so this output is out of date. Rerun it to refresh.", "warn"));
  if (!st.output) {
    box.append(h("p", { class: "muted", text: "No output yet." }));
  } else {
    const area = h("textarea", { class: "code", id: "stage-json", "aria-label": "Stage output JSON", spellcheck: "false" });
    area.value = JSON.stringify(st.output, null, 2);
    const msg = h("div");
    box.append(area, msg, h("div", { class: "row" },
      h("button", { text: "Save edit", onclick: async () => {
        clear(msg);
        let parsed;
        try { parsed = JSON.parse(area.value); } catch (e) { return msg.append(notice("That is not valid JSON: " + e.message, "warn")); }
        ctx.act(() => api("PUT", "/discoveries/" + ctx.id + "/stages/" + name, { output: parsed }), "Saved. Later stages are now marked stale.");
      } }),
      h("button", { text: "Rerun downstream", onclick: () => ctx.act(() => api("POST", "/discoveries/" + ctx.id + "/stages/" + name + "/rerun?mode=downstream"), "Rerunning later stages") }),
      h("button", { text: "Rerun from here", onclick: () => ctx.act(() => api("POST", "/discoveries/" + ctx.id + "/stages/" + name + "/rerun?mode=from"), "Rerunning from this stage") })),
      h("p", { class: "hint", text: "Edits are labelled as user input. Rerun downstream keeps your edit and refreshes later stages. Rerun from here recomputes this stage too and discards the edit." }));
  }
  return box;
}

// ---------------------------------------------------------------- matches
function mappingSvg(mapping) {
  const g = layoutMapping(mapping, 640);
  if (!g.nodes.length) return null;
  const el = svg("svg", { class: "graph", viewBox: `0 0 ${g.width} ${g.height}`, role: "img", "aria-label": "Mapping between problem elements (left) and analog elements (right)" });
  for (const l of g.links) {
    el.append(svg("line", { x1: l.x1 + 54, y1: l.y1, x2: l.x2 - 54, y2: l.y2, "stroke-width": 1 + 3 * (l.score || 0), "stroke-opacity": 0.4 + 0.6 * (l.score || 0) }));
  }
  for (const n of g.nodes) {
    el.append(svg("g", { class: "node" + (n.mapped ? "" : " un"), transform: `translate(${n.x - 54},${n.y - 12})` },
      svg("rect", { width: 108, height: 24, rx: 6 }),
      svg("text", { x: 54, y: 16, "text-anchor": "middle" }, n.id.length > 16 ? n.id.slice(0, 15) + "..." : n.id)));
  }
  return el;
}

function matchCard(m, rank) {
  const rows = breakdownRows(m.components);
  const mp = m.mapping || {};
  const body = h("div", { class: "body" },
    h("h3", { text: "Score breakdown" }),
    rows.map((r) => h("div", {}, h("div", { class: "dim" }, h("span", { text: r.name }), h("div", { class: "bar" }, h("i", { style: "width:" + r.fill * 100 + "%" })),
      h("span", { class: "mono", text: fmtScore(r.contribution) + " / " + r.weight })), h("div", { class: "dim" }, h("span"), h("span", { class: "dim-ex", text: r.explanation })))),
    h("h3", { text: "Mapping" }),
    h("p", { class: "muted", text: "Node coverage " + fmtPercent(mp.node_coverage) + ", edge F1 " + fmtScore(mp.edge_f1, 2) + ", mapping confidence " + fmtScore(mp.confidence, 2) + ". Left: your problem. Right: the analog. Dashed boxes are unmapped." }),
    mappingSvg(mp),
    (mp.lost_edges || []).length ? h("div", {}, h("h3", { text: "Relationships lost in the mapping" }), h("ul", { class: "plain" }, mp.lost_edges.map((e) => h("li", { text: e.relation + " (" + e.source_edge + "): " + e.reason })))) : null,
    (m.differences || []).length ? h("div", {}, h("h3", { text: "Differences" }), h("ul", { class: "plain" }, m.differences.slice(0, 12).map((d) => h("li", { text: d })))) : null,
    (m.limitations || []).length ? h("div", {}, h("h3", { text: "Limitations" }), h("ul", { class: "plain" }, m.limitations.map((d) => h("li", { text: d })))) : null,
    (m.flags || []).length ? h("p", {}, (m.flags).map((f) => pill(f, "warn")), " ") : null);
  return h("details", { class: "card match" },
    h("summary", {}, h("span", { class: "rank", text: rank }),
      h("span", {}, h("b", { text: m.system_name }), h("br"), h("span", { class: "muted", text: m.domain + " | domain distance " + fmtScore(m.domain_distance, 2) })),
      h("span", { class: "score" }, fmtScore(m.score), h("small", { text: "of 100, " + scoreBand(m.score) }))),
    body);
}

async function tabMatches(body, state, ctx) {
  const out = ctx.stageOut("structural_matching");
  if (!out) return body.append(notice("Matches appear once the matching stage finishes.", ""));
  const ms = out.matches || [];
  if (!ms.length) return body.append(notice("No analog passed the structural filters. Add more detail about roles and relationships and rerun.", "warn"));
  body.append(h("p", { class: "muted", text: "Scores are heuristic structural similarity on a 0 to 100 scale. A high score is a lead worth checking, not evidence that the analogy holds." }));
  ms.forEach((m, i) => body.append(matchCard(m, i + 1)));
  if ((out.excluded || []).length) {
    body.append(h("details", { class: "card", style: "margin-top:12px" }, h("summary", { text: out.excluded.length + " candidates filtered out" }),
      h("ul", { class: "plain" }, out.excluded.slice(0, 40).map((e) => h("li", { text: e.system_id + ": " + e.reason })))));
  }
}

// ---------------------------------------------------------------- transformations
async function tabTransformations(body, state, ctx) {
  const out = ctx.stageOut("transformation");
  if (!out) return body.append(notice("Transformations appear once that stage finishes.", ""));
  const cs = out.concepts || [];
  if (!cs.length) return body.append(notice("No design concepts could be derived from these analogs.", "warn"));
  body.append(h("p", { class: "muted", text: out.note || "" }));
  for (const c of cs) {
    body.append(h("div", { class: "card", style: "margin-bottom:12px" },
      h("div", { class: "row spread" }, h("h3", { style: "margin:0", text: c.name }), h("span", { class: "row" }, pill(c.concept_type), pill(c.status, c.status === "ok" ? "ok" : "warn"))),
      h("p", { text: c.rationale }),
      h("p", {}, h("b", { text: "Expected effect: " }), c.expected_effect),
      h("p", { class: "muted", text: "From analog: " + c.analog_name + " (match score " + fmtScore(c.analog_score) + ")" }),
      (c.steps || []).length ? h("ol", { class: "plain" }, c.steps.map((s) => h("li", { text: s.action }))) : null,
      (c.preconditions || []).length ? h("div", {}, h("b", { text: "Preconditions" }), h("ul", { class: "plain" }, c.preconditions.map((p) => h("li", { text: p })))) : null,
      (c.caveats || []).length ? h("div", {}, h("b", { text: "Caveats" }), h("ul", { class: "plain" }, c.caveats.map((p) => h("li", { text: p })))) : null));
  }
}

// ---------------------------------------------------------------- hypotheses arena
const DECISION_LABEL = { none: "Undecided", saved: "Save", rejected: "Reject", promoted: "Accept" };
async function tabHypotheses(body, state, ctx) {
  const gen = ctx.stageOut("hypothesis_generation");
  if (!gen) return body.append(notice("Hypotheses appear once that stage finishes.", ""));
  const annots = (await api("GET", "/discoveries/" + ctx.id + "/annotations")).items;
  const items = mergeHypotheses(ctx.stageOut("validation"), gen, annots);
  if (!items.length) return body.append(notice("No hypotheses were generated for this problem.", "warn"));
  body.append(h("p", { class: "muted", text: "Your decisions and notes are saved on this server and appear in the exported report." }));
  for (const it of items) {
    const hyp = it.hypothesis;
    let decision = it.decision;
    const note = h("textarea", { style: "min-height:70px", maxlength: "5000", "aria-label": "Note for " + hyp.id, placeholder: "Your notes" });
    note.value = it.note;
    const status = h("span", { class: "muted", "aria-live": "polite" });
    const buttons = {};
    const save = async () => {
      status.textContent = "Saving...";
      try { await api("PUT", "/discoveries/" + ctx.id + "/annotations/" + encodeURIComponent(hyp.id), { decision, note: note.value }); status.textContent = "Saved"; }
      catch (e) { status.textContent = ""; toast(e.message, "bad"); }
    };
    const dec = h("div", { class: "decisions", role: "group", "aria-label": "Decision for " + hyp.id });
    for (const d of ["saved", "rejected", "promoted"]) {
      buttons[d] = h("button", { type: "button", "data-d": d, "aria-pressed": String(decision === d), text: DECISION_LABEL[d], onclick: () => {
        decision = decision === d ? "none" : d;
        for (const [k, b] of Object.entries(buttons)) b.setAttribute("aria-pressed", String(decision === k));
        save();
      } });
      dec.append(buttons[d]);
    }
    let timer = null;
    note.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(save, 700); });
    note.addEventListener("blur", () => { clearTimeout(timer); if (note.value !== it.note) { it.note = note.value; save(); } });
    const v = it.validation;
    body.append(h("div", { class: "card", style: "margin-bottom:14px" },
      h("div", { class: "row spread" }, h("span", { class: "row" }, h("b", { text: hyp.id }), pill(hyp.category || "hypothesis"), provLabel(hyp.provenance)),
        v ? pill("validation: " + v.outcome, v.outcome === "supported" ? "ok" : v.outcome === "refuted" ? "bad" : "warn") : pill(hyp.status || "untested")),
      h("p", { text: hyp.statement }),
      h("p", {}, h("b", { text: "Prediction: " }), hyp.prediction),
      h("p", {}, h("b", { text: "Falsifier: " }), hyp.falsifier),
      v && v.caveats ? notice(v.caveats, "warn") : null,
      h("div", { class: "row spread" }, dec, status), note));
  }
}

// ---------------------------------------------------------------- validation
async function tabValidation(body, state, ctx) {
  const out = ctx.stageOut("validation");
  if (!out) return body.append(notice("Validation results appear once that stage finishes.", ""));
  const vs = out.validations || [];
  body.append(h("p", { class: "muted", text: out.note || "" }));
  if (!vs.length) return body.append(notice("Nothing was simulated for these hypotheses.", "warn"));
  const rows = vs.map((v) => {
    const e = v.evidence || {};
    return h("tr", {},
      h("td", { class: "mono", text: v.hypothesis_id }),
      h("td", {}, pill(v.outcome, v.outcome === "supported" ? "ok" : v.outcome === "refuted" ? "bad" : "warn")),
      h("td", { text: v.method }),
      h("td", { class: "mono", text: e.metric ? e.metric + ": " + fmtScore(e.baseline_mean, 3) + " to " + fmtScore(e.proposed_mean, 3) : "n/a" }),
      h("td", { class: "mono", text: e.n ? "win rate " + fmtPercent(e.win_rate) + " over " + e.n + " seeds" : "n/a" }),
      h("td", { class: "muted", text: v.caveats || "" }));
  });
  body.append(h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Hypothesis", "Outcome", "Method", "Metric", "Runs", "Caveats"].map((t) => h("th", { text: t })))), h("tbody", {}, rows))));
}

// ---------------------------------------------------------------- report
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function tabReport(body, state, ctx) {
  if (state.run.status !== "done") return body.append(notice("The report is available when the run is done.", ""));
  const md = await api("GET", "/discoveries/" + ctx.id + "/report?format=md", undefined, true);
  body.append(h("div", { class: "row", style: "margin-bottom:12px" },
    h("button", { class: "primary", text: "Download Markdown", onclick: () => download("isomorph-report-" + ctx.id.slice(0, 8) + ".md", md, "text/markdown") }),
    h("button", { text: "Download JSON", onclick: async () => {
      try { download("isomorph-report-" + ctx.id.slice(0, 8) + ".json", await api("GET", "/discoveries/" + ctx.id + "/report?format=json", undefined, true), "application/json"); }
      catch (e) { toast(e.message, "bad"); }
    } })),
    h("pre", { class: "md", tabindex: "0", text: md }));
}

// ---------------------------------------------------------------- knowledge library
async function viewKnowledge(r) {
  document.title = "Knowledge library | ISOMORPH";
  const [doms] = await Promise.all([api("GET", "/domains?limit=100")]);
  const all = [];
  for (let off = 0; ; off += 100) {
    const page = await api("GET", "/knowledge-systems?limit=100&offset=" + off);
    all.push(...page.items);
    if (all.length >= page.total || !page.items.length) break;
  }
  const q = h("input", { type: "search", id: "q", placeholder: "Search systems", "aria-label": "Search systems" });
  const dom = h("select", { "aria-label": "Filter by domain" }, h("option", { value: "", text: "All domains" }),
    doms.items.map((d) => h("option", { value: d.id, text: (d.name || d.id) + " (" + d.system_count + ")" })));
  const list = h("div", { class: "grid" });
  const detail = h("div");
  const count = h("p", { class: "muted" });
  function draw() {
    clear(list);
    const rows = filterSystems(all, q.value, dom.value);
    count.textContent = rows.length + " of " + all.length + " systems";
    for (const s of rows) {
      list.append(h("a", { class: "card link", href: "#/knowledge/" + encodeURIComponent(s.id) },
        h("div", { class: "row spread" }, pill(s.domain), pill(s.confidence, s.confidence === "high" ? "ok" : "mute")),
        h("h3", { text: s.name }), h("p", { class: "muted", text: s.summary })));
    }
    if (!rows.length) list.append(h("div", { class: "empty" }, "No systems match that search."));
  }
  q.addEventListener("input", draw);
  dom.addEventListener("change", draw);
  mount(h("h1", { text: "Knowledge library" }), h("p", { class: "sub", text: "The curated systems ISOMORPH searches for analogies. Each is a qualitative abstraction with cited sources." }),
    detail, h("div", { class: "row" }, h("div", { style: "flex:1;min-width:200px" }, q), h("div", { style: "min-width:200px" }, dom)), count, list);
  draw();
  if (r.id) {
    const s = await api("GET", "/knowledge-systems/" + encodeURIComponent(r.id));
    detail.append(h("div", { class: "card", style: "margin-bottom:18px" },
      h("div", { class: "row spread" }, h("h2", { style: "margin:0", text: s.name }), h("a", { class: "btn small", href: "#/knowledge", text: "Close" })),
      h("p", { class: "row" }, pill(s.domain), pill(s.kind), pill("confidence " + s.confidence)),
      h("p", { text: s.summary }),
      h("p", { class: "muted", text: s.limitations }),
      h("h3", { text: "Structure" }),
      h("p", { class: "muted", text: (s.graph.nodes || []).length + " elements, " + (s.graph.edges || []).length + " relationships" }),
      h("ul", { class: "plain" }, (s.graph.nodes || []).map((n) => h("li", {}, h("b", { text: n.label }), " ", h("span", { class: "muted", text: "(" + (n.role || "no role") + ")" })))),
      (s.dynamics || []).length ? h("p", {}, h("b", { text: "Dynamics: " }), s.dynamics.join(", ")) : null,
      h("h3", { text: "Sources" }),
      h("ul", { class: "plain" }, (s.sources || []).map((x) => h("li", {}, provLabel("source"), " ", x.citation || "", x.note ? " " : "", h("span", { class: "muted", text: x.note || "" }))))));
  }
}

// ---------------------------------------------------------------- settings
async function viewSettings() {
  document.title = "Settings | ISOMORPH";
  const [s, hl] = await Promise.all([api("GET", "/settings"), api("GET", "/health")]);
  const row = (k, v) => h("tr", {}, h("th", { text: k }), h("td", { class: "mono", text: String(v) }));
  mount(h("h1", { text: "Settings and status" }), h("p", { class: "sub", text: "Read-only. Change these with environment variables or CLI flags, then restart." }),
    h("div", { class: "card" }, h("table", {}, h("tbody", {},
      row("Version", s.version), row("Server status", hl.status), row("Database schema", hl.schema_version), row("Stored investigations", hl.runs),
      row("AI provider", s.provider), row("Data directory", s.home), row("Access token", s.auth_required ? "required" : "not required (local only)"),
      row("Max request size", s.max_body_bytes + " bytes"), row("Knowledge base", s.knowledge.systems + " systems in " + s.knowledge.domains + " domains")))),
    s.provider === "local" ? notice("The local provider is deterministic and offline. It reads keywords and sentence patterns, so unusual wording can be missed. Remote providers are optional and only used for the first stage.", "") : null,
    h("h2", { text: "Honest limits" }),
    h("ul", { class: "plain" },
      h("li", { text: "Perception is keyword and pattern based. It does not deeply understand prose." }),
      h("li", { text: "PDF and image files are not interpreted. Only .txt, .md and .json uploads are read." }),
      h("li", { text: "Hypothesis simulations that use template parameters are capped at inconclusive." }),
      h("li", { text: "Runs execute in this server process. A restart marks interrupted runs as failed. Use Resume." }),
      h("li", { text: "This mode is single-user and local. Use ISOMORPH_TOKEN and a TLS proxy if you expose it." })),
    disclaimer());
}

route();
