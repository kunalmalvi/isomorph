import type { HypothesisRecord } from "@/services/types";

export type Decision = "none" | "saved" | "rejected" | "promoted";
export interface Annotation {
  decision: Decision;
  note: string;
}
export type Annotations = Record<string, Annotation>;

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
