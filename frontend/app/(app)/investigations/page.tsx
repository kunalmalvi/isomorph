"use client";
import Link from "next/link";
import { api } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, Td, Th } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format";

export default function InvestigationsPage() {
  const list = useAsync(() => api.discoveries.list({ limit: 100 }), []);
  const problems = useAsync(() => api.problems.list({ limit: 100 }), []);
  return (
    <>
      <PageHeader title="My Investigations" description="Every discovery run you can access." actions={<Link href="/new"><Button>New discovery</Button></Link>} />
      {list.loading && <LoadingState />}
      {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
      {list.data && list.data.items.length === 0 && <EmptyState title="No investigations yet" hint="Start one from New Discovery." />}
      {list.data && list.data.items.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <Th>Problem</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th>Open</Th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((d) => (
                <tr key={d.id}>
                  <Td>{problems.data?.items.find((p) => p.id === d.problem_id)?.title ?? d.problem_id}</Td>
                  <Td><StatusBadge status={d.status} /></Td>
                  <Td className="text-xs text-muted-foreground">{formatDate(d.created_at)}</Td>
                  <Td><Link className="text-primary underline" href={`/investigations/${d.id}`}>Open</Link></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </>
  );
}
