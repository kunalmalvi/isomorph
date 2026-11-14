import { describe, expect, it } from "vitest";
import { filterGraph, layerLayout } from "@/lib/graph-layout";
import { filterCommands, isActive } from "@/lib/commands";
import type { Graph } from "@/services/types";

const g: Graph = {
  nodes: [
    { id: "a", label: "Roller", kind: "component", role: "actuator" },
    { id: "b", label: "Strip", kind: "material", role: "medium" },
    { id: "c", label: "Sensor", kind: "component", role: "sensor" },
  ],
  edges: [
    { id: "e1", source: "a", target: "b", relation: "acts_on" },
    { id: "e2", source: "b", target: "c", relation: "measured_by" },
  ],
};

describe("layerLayout", () => {
  it("places nodes by longest path depth", () => {
    const pos = Object.fromEntries(layerLayout(g).map((p) => [p.id, p.x]));
    expect(pos.a).toBe(0);
    expect(pos.b).toBeGreaterThan(pos.a);
    expect(pos.c).toBeGreaterThan(pos.b);
  });
  it("terminates on cycles", () => {
    const cyc: Graph = { nodes: g.nodes, edges: [...g.edges, { id: "e3", source: "c", target: "a", relation: "feeds" }] };
    expect(layerLayout(cyc)).toHaveLength(3);
  });
});

describe("filterGraph", () => {
  it("filters by text and drops dangling edges", () => {
    const f = filterGraph(g, { text: "roll" });
    expect(f.nodes.map((n) => n.id)).toEqual(["a"]);
    expect(f.edges).toEqual([]);
  });
  it("filters by kind", () => {
    expect(filterGraph(g, { kind: "component" }).nodes).toHaveLength(2);
  });
});

describe("commands", () => {
  const items = [
    { label: "Overview", description: "Totals" },
    { label: "Settings", description: "Providers" },
  ];
  it("filters by label or description", () => {
    expect(filterCommands(items, "prov")).toEqual([items[1]]);
    expect(filterCommands(items, "")).toEqual(items);
  });
  it("matches active nav entries", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/investigations/1", "/investigations")).toBe(true);
    expect(isActive("/investigations", "/")).toBe(false);
  });
});
