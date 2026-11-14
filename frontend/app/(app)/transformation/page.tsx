"use client";
import * as React from "react";
import { api } from "@/services/api";
import { InvestigationScope } from "@/components/investigation-picker";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { EmptyState, errorMessage } from "@/components/ui/states";
import { JsonView } from "@/components/json-view";
import { formatScore, titleCase } from "@/lib/format";
import type { Concept } from "@/services/types";

interface MappingEntry {
  system_id: string;
  system_name: string;
  score: number;
  mapping: { node_pairs: unknown[]; edge_pairs: unknown[]; unmapped_source: string[]; unmapped_target: string[]; confidence: number };
  transferable_elements: Array<{ id: string; label: string; role: string }>;
}

function ConceptCard({ concept, runId, mapping }: { concept: Concept; runId: string; mapping?: MappingEntry }) {
  const [state, setState] = React.useState<{ kind: "idle" | "busy" | "ok" | "error"; text?: string }>({ kind: "idle" });
  const [showReport, setShowReport] = React.useState(false);

  async function save() {
    setState({ kind: "busy" });
    try {
      const matches = await api.discoveries.matches(runId, { limit: 100 });
      const match = matches.items.find((m) => m.system_key === concept.analog_id);
      if (!match) throw new Error("No stored match for this analog. Rerun the discovery with a larger match count.");
      const mp = await api.pipeline.createMapping(match.id);
      const tr = await api.pipeline.createTransformation(mp.id, concept.concept_type);
      const h = await api.pipeline.createHypothesis(tr.id);
      setState({ kind: "ok", text: `Saved. Hypothesis ${h.id.slice(0, 8)} is now listed in the Hypothesis Arena (status ${h.status}).` });
    } catch (e) {
      setState({ kind: "error", text: errorMessage(e) });
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{concept.name}</CardTitle>
          <div className="flex gap-2"><Badge tone="violet">{titleCase(concept.concept_type)}</Badge><StatusBadge status={concept.status} /></div>
        </div>
        <CardDescription>Borrowed from {concept.analog_name} (match score {formatScore(concept.analog_score)})</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{concept.rationale}</p>
        <p><span className="font-medium">Expected effect (hypothesised): </span>{concept.expected_effect}</p>
        {concept.preconditions.length > 0 && <div><p className="font-medium">Preconditions</p><ul className="list-disc pl-5 text-muted-foreground">{concept.preconditions.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
        {concept.caveats.length > 0 && <div><p className="font-medium text-warning">Caveats</p><ul className="list-disc pl-5 text-muted-foreground">{concept.caveats.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
        {mapping && (
          <p className="text-xs text-muted-foreground">
            Mapping confidence {formatScore(mapping.mapping.confidence, 2)}; {mapping.mapping.node_pairs.length} node pairs, {mapping.mapping.unmapped_source.length} unmapped problem nodes, {mapping.transferable_elements.length} transferable analog elements.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" aria-expanded={showReport} onClick={() => setShowReport(!showReport)}>{showReport ? "Hide" : "Show"} constraint report</Button>
          <Button size="sm" disabled={concept.status === "blocked" || state.kind === "busy"} onClick={save} title={concept.status === "blocked" ? "Blocked concepts violate a hard constraint" : undefined}>
            {state.kind === "busy" ? "Saving..." : "Save as hypothesis"}
          </Button>
        </div>
        {concept.status === "blocked" && <p className="text-xs text-danger">Blocked: this concept violates a hard constraint, so it cannot be saved.</p>}
        {showReport && <JsonView value={concept.constraint_report} />}
        {state.text && <p role={state.kind === "error" ? "alert" : "status"} className={`text-sm ${state.kind === "error" ? "text-danger" : "text-success"}`}>{state.text}</p>}
      </CardContent>
    </Card>
  );
}

export default function TransformationPage() {
  return (
    <>
      <PageHeader title="Transformation Studio" description="Concepts derived by transferring a mechanism from a matched system. They are analogies, not tested designs." />
      <InvestigationScope stages={["transformation", "mechanism_mapping"]}>
        {({ id, outputs }) => {
          const concepts = ((outputs.transformation.output as { concepts?: Concept[] }).concepts ?? []) as Concept[];
          const mappings = ((outputs.mechanism_mapping.output as { mappings?: MappingEntry[] }).mappings ?? []) as MappingEntry[];
          if (concepts.length === 0) return <EmptyState title="No concepts derived" hint="No mapping produced a grounded transformation for this problem." />;
          return (
            <div className="grid gap-4 xl:grid-cols-2">
              {concepts.map((c) => <ConceptCard key={c.id} concept={c} runId={id} mapping={mappings.find((m) => m.system_id === c.analog_id)} />)}
            </div>
          );
        }}
      </InvestigationScope>
    </>
  );
}
