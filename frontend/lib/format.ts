/** Pure formatting and data helpers. Covered by tests/unit. */

export function formatScore(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(digits);
}

export function titleCase(key: string): string {
  const s = key.replace(/[_-]+/g, " ").trim();
  return s.length === 0 ? s : s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatDate(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "n/a";
  const d = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(d.getTime())) return "n/a";
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

/** Weights must sum to 100 (the API rejects anything else with 422). */
export const WEIGHT_KEYS = ["functional", "relationship", "topological", "dynamic", "constraint", "semantic"] as const;
export type WeightKey = (typeof WEIGHT_KEYS)[number];
export type Weights = Record<WeightKey, number>;
export const DEFAULT_WEIGHTS: Weights = {
  functional: 25,
  relationship: 25,
  topological: 20,
  dynamic: 15,
  constraint: 10,
  semantic: 5,
};

export function weightsTotal(w: Weights): number {
  return WEIGHT_KEYS.reduce((sum, k) => sum + (Number.isFinite(w[k]) ? w[k] : 0), 0);
}

export function weightsValid(w: Weights): boolean {
  return WEIGHT_KEYS.every((k) => Number.isFinite(w[k]) && w[k] >= 0) && Math.abs(weightsTotal(w) - 100) < 1e-9;
}

/** Escape one CSV cell (RFC 4180) and neutralise spreadsheet formula injection. */
export function csvCell(value: unknown): string {
  let s = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export function toCsv(rows: Array<Record<string, unknown>>, columns: string[]): string {
  const lines = [columns.map(csvCell).join(",")];
  for (const r of rows) lines.push(columns.map((c) => csvCell(r[c])).join(","));
  return lines.join("\n") + "\n";
}

/** Parse user JSON for the stage editor. Returns an error string instead of throwing. */
export function parseJsonObject(text: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  try {
    const v: unknown = JSON.parse(text);
    if (v === null || typeof v !== "object" || Array.isArray(v)) return { ok: false, error: "Stage output must be a JSON object." };
    return { ok: true, value: v as Record<string, unknown> };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON" };
  }
}

/** Collect top level numeric fields of an object, for charts. Nothing is invented. */
export function numericEntries(obj: unknown): Array<{ name: string; value: number }> {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return [];
  return Object.entries(obj as Record<string, unknown>)
    .filter(([, v]) => typeof v === "number" && Number.isFinite(v))
    .map(([name, value]) => ({ name, value: value as number }));
}

export const STAGE_ORDER = [
  "perception",
  "structural_extraction",
  "structural_dna",
  "cross_domain_search",
  "structural_matching",
  "mechanism_mapping",
  "transformation",
  "hypothesis_generation",
  "validation",
] as const;
export type StageName = (typeof STAGE_ORDER)[number];

export function isTerminal(status: string): boolean {
  return status === "done" || status === "failed" || status === "cancelled";
}
