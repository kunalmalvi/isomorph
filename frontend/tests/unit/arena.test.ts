import { describe, expect, it } from "vitest";
import { MAX_COMPARE, hypothesesToMarkdown, toggleCompare } from "@/lib/arena";
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
