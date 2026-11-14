"use client";
import * as React from "react";
import { api, downloadText } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState, errorMessage } from "@/components/ui/states";
import { formatDate } from "@/lib/format";

export default function ArchivePage() {
  const archived = useAsync(() => api.archive.list({ limit: 100 }), []);
  const projects = useAsync(() => api.projects.list({ limit: 100 }), []);
  const reports = useAsync(() => api.reports.list({ limit: 100 }), []);
  const [msg, setMsg] = React.useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try {
      await fn();
      setMsg({ kind: "ok", text: ok });
      archived.reload();
      projects.reload();
    } catch (e) {
      setMsg({ kind: "error", text: errorMessage(e) });
    }
  }

  async function exportReport(id: string, format: "md" | "json") {
    try {
      downloadText(`isomorph-report-${id}.${format}`, await api.reports.export(id, format), format === "md" ? "text/markdown" : "application/json");
    } catch (e) {
      setMsg({ kind: "error", text: errorMessage(e) });
    }
  }

  const active = (projects.data?.items ?? []).filter((p) => !p.archived_at);
  return (
    <>
      <PageHeader title="Discovery Archive" description="Archive finished projects, restore them later and download reports." />
      {msg && <p role={msg.kind === "error" ? "alert" : "status"} className={`mb-3 text-sm ${msg.kind === "error" ? "text-danger" : "text-success"}`}>{msg.text}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Active projects</CardTitle><CardDescription>Only the owner can archive a project.</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {projects.loading && <LoadingState rows={2} />}
            {projects.error ? <ErrorState error={projects.error} onRetry={projects.reload} /> : null}
            {projects.data && active.length === 0 && <EmptyState title="No active projects" />}
            {active.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 rounded-md border p-3 text-sm">
                <span>{p.name} {p.role && <Badge>{p.role}</Badge>}</span>
                <Button size="sm" variant="secondary" disabled={p.role !== undefined && p.role !== null && p.role !== "owner"} title={p.role && p.role !== "owner" ? "Only owners can archive" : undefined} onClick={() => run(() => api.archive.archive(p.id), `Archived ${p.name}.`)}>Archive</Button>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Archived projects</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {archived.loading && <LoadingState rows={2} />}
            {archived.error ? <ErrorState error={archived.error} onRetry={archived.reload} /> : null}
            {archived.data && archived.data.items.length === 0 && <EmptyState title="Nothing archived" />}
            {archived.data?.items.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 rounded-md border p-3 text-sm">
                <span>{p.name}<span className="block text-xs text-muted-foreground">Archived {formatDate(p.archived_at)}</span></span>
                <Button size="sm" variant="secondary" onClick={() => run(() => api.archive.restore(p.id), `Restored ${p.name}.`)}>Restore</Button>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Reports</CardTitle><CardDescription>Create reports from an investigation page.</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {reports.loading && <LoadingState rows={2} />}
            {reports.error ? <ErrorState error={reports.error} onRetry={reports.reload} /> : null}
            {reports.data && reports.data.items.length === 0 && <EmptyState title="No reports yet" hint="Open an investigation and use Export report." />}
            {reports.data?.items.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
                <span>{r.title}<span className="block text-xs text-muted-foreground">{formatDate(r.created_at)}</span></span>
                <span className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => exportReport(r.id, "md")}>Markdown</Button><Button size="sm" variant="secondary" onClick={() => exportReport(r.id, "json")}>JSON</Button></span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
