"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { Select, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatDate } from "@/lib/format";
import type { Discovery, StageRecord } from "@/services/types";

/**
 * Shared header for pages that read the stage outputs of one investigation. The selection lives in the `run` query
 * parameter so links are shareable. `render` receives the stage lookup once the run is chosen.
 */
export function InvestigationScope({
  stages,
  children,
}: {
  stages: string[];
  children: (ctx: { id: string; discovery: Discovery; outputs: Record<string, StageRecord>; reload: () => void }) => React.ReactNode;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const selected = params.get("run");
  const list = useAsync(() => api.discoveries.list({ limit: 100 }), []);
  const problems = useAsync(() => api.problems.list({ limit: 100 }), []);
  const titleOf = (d: Discovery) => problems.data?.items.find((p) => p.id === d.problem_id)?.title ?? d.problem_id.slice(0, 8);

  if (list.loading) return <LoadingState />;
  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  const items = list.data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="No investigations yet"
        hint="Run a discovery first. This page shows the results of one run."
        action={
          <Link className="text-sm text-primary underline" href="/new">
            Start a new discovery
          </Link>
        }
      />
    );
  }
  const id = selected ?? items[0].id;
  const discovery = items.find((d) => d.id === id) ?? items[0];
  return (
    <div className="space-y-4">
      <div className="max-w-md">
        <Label htmlFor="run-select">Investigation</Label>
        <Select id="run-select" value={discovery.id} onChange={(e) => router.replace(`?run=${e.target.value}`)}>
          {items.map((d) => (
            <option key={d.id} value={d.id}>
              {titleOf(d)} ({d.status}, {formatDate(d.created_at)})
            </option>
          ))}
        </Select>
      </div>
      <ScopeBody id={discovery.id} discovery={discovery} stages={stages}>
        {children}
      </ScopeBody>
    </div>
  );
}

function ScopeBody({ id, discovery, stages, children }: { id: string; discovery: Discovery; stages: string[]; children: Parameters<typeof InvestigationScope>[0]["children"] }) {
  const res = useAsync(async () => {
    const out: Record<string, StageRecord> = {};
    await Promise.all(stages.map(async (s) => (out[s] = await api.discoveries.stage(id, s))));
    return out;
  }, [id, stages.join(",")]);
  if (res.loading) return <LoadingState />;
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  const outputs = res.data ?? {};
  const missing = stages.filter((s) => outputs[s]?.status !== "done" || !outputs[s]?.output);
  if (missing.length > 0) {
    return (
      <EmptyState
        title="Results are not ready"
        hint={`Stage ${missing.map((m) => `"${m}"`).join(", ")} has no output yet (status: ${outputs[missing[0]]?.status ?? "unknown"}). Open the investigation to follow progress.`}
        action={
          <Link className="text-sm text-primary underline" href={`/investigations/${id}`}>
            Open investigation
          </Link>
        }
      />
    );
  }
  return <>{children({ id, discovery, outputs, reload: res.reload })}</>;
}
