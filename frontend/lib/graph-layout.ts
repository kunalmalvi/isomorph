import type { Graph } from "@/services/types";

export interface Positioned {
  id: string;
  x: number;
  y: number;
}

/** Layered layout: depth is the longest path from a source, capped to survive cycles. Deterministic and dependency free. */
export function layerLayout(graph: Graph, dx = 220, dy = 90): Positioned[] {
  const ids = graph.nodes.map((n) => n.id);
  const known = new Set(ids);
  const depth = new Map<string, number>(ids.map((i) => [i, 0]));
  const edges = graph.edges.filter((e) => known.has(e.source) && known.has(e.target) && e.source !== e.target);
  for (let pass = 0; pass < ids.length; pass++) {
    let changed = false;
    for (const e of edges) {
      const next = (depth.get(e.source) ?? 0) + 1;
      if (next > (depth.get(e.target) ?? 0) && next < ids.length) {
        depth.set(e.target, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const rows = new Map<number, number>();
  return ids.map((id) => {
    const d = depth.get(id) ?? 0;
    const r = rows.get(d) ?? 0;
    rows.set(d, r + 1);
    return { id, x: d * dx, y: r * dy };
  });
}

export function filterGraph(graph: Graph, opts: { text?: string; kind?: string; role?: string }): Graph {
  const t = (opts.text ?? "").trim().toLowerCase();
  const nodes = graph.nodes.filter(
    (n) => (!opts.kind || n.kind === opts.kind) && (!opts.role || n.role === opts.role) && (!t || n.label.toLowerCase().includes(t) || n.id.toLowerCase().includes(t)),
  );
  const keep = new Set(nodes.map((n) => n.id));
  return { nodes, edges: graph.edges.filter((e) => keep.has(e.source) && keep.has(e.target)) };
}
