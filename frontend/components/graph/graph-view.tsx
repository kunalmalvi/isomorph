"use client";
import * as React from "react";
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layerLayout } from "@/lib/graph-layout";
import type { Graph } from "@/services/types";

const ROLE_COLOR: Record<string, string> = {
  source: "#22d3ee", sink: "#a78bfa", controller: "#7c9cff", sensor: "#34d399", actuator: "#fbbf24", buffer: "#94a3b8",
};

export function GraphView({ graph, height = 420, label }: { graph: Graph; height?: number; label: string }) {
  const { nodes, edges } = React.useMemo(() => {
    const pos = new Map(layerLayout(graph).map((p) => [p.id, p]));
    const nodes: Node[] = graph.nodes.map((n) => ({
      id: n.id,
      position: { x: pos.get(n.id)?.x ?? 0, y: pos.get(n.id)?.y ?? 0 },
      data: { label: n.label },
      style: {
        background: "hsl(225 13% 13%)", color: "hsl(220 14% 93%)", fontSize: 12, padding: 8, borderRadius: 8,
        border: `1px solid ${ROLE_COLOR[n.role ?? ""] ?? "#475569"}`,
      },
    }));
    const edges: Edge[] = graph.edges.map((e) => ({
      id: e.id, source: e.source, target: e.target, label: e.relation, animated: false,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#64748b" }, labelStyle: { fill: "#94a3b8", fontSize: 10 }, labelBgStyle: { fill: "hsl(225 14% 8%)" },
    }));
    return { nodes, edges };
  }, [graph]);

  if (graph.nodes.length === 0) return <p className="p-6 text-sm text-muted-foreground">No nodes match the current filter.</p>;
  return (
    <div role="img" aria-label={label} style={{ height }} className="rounded-lg border">
      <ReactFlow nodes={nodes} edges={edges} fitView nodesConnectable={false} nodesDraggable colorMode="dark" proOptions={{ hideAttribution: true }}>
        <Background gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
