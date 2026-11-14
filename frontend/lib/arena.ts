import type { HypothesisRecord, ServerAnnotation } from "@/services/types";

export type Decision = "none" | "saved" | "rejected" | "promoted";
export interface Annotation {
  decision: Decision;
  note: string;
}
export type Annotations = Record<string, Annotation>;

/** Server decisions win over the browser copy for the same hypothesis. Hypotheses only in the browser copy are kept. */
export function mergeAnnotations(local: Annotations, server: Record<string, Pick<ServerAnnotation, "decision" | "note">>): Annotations {
  const out: Annotations = { ...local };
  for (const [id, a] of Object.entries(server)) out[id] = { decision: a.decision, note: a.note };
  return out;
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
