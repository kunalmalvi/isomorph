import { describe, expect, it } from "vitest";
import { MAX_COMPARE, hypothesesToMarkdown, mergeAnnotations, toggleCompare } from "@/lib/arena";
import type { HypothesisRecord } from "@/services/types";

describe("toggleCompare", () => {
  it("never exceeds three selections", () => {
    let sel: string[] = [];
    for (const id of ["a", "b", "c", "d"]) sel = toggleCompare(sel, id);
    expect(sel).toEqual(["a", "b", "c"]);
    expect(sel.length).toBe(MAX_COMPARE);
  });
  it("removes an already selected item", () => {
    expect(toggleCompare(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("hypothesesToMarkdown", () => {
  const h: HypothesisRecord = {
    id: "H1", statement: "If X then Y", prediction: "Y improves", falsifier: "No change", category: "robustness",
    provenance: "computation", status: "untested", based_on: [], experiment: null,
  };
  it("states that hypotheses are unproven and includes the decision and note", () => {
    const md = hypothesesToMarkdown([{ ...h, annotation: { decision: "promoted", note: "check with team" } }]);
    expect(md).toContain("not proven");
    expect(md).toContain("Your decision: promoted");
    expect(md).toContain("Note: check with team");
  });
  it("omits decision when none was made", () => {
    expect(hypothesesToMarkdown([h])).not.toContain("Your decision");
  });
});

describe("mergeAnnotations", () => {
  const local = { a: { decision: "saved" as const, note: "local" }, b: { decision: "none" as const, note: "only here" } };
  it("lets the server win without browser edit times and keeps browser only entries", () => {
    const r = mergeAnnotations(local, { a: { decision: "rejected", note: "server", updated_at: 100 } });
    expect(r.merged).toEqual({ a: { decision: "rejected", note: "server" }, b: { decision: "none", note: "only here" } });
    expect(r.push).toEqual([]);
  });
  it("keeps a browser edit that is newer than the server copy and reports it for upload", () => {
    const r = mergeAnnotations(local, { a: { decision: "rejected", note: "server", updated_at: 100 } }, { a: 200 });
    expect(r.merged.a).toEqual({ decision: "saved", note: "local" });
    expect(r.push).toEqual(["a"]);
  });
  it("takes the server copy when it is newer than the browser edit", () => {
    const r = mergeAnnotations(local, { a: { decision: "rejected", note: "server", updated_at: 300 } }, { a: 200 });
    expect(r.merged.a.note).toBe("server");
    expect(r.push).toEqual([]);
  });
});
