"use client";
import * as React from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/services/api";
import { InvestigationScope } from "@/components/investigation-picker";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState, errorMessage } from "@/components/ui/states";
import { JsonView } from "@/components/json-view";
import { titleCase } from "@/lib/format";
import type { HypothesisRecord, ValidationEntry } from "@/services/types";

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function EvidenceCard({ entry, hypothesis }: { entry: ValidationEntry; hypothesis?: HypothesisRecord }) {
  const ev = entry.evidence;
  const baseline = num(ev.baseline_mean);
  const proposed = num(ev.proposed_mean);
  const chart = baseline !== null && proposed !== null ? [{ name: "Baseline", value: baseline }, { name: "Proposed", value: proposed }] : null;
  const stats: Array<[string, unknown]> = [
    ["Metric", ev.metric], ["Direction", ev.direction], ["Seeds", ev.n], ["Win rate", num(ev.win_rate) !== null ? (ev.win_rate as number).toFixed(2) : undefined],
    ["Mean relative improvement", num(ev.mean_relative_improvement) !== null ? (ev.mean_relative_improvement as number).toFixed(4) : undefined],
    ["95% CI half width", num(ev.ci95_half_width) !== null ? (ev.ci95_half_width as number).toFixed(4) : undefined],
  ];
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2"><CardTitle className="font-normal">{hypothesis?.statement ?? entry.hypothesis_id}</CardTitle><StatusBadge status={entry.outcome} /></div>
        <CardDescription>Method: {entry.method}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {chart ? (
          <div className="h-44" role="img" aria-label={`Baseline mean ${baseline} against proposed mean ${proposed}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart}>
                <CartesianGrid stroke="#2a2f3a" vertical={false} />
                <XAxis dataKey="name" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip contentStyle={{ background: "#14171f", border: "1px solid #2a2f3a" }} />
                <Bar dataKey="value" fill="#7c9cff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-muted-foreground">No numeric evidence: {String(ev.reason ?? "this hypothesis has no applicable experiment")}. Outcome stays untested.</p>
        )}
        {chart && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
            {stats.filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => (<React.Fragment key={k}><dt className="text-muted-foreground">{k}</dt><dd className="font-mono">{String(v)}</dd></React.Fragment>))}
          </dl>
        )}
        <p className="rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">{entry.caveats}</p>
      </CardContent>
    </Card>
  );
}

function RunServerValidation() {
  const hyps = useAsync(() => api.pipeline.hypotheses({ limit: 100 }), []);
  const records = useAsync(() => api.pipeline.validations(undefined, { limit: 100 }), []);
  const [seeds, setSeeds] = React.useState("20");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);

  async function run(id: string) {
    setBusy(id);
    setMsg(null);
    try {
      const n = Math.min(Math.max(Number(seeds) || 20, 1), 200);
      const r = await api.pipeline.validate(id, n);
      setMsg(`Validation finished with outcome ${r.outcome}.`);
      hyps.reload();
      records.reload();
    } catch (e) {
      setMsg(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Validate saved hypotheses</CardTitle><CardDescription>Runs a seeded simulation on the server and stores the result.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <div className="max-w-[160px]"><Label htmlFor="seeds">Seeds (1 to 200)</Label><Input id="seeds" type="number" min={1} max={200} value={seeds} onChange={(e) => setSeeds(e.target.value)} /></div>
        {hyps.loading && <LoadingState rows={2} />}
        {hyps.error ? <ErrorState error={hyps.error} onRetry={hyps.reload} /> : null}
        {hyps.data && hyps.data.items.length === 0 && <EmptyState title="No saved hypotheses" hint="Save one from the Transformation Studio first." />}
        {hyps.data?.items.map((h) => (
          <div key={h.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
            <span className="min-w-0 flex-1">{h.statement}</span>
            <StatusBadge status={h.status} />
            <Button size="sm" disabled={busy === h.id || !h.experiment} title={!h.experiment ? "No applicable experiment model" : undefined} onClick={() => run(h.id)}>{busy === h.id ? "Running..." : "Run validation"}</Button>
          </div>
        ))}
        {msg && <p role="status" className="text-sm">{msg}</p>}
        {records.data && records.data.items.length > 0 && (
          <div><p className="mb-1 text-xs font-medium text-muted-foreground">Stored validation records</p>
            <ul className="space-y-1 text-xs">{records.data.items.map((r) => (<li key={r.id} className="flex gap-2"><StatusBadge status={r.outcome} /><span className="text-muted-foreground">{r.method}</span></li>))}</ul></div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ValidationPage() {
  return (
    <>
      <PageHeader title="Validation Lab" description="Outcomes come from seeded simulation under stated assumptions. They are not real world evidence." />
      <div className="space-y-6">
        <InvestigationScope stages={["validation"]}>
          {({ outputs }) => {
            const out = outputs.validation.output as { validations?: ValidationEntry[]; hypotheses?: HypothesisRecord[]; note?: string };
            const vals = out.validations ?? [];
            if (vals.length === 0) return <EmptyState title="No validations" />;
            return (
              <div className="space-y-3">
                {out.note && <p className="text-xs text-muted-foreground">{out.note}</p>}
                <div className="grid gap-4 xl:grid-cols-2">
                  {vals.map((v) => <EvidenceCard key={v.hypothesis_id} entry={v} hypothesis={out.hypotheses?.find((h) => h.id === v.hypothesis_id)} />)}
                </div>
                <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">Raw evidence ({titleCase("json")})</summary><JsonView value={vals} /></details>
              </div>
            );
          }}
        </InvestigationScope>
        <RunServerValidation />
      </div>
    </>
  );
}
