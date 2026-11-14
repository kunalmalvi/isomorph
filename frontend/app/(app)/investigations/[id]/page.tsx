"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CheckCircle2, Circle, Loader2, XCircle, AlertCircle } from "lucide-react";
import { api, downloadText } from "@/services/api";
import { useAsync, useDiscoveryProgress } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, ProvenanceBadge, StatusBadge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { Table, Td, Th } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingState, errorMessage } from "@/components/ui/states";
import { JsonView } from "@/components/json-view";
import { STAGE_ORDER, formatScore, isTerminal, parseJsonObject, titleCase } from "@/lib/format";

function StageIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-danger" aria-hidden />;
  if (status === "stale") return <AlertCircle className="h-4 w-4 text-warning" aria-hidden />;
  return <Circle className="h-4 w-4 text-muted-foreground" aria-hidden />;
}

export default function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const [restart, setRestart] = React.useState(0);
  const { progress, streamError } = useDiscoveryProgress(id, restart);
  const discovery = useAsync(() => api.discoveries.get(id), [id, progress?.status]);
  const problem = useAsync(async () => (discovery.data ? api.problems.get(discovery.data.problem_id) : null), [discovery.data?.problem_id]);
  const [selected, setSelected] = React.useState<string>("perception");
  const [tab, setTab] = React.useState("output");
  const stage = useAsync(() => api.discoveries.stage(id, selected), [id, selected, progress?.completed, progress?.status]);
  const matches = useAsync(() => api.discoveries.matches(id, { limit: 100 }), [id, progress?.status]);
  const [draft, setDraft] = React.useState("");
  const [message, setMessage] = React.useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = React.useState(false);

  const live = progress ?? discovery.data?.progress ?? null;
  const status = live?.status ?? discovery.data?.status ?? "queued";
  const running = status === "queued" || status === "running";
  const stageList = STAGE_ORDER.map((name) => live?.stages.find((s) => s.name === name) ?? { name, status: "pending", version: 0, source: "computation" });

  React.useEffect(() => {
    if (stage.data?.output) setDraft(JSON.stringify(stage.data.output, null, 2));
  }, [stage.data]);

  async function act(fn: () => Promise<unknown>, ok: string, restartStream = false) {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
      setMessage({ kind: "ok", text: ok });
      if (restartStream) setRestart((n) => n + 1);
      stage.reload();
      discovery.reload();
    } catch (e) {
      setMessage({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    const parsed = parseJsonObject(draft);
    if (!parsed.ok) return setMessage({ kind: "error", text: parsed.error });
    await act(() => api.discoveries.editStage(id, selected, parsed.value), "Stage output replaced. Later stages are now stale until you rerun them.");
  }

  async function exportReport(format: "md" | "json") {
    if (!discovery.data?.project_id) return;
    await act(async () => {
      const r = await api.reports.create({ project_id: discovery.data!.project_id!, discovery_session_id: id, title: problem.data?.title ?? `Investigation ${id.slice(0, 8)}` });
      const text = await api.reports.export(r.id, format);
      downloadText(`isomorph-report-${r.id}.${format}`, text, format === "md" ? "text/markdown" : "application/json");
    }, "Report created and downloaded.");
  }

  if (discovery.loading && !discovery.data) return <LoadingState rows={5} />;
  if (discovery.error) return <ErrorState error={discovery.error} onRetry={discovery.reload} />;

  return (
    <>
      <PageHeader
        title={problem.data?.title ?? `Investigation ${id.slice(0, 8)}`}
        description={problem.data?.statement?.slice(0, 240)}
        actions={
          <>
            <StatusBadge status={status} />
            {running && (
              <Button variant="danger" size="sm" disabled={busy} onClick={() => act(() => api.discoveries.cancel(id), "Cancellation requested.")}>
                Cancel run
              </Button>
            )}
            <Button variant="secondary" size="sm" disabled={busy || running} onClick={() => exportReport("md")}>
              Export report (Markdown)
            </Button>
            <Button variant="secondary" size="sm" disabled={busy || running} onClick={() => exportReport("json")}>
              Export report (JSON)
            </Button>
          </>
        }
      />
      {streamError && (
        <p role="status" className="mb-3 text-xs text-warning">
          Live updates unavailable: {streamError}. Reload the page to retry.
        </p>
      )}
      {discovery.data?.error && (
        <p role="alert" className="mb-3 text-sm text-danger">
          Run error: {discovery.data.error}
        </p>
      )}
      <p className="mb-3 text-xs text-muted-foreground" aria-live="polite">
        {live ? `${live.completed} of ${live.total} stages complete` : "Waiting for progress"}
      </p>
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
            <CardDescription>Status comes from the server event stream.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-1" aria-label="Pipeline stages">
              {stageList.map((s, i) => (
                <li key={s.name}>
                  <button
                    type="button"
                    onClick={() => setSelected(s.name)}
                    aria-current={selected === s.name ? "step" : undefined}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-muted ${selected === s.name ? "bg-muted" : ""}`}
                  >
                    <StageIcon status={s.status} />
                    <span className="flex-1">
                      {i + 1}. {titleCase(s.name)}
                    </span>
                    {s.version > 1 && <Badge title="Output version">v{s.version}</Badge>}
                    <span className="sr-only">{s.status}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <Link className="text-primary underline" href={`/dna?run=${id}`}>Structural DNA</Link>
              <Link className="text-primary underline" href={`/universe?run=${id}`}>Universe</Link>
              <Link className="text-primary underline" href={`/transformation?run=${id}`}>Transformations</Link>
              <Link className="text-primary underline" href={`/hypotheses?run=${id}`}>Hypotheses</Link>
              <Link className="text-primary underline" href={`/validation?run=${id}`}>Validation</Link>
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>{titleCase(selected)}</CardTitle>
                <CardDescription>
                  {stage.data ? `Version ${stage.data.version}` : ""} {stage.data?.error ? `| error: ${stage.data.error}` : ""}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {stage.data && <StatusBadge status={stage.data.status} />}
                {stage.data && <ProvenanceBadge provenance={stage.data.source} />}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <Tabs label="Stage view" value={tab} onChange={setTab} items={[{ id: "output", label: "Output" }, { id: "edit", label: "Edit and rerun" }]} />
              {stage.loading && !stage.data && <LoadingState rows={2} />}
              {stage.error ? <ErrorState error={stage.error} onRetry={stage.reload} /> : null}
              {stage.data && !stage.data.output && <EmptyState title="No output yet" hint={`This stage is ${stage.data.status}.`} />}
              {stage.data?.output && tab === "output" && <JsonView value={stage.data.output} className="max-h-[520px]" />}
              {stage.data?.output && tab === "edit" && (
                <div className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Replacing a stage output marks every later stage stale. The server validates the shape and rejects invalid edits. Edited output is labelled as user provenance.
                  </p>
                  <label htmlFor="stage-json" className="sr-only">Stage output JSON</label>
                  <Textarea id="stage-json" className="min-h-[320px] font-mono text-xs" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" disabled={busy || running} onClick={saveEdit}>Save edit</Button>
                    <Button size="sm" variant="secondary" disabled={busy || running} onClick={() => act(() => api.discoveries.rerun(id, selected, "downstream"), "Rerunning stages after this one.", true)}>
                      Rerun stages after this one
                    </Button>
                    <Button size="sm" variant="secondary" disabled={busy || running} onClick={() => act(() => api.discoveries.rerun(id, selected, "from"), "Rerunning this stage and everything after it.", true)}>
                      Recompute from this stage
                    </Button>
                  </div>
                </div>
              )}
              {message && (
                <p role={message.kind === "error" ? "alert" : "status"} className={`text-sm ${message.kind === "error" ? "text-danger" : "text-success"}`}>
                  {message.text}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Ranked matches</CardTitle>
              <CardDescription>Scores are heuristic structural similarity on a 0 to 100 scale, not probabilities.</CardDescription>
            </CardHeader>
            <CardContent>
              {matches.loading && <LoadingState rows={2} />}
              {matches.error ? <ErrorState error={matches.error} onRetry={matches.reload} /> : null}
              {matches.data && matches.data.items.length === 0 && <EmptyState title="No matches yet" hint={isTerminal(status) ? "No system passed the filters." : "Matching has not finished."} />}
              {matches.data && matches.data.items.length > 0 && (
                <Table>
                  <thead>
                    <tr>
                      <Th>Rank</Th>
                      <Th>System</Th>
                      <Th>Domain</Th>
                      <Th>Score</Th>
                      <Th>Domain distance</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.data.items.map((m) => (
                      <tr key={m.id}>
                        <Td>{m.rank}</Td>
                        <Td>{m.system_name ?? m.system_key}</Td>
                        <Td>{m.domain ?? "n/a"}</Td>
                        <Td>{formatScore(m.score)}</Td>
                        <Td>{formatScore(m.domain_distance, 2)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
