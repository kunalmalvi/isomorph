import { layoutUniverse, projectPoints } from "../lib/universe-layout.ts";
import assert from "node:assert";
const items = [
  { id: "a", domain: "biology", score: 80, domain_distance: 0.9 },
  { id: "b", domain: "economics", score: 20, domain_distance: 0.1 },
];
assert.deepStrictEqual(layoutUniverse(items), layoutUniverse([...items].reverse()));
const [a, b] = layoutUniverse(items);
assert(Math.hypot(a.x, a.z) > Math.hypot(b.x, b.z));
const p = layoutUniverse([{ id: "x", domain: "d", score: NaN, domain_distance: 5 }]);
assert(Number.isFinite(p[0].x + p[0].y + p[0].z));
const proj = projectPoints(layoutUniverse(items), 0.3, 600, 400);
assert.strictEqual(proj.length, 2);
assert(proj[0].depth >= proj[1].depth);
console.log("universe assertions ok");
