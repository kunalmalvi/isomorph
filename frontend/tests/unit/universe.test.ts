import { describe, expect, it } from "vitest";
import { layoutUniverse, projectPoints } from "@/lib/universe-layout";

const items = [
  { id: "a", domain: "biology", score: 80, domain_distance: 0.9 },
  { id: "b", domain: "economics", score: 20, domain_distance: 0.1 },
];

describe("universe layout", () => {
  it("is deterministic and independent of input order", () => {
    expect(layoutUniverse(items)).toEqual(layoutUniverse([...items].reverse()));
  });
  it("places distant domains farther from the origin", () => {
    const [a, b] = layoutUniverse(items);
    expect(Math.hypot(a.x, a.z)).toBeGreaterThan(Math.hypot(b.x, b.z));
  });
  it("survives bad numbers", () => {
    const p = layoutUniverse([{ id: "x", domain: "d", score: NaN, domain_distance: 5 }]);
    expect(Number.isFinite(p[0].x + p[0].y + p[0].z)).toBe(true);
  });
  it("projects near points larger than far points", () => {
    const proj = projectPoints(layoutUniverse(items), 0.3, 600, 400);
    expect(proj).toHaveLength(2);
    expect(proj[0].depth).toBeGreaterThanOrEqual(proj[1].depth);
  });
});
