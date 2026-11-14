"use client";
import * as React from "react";
import { api, downloadText } from "@/services/api";
import { InvestigationScope } from "@/components/investigation-picker";
import { useAsync, useLocalState } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, ProvenanceBadge, StatusBadge } from "@/components/ui/badge";
import { Textarea, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState, errorMessage } from "@/components/ui/states";
import { MAX_COMPARE, hypothesesToMarkdown, toggleCompare, type Annotations, type Decision } from "@/lib/arena";
import type { HypothesisRecord, PersistedHypothesis } from "@/services/types";

function ArenaBody({ runId, hypotheses }: { runId: string; hypotheses: HypothesisRecord[] }) {
  const [compare, setCompare] = React.useState<string[]>([]);
  const [annotations, setAnnotations] = useLocalState<Annotations>(`isomorph.arena.${runId}`, {});
  const decide = (id: string, decision: Decision) => setAnnotations({ ...annotations, [id]: { note: annotations[id]?.note ?? "", decision } });
  const note = (id: string, text: string) => setAnnotations({ ...annotations, [id]: { decision: annotations[id]?.decision ?? "none", note: text } });
  const chosen = hypotheses.filter((h) => compare.includes(h.id));
  const withNotes = (list: HypothesisRecord[]) => list.map((h) => ({ ...h, annotation: annotations[h.id] }));

  if (hypotheses.length === 0) return <EmptyState title="No hypotheses" hint="No grounded concept produced a hypothesis for this run." />;
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Decisions and notes below are stored in this browser only. To keep a hypothesis on the server, use Save as hypothesis in the Transformation Studio.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={chosen.length === 0} onClick={() => downloadText("hypotheses.json", JSON.stringify(withNotes(chosen), null, 2), "application/json")}>
          Export selected (JSON)
        </Button>
        <Button size="sm" variant="secondary" disabled={chosen.length === 0} onClick={() => downloadText("hypotheses.md", hypothesesToMarkdown(withNotes(chosen)), "text/markdown")}>
          Export selected (Markdown)
        </Button>
        <span className="self-center text-xs text-muted-foreground" aria-live="polite">{compare.length} of {MAX_COMPARE} selected for comparison</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {hypotheses.map((h) => {
          const a = annotations[h.id];
          const checked = compare.includes(h.id);
          return (
            <Card key={h.id} className={a?.decision === "rejected" ? "opacity-60" : ""}>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="violet">{h.category}</Badge><StatusBadge status={h.status} /><ProvenanceBadge provenance={h.provenance} />
                  {a && a.decision !== "none" && <Badge tone={a.decision === "rejected" ? "danger" : "success"}>{a.decision}</Badge>}
                </div>
                <CardTitle className="font-normal leading-snug">{h.statement}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p><span className="font-medium">Prediction: </span>{h.prediction}</p>
                <p><span className="font-medium">Falsified if: </span>{h.falsifier}</p>
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={checked} disabled={!checked && compare.length >= MAX_COMPARE} onChange={() => setCompare(toggleCompare(compare, h.id))} />
                  Compare (max {MAX_COMPARE})
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" onClick={() => decide(h.id, "saved")}>Shortlist</Button>
                  <Button size="sm" variant="secondary" onClick={() => decide(h.id, "promoted")}>Promote</Button>
                  <Button size="sm" variant="secondary" onClick={() => decide(h.id, "rejected")}>Reject</Button>
                  <Button size="sm" variant="ghost" onClick={() => decide(h.id, "none")}>Clear</Button>
                </div>
                <div>
                  <Label htmlFor={`note-${h.id}`}>Notes</Label>
                  <Textarea id={`note-${h.id}`} rows={2} value={a?.note ?? ""} onChange={(e) => note(h.id, e.target.value)} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      {chosen.length >= 2 && (
        <Card>
          <CardHeader><CardTitle>Side by side</CardTitle><CardDescription>Comparing {chosen.length} hypotheses.</CardDescription></CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <caption className="sr-only">Hypothesis comparison</caption>
              <thead>
                <tr><th scope="col" className="p-2" />{chosen.map((h) => <th key={h.id} scope="col" className="p-2 text-xs text-muted-foreground">{h.id}</th>)}</tr>
              </thead>
              <tbody>
                {(["statement", "prediction", "falsifier", "category", "status", "provenance"] as const).map((row) => (
                  <tr key={row} className="border-t">
                    <th scope="row" className="p-2 align-top text-xs font-medium capitalize text-muted-foreground">{row}</th>
                    {chosen.map((h) => <td key={h.id} className="p-2 align-top">{h[row]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PersistedHypotheses() {
  const list = useAsync(() => api.pipeline.hypotheses({ limit: 100 }), []);
  const [editing, setEditing] = React.useState<PersistedHypothesis | null>(null);
  const [text, setText] = React.useState("");
  const [msg, setMsg] = React.useState<string | null>(null);

  async function save() {
    if (!editing) return;
    try {
      await api.pipeline.patchHypothesis(editing.id, { statement: text });
      setMsg("Saved. The hypothesis is now user authored and back to untested, because earlier evidence no longer applies.");
      setEditing(null);
      list.reload();
    } catch (e) {
      setMsg(errorMessage(e));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Saved on the server</CardTitle><CardDescription>Hypotheses you saved from the Transformation Studio.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {list.loading && <LoadingState rows={2} />}
        {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
        {list.data && list.data.items.length === 0 && <EmptyState title="Nothing saved yet" />}
        {list.data?.items.map((h) => (
          <div key={h.id} className="rounded-md border p-3 text-sm">
            <div className="mb-1 flex gap-2"><StatusBadge status={h.status} /><ProvenanceBadge provenance={h.provenance} /></div>
            <p>{h.statement}</p>
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => { setEditing(h); setText(h.statement); setMsg(null); }}>Modify statement</Button>
          </div>
        ))}
        {editing && (
          <div className="space-y-2">
            <Label htmlFor="edit-statement">Statement</Label>
            <Textarea id="edit-statement" value={text} onChange={(e) => setText(e.target.value)} />
            <div className="flex gap-2"><Button size="sm" disabled={!text.trim()} onClick={save}>Save change</Button><Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button></div>
          </div>
        )}
        {msg && <p role="status" className="text-sm text-muted-foreground">{msg}</p>}
      </CardContent>
    </Card>
  );
}

export default function HypothesesPage() {
  return (
    <>
      <PageHeader title="Hypothesis Arena" description="Compare up to three hypotheses, record your decisions and export them. Hypotheses are testable statements, not conclusions." />
      <div className="space-y-6">
        <InvestigationScope stages={["validation"]}>
          {({ id, outputs }) => <ArenaBody runId={id} hypotheses={((outputs.validation.output as { hypotheses?: HypothesisRecord[] }).hypotheses ?? [])} />}
        </InvestigationScope>
        <PersistedHypotheses />
      </div>
    </>
  );
}
