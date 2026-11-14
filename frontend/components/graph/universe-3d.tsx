"use client";
import * as React from "react";
import { layoutUniverse, projectPoints, hash01 } from "@/lib/universe-layout";

export interface UniverseDatum {
  id: string;
  system_name: string;
  domain: string;
  score: number;
  domain_distance: number;
}

const W = 640;
const H = 380;

/** Dependency free SVG scene with a drag-to-rotate camera. UNVERIFIED: never rendered in the authoring sandbox. */
export function Universe3D({ data, selectedId, onSelect }: { data: UniverseDatum[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const [angle, setAngle] = React.useState(0.5);
  const drag = React.useRef<number | null>(null);
  const points = React.useMemo(() => layoutUniverse(data), [data]);
  const projected = projectPoints(points, angle, W, H);
  const names = new Map(data.map((d) => [d.id, d]));

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-none rounded-md border bg-background"
        role="img"
        aria-label="Three dimensional style view of candidate systems. Distance from centre is domain distance, height is match score. Drag or use the buttons to rotate."
        onPointerDown={(e) => { drag.current = e.clientX; (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => { if (drag.current !== null) { setAngle((a) => a + (e.clientX - (drag.current as number)) * 0.01); drag.current = e.clientX; } }}
        onPointerUp={() => { drag.current = null; }}
      >
        <circle cx={W / 2} cy={H / 2} r={6} fill="#facc15"><title>Your problem</title></circle>
        {projected.map((p) => {
          const d = names.get(p.id);
          const hue = Math.round(hash01(p.domain) * 360);
          const selected = p.id === selectedId;
          return (
            <g key={p.id} tabIndex={0} role="button" aria-label={`${d?.system_name ?? p.id}, ${p.domain}`} onClick={() => onSelect(p.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(p.id); }} className="cursor-pointer">
              <circle cx={p.sx} cy={p.sy} r={Math.max(3, 7 * p.scale)} fill={`hsl(${hue} 70% 60%)`} fillOpacity={Math.min(1, 0.35 + 0.65 * p.scale / 1.4)} stroke={selected ? "#fff" : "none"} strokeWidth={2}>
                <title>{`${d?.system_name ?? p.id} (${p.domain}), score ${d?.score ?? "?"}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex gap-2">
        <button type="button" className="rounded border px-2 py-1 text-xs" onClick={() => setAngle((a) => a - 0.3)}>Rotate left</button>
        <button type="button" className="rounded border px-2 py-1 text-xs" onClick={() => setAngle((a) => a + 0.3)}>Rotate right</button>
      </div>
    </div>
  );
}
