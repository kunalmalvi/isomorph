/** Dependency free projection of match candidates into a 3D-style scene. Pure and deterministic. */

export interface UniverseInput {
  id: string;
  domain: string;
  score: number; // 0 to 100
  domain_distance: number; // 0 to 1
}

export interface UniversePoint {
  id: string;
  domain: string;
  x: number;
  y: number;
  z: number;
}

export interface ProjectedPoint {
  id: string;
  domain: string;
  sx: number;
  sy: number;
  /** Scale factor from perspective, larger means nearer to the viewer. */
  scale: number;
  depth: number;
}

function clamp(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo;
  return Math.min(hi, Math.max(lo, v));
}

/** Stable 0..1 hash of a string, used so equal inputs always get the same angle. */
export function hash01(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h / 4294967296;
}

/**
 * Place each candidate on a sphere-like shell around the origin (the user's problem).
 * Radius grows with domain distance. Height (y) encodes score. The angle comes from the domain
 * so systems of one domain share a sector, with a small per-system offset.
 */
export function layoutUniverse(items: UniverseInput[], radius = 100): UniversePoint[] {
  const sorted = [...items].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return sorted.map((it) => {
    const r = radius * (0.25 + 0.75 * clamp(it.domain_distance, 0, 1));
    const theta = (hash01(it.domain) + 0.08 * hash01(it.id)) * Math.PI * 2;
    const y = (clamp(it.score, 0, 100) / 100 - 0.5) * radius * 1.5;
    return { id: it.id, domain: it.domain, x: r * Math.cos(theta), y, z: r * Math.sin(theta) };
  });
}

/** Rotate around the vertical axis then project with a simple perspective camera. */
export function projectPoints(points: UniversePoint[], angle: number, width: number, height: number, cameraDistance = 320): ProjectedPoint[] {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const out = points.map((p) => {
    const rx = p.x * cos - p.z * sin;
    const rz = p.x * sin + p.z * cos;
    const scale = cameraDistance / (cameraDistance + rz);
    return { id: p.id, domain: p.domain, sx: width / 2 + rx * scale, sy: height / 2 - p.y * scale, scale, depth: rz };
  });
  // Far points first so near points draw on top.
  return out.sort((a, b) => b.depth - a.depth || (a.id < b.id ? -1 : 1));
}
