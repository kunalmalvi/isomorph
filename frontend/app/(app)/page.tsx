"use client";
import Link from "next/link";
import { api } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/states";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";

async function loadOverview() {
  const [projects, discoveries, hypotheses, reports, domains, systems, mechanisms, recent] = await Promise.all([
    api.projects.list({ limit: 1 }),
    api.discoveries.list({ limit: 1 }),
    api.pipeline.hypotheses({ limit: 1 }),
    api.reports.list({ limit: 1 }),
    api.knowledge.domains({ limit: 1 }),
    api.knowledge.systems({ limit: 1 }),
    api.knowledge.mechanisms({ limit: 1 }),
    api.discoveries.list({ limit: 5 }),
  ]);
  return { counts: { projects, discoveries, hypotheses, reports, domains, systems, mechanisms }, recent };
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useAsync(loadOverview, []);
  return (
    <>
      <PageHeader
        title="Overview"
        description="Totals below are read from the API. ISOMORPH produces hypotheses from structural analogies, not proven designs."
        actions={
          <Link href="/new">
            <Button>New discovery</Button>
          </Link>
        }
      />
      {loading && <LoadingState rows={4} />}
      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {data && (
        <div className="space-y-6">
          <section aria-label="Totals" className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {(
              [
                ["Projects", data.counts.projects.total],
                ["Investigations", data.counts.discoveries.total],
                ["Saved hypotheses", data.counts.hypotheses.total],
                ["Reports", data.counts.reports.total],
                ["Domains", data.counts.domains.total],
                ["Knowledge systems", data.counts.systems.total],
                ["Mechanisms", data.counts.mechanisms.total],
              ] as Array<[string, number]>
            ).map(([label, value]) => (
              <Card key={label}>
                <CardHeader>
                  <CardDescription>{label}</CardDescription>
                  <CardTitle className="text-2xl">{value}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </section>
          <Card>
            <CardHeader>
              <CardTitle>Recent investigations</CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent.items.length === 0 ? (
                <EmptyState title="No investigations yet" hint="Describe a problem to find structurally similar systems in other domains." />
              ) : (
                <ul className="divide-y">
                  {data.recent.items.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <Link href={`/investigations/${d.id}`} className="text-primary hover:underline">
                        {d.id.slice(0, 8)}
                      </Link>
                      <span className="text-xs text-muted-foreground">{formatDate(d.created_at)}</span>
                      <StatusBadge status={d.status} />
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
