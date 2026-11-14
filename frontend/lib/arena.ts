import type { HypothesisRecord, ServerAnnotation } from "@/services/types";

export type Decision = "none" | "saved" | "rejected" | "promoted";
export interface Annotation {
  decision: Decision;
  note: string;
}
export type Annotations = Record<string, Annotation>;

export type AnnotationTimes = Record<string, number>;

/**
 * Merge server annotations over the browser copy. The newer edit wins per hypothesis: a browser edit made after the
 * server's `updated_at` (seconds) is kept. `localTimes` holds browser edit times in seconds. Returns the merged
 * annotations and the ids whose browser edits were newer and should be pushed to the server.
 */
export function mergeAnnotations(
  local: Annotations,
  server: Record<string, Pick<ServerAnnotation, "decision" | "note"> & { updated_at?: number }>,
  localTimes: AnnotationTimes = {},
): { merged: Annotations; push: string[] } {
  const merged: Annotations = { ...local };
  const push: string[] = [];
  for (const [id, a] of Object.entries(server)) {
    const localT = localTimes[id];
    if (local[id] && localT !== undefined && localT > (a.updated_at ?? 0)) push.push(id);
    else merged[id] = { decision: a.decision, note: a.note };
  }
  return { merged, push };
}

export const MAX_COMPARE = 3;

/** Toggle a hypothesis in the comparison set, never exceeding MAX_COMPARE. Returns the same array when the add is refused. */
export function toggleCompare(selected: string[], id: string): string[] {
  if (selected.includes(id)) return selected.filter((s) => s !== id);
  return selected.length >= MAX_COMPARE ? selected : [...selected, id];
}

export function hypothesesToMarkdown(items: Array<HypothesisRecord & { annotation?: Annotation }>): string {
  const lines = ["# Hypotheses", "", "These are hypotheses from structural analogy. They are not proven.", ""];
  for (const h of items) {
    lines.push(`## ${h.id}`, "", h.statement, "", `- Prediction: ${h.prediction}`, `- Falsifier: ${h.falsifier}`, `- Category: ${h.category}`, `- Provenance: ${h.provenance}`, `- Validation status: ${h.status}`);
    if (h.annotation && h.annotation.decision !== "none") lines.push(`- Your decision: ${h.annotation.decision}`);
    if (h.annotation?.note) lines.push(`- Note: ${h.annotation.note}`);
    lines.push("");
  }
  return lines.join("\n");
}
