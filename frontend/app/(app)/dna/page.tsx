"use client";
import * as React from "react";
import { InvestigationScope } from "@/components/investigation-picker";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { Table, Td, Th } from "@/components/ui/table";
import { ProvenanceBadge } from "@/components/ui/badge";
import { GraphView } from "@/components/graph/graph-view";
import { filterGraph } from "@/lib/graph-layout";
import { downloadText } from "@/services/api";
import { numericEntries, titleCase, toCsv } from "@/lib/format";
import type { Graph } from "@/services/types";

const FP_KEYS = ["functional", "relational", "topological", "dynamic", "constraint", "semantic"] as const;

function Sparkbars({ values, label }: { values: number[]; label: string }) {
  const max = Math.max(...values.map((v) => Math.abs(v)), 1e-9);
  return (
    <div role="img" aria-label={`${label}: ${values.length} dimensions`} className="flex h-10 items-end gap-px">
      {values.map((v, i) => (
        <div key={i} className="w-1 rounded-sm bg-primary/70" style={{ height: `${Math.max((Math.abs(v) / max) * 100, 2)}%` }} />
      ))}
    </div>
  );
}

function DnaBody({ extraction, dna }: { extraction: Record<string, unknown>; dna: Record<string, unknown> }) {
  const model = extraction.model as { graph: Graph; metrics: Record<string, unknown>; dynamics?: unknown; constraint_tags?: string[]; flags?: string[]; domain?: string };
  const fp = dna.fingerprint as Record<string, unknown> & { hash: string; schema_version: number };
  const [view, setView] = React.useState("graph");
  const [text, setText] = React.useState("");
  const [kind, setKind] = React.useState("");
  const [role, setRole] = React.useState("");
  const kinds = Array.from(new Set(model.graph.nodes.map((n) => n.kind).filter(Boolean))) as string[];
  const roles = Array.from(new Set(model.graph.nodes.map((n) => n.role).filter(Boolean))) as string[];
  const filtered = filterGraph(model.graph, { text, kind, role });

  const exportJson = () => downloadText("structural-model.json", JSON.stringify(model, null, 2), "application/json");
  const exportCsv = () =>
    downloadText(
      "structural-nodes.csv",
      toCsv(filtered.nodes.map((n) => ({ ...n })) as Array<Record<string, unknown>>, ["id", "label", "kind", "role", "confidence", "provenance"]),
      "text/csv",
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label htmlFor="dna-filter">Filter by label</Label>
          <Input id="dna-filter" value={text} onChange={(e) => setText(e.target.value)} placeholder="roller" />
        </div>
        <div>
          <Label htmlFor="dna-kind">Kind</Label>
          <Select id="dna-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All</option>
            {kinds.map((k) => <option key={k}>{k}</option>)}
          </Select>
        </div>
        <div>
          <Label htmlFor="dna-role">Role</Label>
          <Select id="dna-role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">All</option>
            {roles.map((k) => <option key={k}>{k}</option>)}
          </Select>
        </div>
        <Button variant="secondary" size="sm" onClick={exportJson}>Export model (JSON)</Button>
        <Button variant="secondary" size="sm" onClick={exportCsv}>Export nodes (CSV)</Button>
      </div>
      <Tabs label="Structural view" value={view} onChange={setView} items={[{ id: "graph", label: "Graph" }, { id: "table", label: "Table" }]} />
      {view === "graph" ? (
        <GraphView graph={filtered} label={`Structural graph with ${filtered.nodes.length} nodes and ${filtered.edges.length} edges`} />
      ) : (
        <Card>
          <Table>
            <thead><tr><Th>Label</Th><Th>Kind</Th><Th>Role</Th><Th>Confidence</Th><Th>Provenance</Th></tr></thead>
            <tbody>
              {filtered.nodes.map((n) => (
                <tr key={n.id}>
                  <Td>{n.label}</Td><Td>{n.kind ?? "n/a"}</Td><Td>{n.role ?? "n/a"}</Td>
                  <Td>{n.confidence !== undefined ? n.confidence.toFixed(2) : "n/a"}</Td>
                  <Td>{n.provenance ? <ProvenanceBadge provenance={n.provenance} /> : "n/a"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Table>
            <thead><tr><Th>Source</Th><Th>Relation</Th><Th>Target</Th><Th>Provenance</Th></tr></thead>
            <tbody>
              {filtered.edges.map((e) => (
                <tr key={e.id}><Td>{e.source}</Td><Td>{e.relation}</Td><Td>{e.target}</Td><Td>{e.provenance ? <ProvenanceBadge provenance={e.provenance} /> : "n/a"}</Td></tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Graph metrics</CardTitle><CardDescription>Computed from the extracted graph.</CardDescription></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {numericEntries(model.metrics).map((m) => (
                <React.Fragment key={m.name}>
                  <dt className="text-muted-foreground">{titleCase(m.name)}</dt>
                  <dd className="font-mono">{Number.isInteger(m.value) ? m.value : m.value.toFixed(3)}</dd>
                </React.Fragment>
              ))}
            </dl>
            {model.constraint_tags && model.constraint_tags.length > 0 && <p className="mt-3 text-xs text-muted-foreground">Constraint tags: {model.constraint_tags.join(", ")}</p>}
            {model.flags && model.flags.length > 0 && <p className="mt-1 text-xs text-warning">Flags: {model.flags.join(", ")}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Structural fingerprint</CardTitle><CardDescription>Hash {fp.hash} (schema v{fp.schema_version}). Bars show each component vector.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            {FP_KEYS.map((k) => (
              <div key={k}>
                <p className="mb-1 text-xs text-muted-foreground">{titleCase(k)}</p>
                <Sparkbars values={(fp[k] as number[]) ?? []} label={titleCase(k)} />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DnaPage() {
  return (
    <>
      <PageHeader title="Structural DNA" description="The extracted graph of your problem, its metrics and its fingerprint. Every node and edge carries its provenance." />
      <InvestigationScope stages={["structural_extraction", "structural_dna"]}>
        {({ outputs }) => <DnaBody extraction={outputs.structural_extraction.output!} dna={outputs.structural_dna.output!} />}
      </InvestigationScope>
    </>
  );
}
