"use client";
import * as React from "react";
import { api } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { GraphView } from "@/components/graph/graph-view";
import type { SystemSummary } from "@/services/types";

function SystemDialog({ system, onClose }: { system: SystemSummary | null; onClose: () => void }) {
  const graph = useAsync(async () => (system ? api.knowledge.systemGraph(system.id) : null), [system?.id]);
  return (
    <Dialog open={!!system} onClose={onClose} title={system?.name ?? "System"}>
      {system && (
        <div className="space-y-3 text-sm">
          <p>{system.summary}</p>
          <p className="text-xs text-muted-foreground">Domain {system.domain}, kind {system.kind}, {system.node_count} nodes, {system.edge_count} edges, confidence {String(system.confidence ?? "n/a")}.</p>
          {graph.loading && <LoadingState rows={2} />}
          {graph.error ? <ErrorState error={graph.error} onRetry={graph.reload} /> : null}
          {graph.data && <GraphView graph={graph.data} height={300} label={`Graph of ${system.name}`} />}
          {system.sources.length > 0 && <p className="text-xs text-muted-foreground">Sources: {system.sources.map((s) => (typeof s === "string" ? s : JSON.stringify(s))).join("; ")}</p>}
        </div>
      )}
    </Dialog>
  );
}

export default function LibraryPage() {
  const [tab, setTab] = React.useState("systems");
  const [q, setQ] = React.useState("");
  const [domain, setDomain] = React.useState("");
  const [open, setOpen] = React.useState<SystemSummary | null>(null);
  const domains = useAsync(() => api.knowledge.domains(), []);
  const systems = useAsync(() => api.knowledge.systems({ q, domain }), [q, domain]);
  const mechanisms = useAsync(() => api.knowledge.mechanisms({ domain }), [domain]);
  const list = tab === "mechanisms" ? mechanisms : systems;

  return (
    <>
      <PageHeader title="Knowledge Library" description="The curated seed knowledge ISOMORPH searches. Entries are simplified models with their sources, not complete references." />
      <div className="space-y-4">
        <Tabs label="Library section" value={tab} onChange={setTab} items={[{ id: "domains", label: "Domains" }, { id: "systems", label: "Systems" }, { id: "mechanisms", label: "Mechanisms" }]} />
        {tab !== "domains" && (
          <div className="flex flex-wrap gap-3">
            {tab === "systems" && <div><Label htmlFor="lib-q">Search</Label><Input id="lib-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="feedback" /></div>}
            <div><Label htmlFor="lib-domain">Domain</Label>
              <Select id="lib-domain" value={domain} onChange={(e) => setDomain(e.target.value)}>
                <option value="">All</option>
                {domains.data?.items.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
            </div>
          </div>
        )}
        {tab === "domains" && (
          <>
            {domains.loading && <LoadingState />}
            {domains.error ? <ErrorState error={domains.error} onRetry={domains.reload} /> : null}
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {domains.data?.items.map((d) => (
                <Card key={d.id}>
                  <CardHeader><CardTitle>{d.name}</CardTitle><CardDescription>{d.family}, {d.system_count} systems</CardDescription></CardHeader>
                  <CardContent className="space-y-2 text-sm"><p>{d.description}</p>
                    <Button size="sm" variant="secondary" onClick={() => { setDomain(d.id); setTab("systems"); }}>Browse systems</Button></CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
        {tab !== "domains" && (
          <>
            {list.loading && <LoadingState />}
            {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
            {list.data && list.data.items.length === 0 && <EmptyState title="Nothing matches" hint="Clear the search or the domain filter." />}
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {list.data?.items.map((s) => (
                <Card key={s.id}>
                  <CardHeader><div className="flex items-start justify-between gap-2"><CardTitle>{s.name}</CardTitle><Badge tone="cyan">{s.domain}</Badge></div></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <p className="line-clamp-3 text-muted-foreground">{s.summary}</p>
                    <p className="text-xs text-muted-foreground">{s.node_count} nodes, {s.edge_count} edges</p>
                    <Button size="sm" variant="secondary" onClick={() => setOpen(s)}>View graph</Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
      <SystemDialog system={open} onClose={() => setOpen(null)} />
    </>
  );
}
