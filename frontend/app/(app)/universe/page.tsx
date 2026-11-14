"use client";
import * as React from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { InvestigationScope } from "@/components/investigation-picker";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, Label } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import { EmptyState, Unavailable } from "@/components/ui/states";
import { formatScore, titleCase } from "@/lib/format";
import type { StageMatch } from "@/services/types";

function UniverseBody({ search }: { search: { matches: StageMatch[]; excluded?: Array<{ system_id: string; reason: string }>; stage_counts?: Record<string, number>; notes?: string[] } }) {
  const [domain, setDomain] = React.useState("");
  const [openId, setOpenId] = React.useState<string | null>(null);
  const matches = search.matches ?? [];
  const domains = Array.from(new Set(matches.map((m) => m.domain)));
  const shown = matches.filter((m) => !domain || m.domain === domain);
  const open = matches.find((m) => m.id === openId);
  const points = shown.map((m) => ({ x: m.domain_distance, y: m.score, name: m.system_name }));

  if (matches.length === 0) return <EmptyState title="No matches" hint="No system passed the filters. Lower the minimum score or check the problem description." />;
  return (
    <div className="space-y-4">
      <div className="max-w-xs">
        <Label htmlFor="dom">Domain</Label>
        <Select id="dom" value={domain} onChange={(e) => setDomain(e.target.value)}>
          <option value="">All domains</option>
          {domains.map((d) => <option key={d}>{d}</option>)}
        </Select>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Score against domain distance</CardTitle>
          <CardDescription>Each point is one candidate system. Higher and further right means a strong match from a more distant domain.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-72" role="img" aria-label="Scatter chart of match score against domain distance">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                <CartesianGrid stroke="#2a2f3a" />
                <XAxis type="number" dataKey="x" name="Domain distance" domain={[0, 1]} stroke="#94a3b8" label={{ value: "Domain distance", position: "bottom", fill: "#94a3b8", fontSize: 12 }} />
                <YAxis type="number" dataKey="y" name="Score" domain={[0, 100]} stroke="#94a3b8" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "#14171f", border: "1px solid #2a2f3a" }} />
                <Scatter data={points} fill="#7c9cff" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
      <Card>
        <Table>
          <thead><tr><Th>System</Th><Th>Domain</Th><Th>Score</Th><Th>Distance</Th><Th>Details</Th></tr></thead>
          <tbody>
            {shown.map((m) => (
              <tr key={m.id}>
                <Td>{m.system_name}</Td><Td>{m.domain}</Td><Td>{formatScore(m.score)}</Td><Td>{formatScore(m.domain_distance, 2)}</Td>
                <Td><Button size="sm" variant="ghost" aria-expanded={openId === m.id} onClick={() => setOpenId(openId === m.id ? null : m.id)}>{openId === m.id ? "Hide" : "Show"}</Button></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      {open && (
        <Card>
          <CardHeader><CardTitle>{open.system_name}: score breakdown</CardTitle><CardDescription>Component scores range from 0 to 1 and are combined with the configured weights.</CardDescription></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {Object.entries(open.components).map(([k, v]) => (
                <div key={k} className="rounded-md border p-2"><p className="text-xs text-muted-foreground">{titleCase(k)}</p><p className="font-mono">{Number(v).toFixed(3)}</p></div>
              ))}
            </div>
            {open.differences?.length > 0 && <div><p className="font-medium">Differences</p><ul className="list-disc pl-5 text-muted-foreground">{open.differences.map((d, i) => <li key={i}>{d}</li>)}</ul></div>}
            {open.limitations?.length > 0 && <div><p className="font-medium">Limitations</p><ul className="list-disc pl-5 text-muted-foreground">{open.limitations.map((d, i) => <li key={i}>{d}</li>)}</ul></div>}
          </CardContent>
        </Card>
      )}
      {search.stage_counts && (
        <Card>
          <CardHeader><CardTitle>Search funnel</CardTitle><CardDescription>Number of systems left after each stage.</CardDescription></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {Object.entries(search.stage_counts).map(([k, v]) => <Badge key={k} tone="blue">{titleCase(k)}: {v}</Badge>)}
          </CardContent>
        </Card>
      )}
      {search.excluded && search.excluded.length > 0 && <p className="text-xs text-muted-foreground">{search.excluded.length} systems were excluded (for example same domain, or outside the retrieval cutoff).</p>}
      <Unavailable>The 3D universe view is not included in this version. The chart and tables above show the same data.</Unavailable>
    </div>
  );
}

export default function UniversePage() {
  return (
    <>
      <PageHeader title="Discovery Universe" description="Candidate systems from other domains, ranked by structural similarity to your problem." />
      <InvestigationScope stages={["structural_matching"]}>
        {({ outputs }) => <UniverseBody search={outputs.structural_matching.output as never} />}
      </InvestigationScope>
    </>
  );
}
