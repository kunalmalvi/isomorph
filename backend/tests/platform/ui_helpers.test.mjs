// Run with: node tests/platform/ui_helpers.test.mjs  (from backend/). Exits non-zero on failure.
import assert from "node:assert/strict";
import {
  checkUpload, textFromUpload, errorMessage, parseSse, progressFraction, scoreBand, fmtScore, fmtPercent, relTime,
  breakdownRows, layoutMapping, filterSystems, mergeHypotheses, parseRoute, STAGES, EXAMPLES,
} from "../../isomorph_app/static/lib.js";

let n = 0;
const t = (name, fn) => { fn(); n += 1; };

t("upload checks", () => {
  assert.equal(checkUpload("a.txt", 10), null);
  assert.match(checkUpload("a.pdf", 10), /PDF and images/);
  assert.match(checkUpload("a.md", 10 ** 7), /200 KB/);
});
t("upload text", () => {
  assert.equal(textFromUpload("a.txt", "  hi  "), "hi");
  assert.equal(textFromUpload("a.json", '{"statement":" s "}'), "s");
  assert.throws(() => textFromUpload("a.json", "{"), /not valid JSON/);
  assert.throws(() => textFromUpload("a.json", "{}"), /statement/);
});
t("error messages", () => {
  assert.match(errorMessage(0, null), /Cannot reach/);
  assert.equal(errorMessage(404, { error: { message: "gone" } }), "gone");
  assert.match(errorMessage(500, null), /internal error/);
  assert.match(errorMessage(401, null), /token/);
});
t("sse parser handles partial chunks", () => {
  const a = parseSse('retry: 2000\n\nid: 1\nevent: progress\ndata: {"status":"running"}\n\nid: 2\nevent: pro');
  assert.equal(a.events.length, 1);
  assert.equal(a.events[0].event, "progress");
  assert.equal(a.events[0].data.status, "running");
  const b = parseSse(a.rest + 'gress\ndata: {"status":"done"}\n\n');
  assert.equal(b.events[0].data.status, "done");
  assert.equal(parseSse("event: x\ndata: {bad\n\n").events.length, 0);
});
t("progress and formatting", () => {
  assert.equal(progressFraction([{ status: "done" }, { status: "running" }]), 0.5);
  assert.equal(progressFraction([]), 0);
  assert.equal(scoreBand(80), "strong");
  assert.equal(scoreBand(36.5), "weak");
  assert.equal(fmtScore(36.519), "36.5");
  assert.equal(fmtScore(undefined), "n/a");
  assert.equal(fmtPercent(0.304), "30%");
  assert.equal(relTime(0, 120), "2 min ago");
});
t("breakdown rows sorted with fill", () => {
  const rows = breakdownRows({ a: { score: 1, weight: 10, contribution: 2 }, b: { score: 1, weight: 10, contribution: 9, explanation: "e" } });
  assert.equal(rows[0].name, "b");
  assert.equal(rows[0].fill, 0.9);
});
t("mapping layout", () => {
  const g = layoutMapping({ node_pairs: [["a", "x", 0.5], ["b", "y", 0.2]], unmapped_source: ["c", "a"], unmapped_target: ["z"] });
  assert.equal(g.links.length, 2);
  assert.equal(g.nodes.filter((x) => x.side === "L").length, 3);
  assert.equal(g.nodes.filter((x) => x.side === "R" && !x.mapped).length, 1);
  assert.ok(g.height > 0);
  assert.equal(layoutMapping(null).nodes.length, 0);
});
t("filter systems", () => {
  const s = [{ name: "Tank", summary: "stores heat", domain: "energy" }, { name: "Valve", summary: "controls", domain: "fluids" }];
  assert.equal(filterSystems(s, "HEAT", "").length, 1);
  assert.equal(filterSystems(s, "", "fluids")[0].name, "Valve");
  assert.equal(filterSystems(s, "", "").length, 2);
});
t("merge hypotheses", () => {
  const gen = { hypotheses: [{ id: "H1" }] };
  const m = mergeHypotheses(null, gen, { H1: { decision: "saved", note: "n" } });
  assert.equal(m[0].decision, "saved");
  const v = mergeHypotheses({ hypotheses: [{ id: "H1" }], validations: [{ hypothesis_id: "H1", outcome: "inconclusive" }] }, gen, {});
  assert.equal(v[0].validation.outcome, "inconclusive");
  assert.equal(v[0].decision, "none");
});
t("routes", () => {
  assert.deepEqual(parseRoute(""), { name: "home" });
  assert.deepEqual(parseRoute("#/run/abc/matches"), { name: "run", id: "abc", tab: "matches" });
  assert.equal(parseRoute("#/run/abc").tab, "progress");
  assert.equal(parseRoute("#/knowledge/x").id, "x");
  assert.equal(parseRoute("#/nope").name, "notfound");
});
t("stages match the engine order and examples exist", () => {
  assert.equal(STAGES.length, 9);
  assert.equal(STAGES[0][0], "perception");
  assert.ok(EXAMPLES[0].text.includes("copper or silver"));
});
console.log(`ui helper tests passed: ${n}`);
