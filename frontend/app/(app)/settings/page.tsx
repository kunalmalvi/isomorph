"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { API_URL, api, tokenStore } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, ProvenanceBadge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { ErrorState, LoadingState, errorMessage } from "@/components/ui/states";
import { DEFAULT_WEIGHTS, WEIGHT_KEYS, titleCase, weightsTotal, weightsValid, type Weights } from "@/lib/format";

export default function SettingsPage() {
  const router = useRouter();
  const me = useAsync(() => api.auth.me(), []);
  const settings = useAsync(() => api.settings.get(), []);
  const providers = useAsync(() => api.settings.providers(), []);
  const [weights, setWeights] = React.useState<Weights>({ ...DEFAULT_WEIGHTS });
  const [msg, setMsg] = React.useState<{ kind: "ok" | "error"; text: string } | null>(null);

  React.useEffect(() => {
    if (settings.data) setWeights({ ...DEFAULT_WEIGHTS, ...(settings.data.weights as Partial<Weights>) });
  }, [settings.data]);

  async function save() {
    try {
      await api.settings.setWeights(weights);
      setMsg({ kind: "ok", text: "Default weights saved." });
      settings.reload();
    } catch (e) {
      setMsg({ kind: "error", text: errorMessage(e) });
    }
  }

  return (
    <>
      <PageHeader title="Settings" description="AI providers, default scoring weights and your account." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Account</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {me.loading && <LoadingState rows={1} />}
            {me.error ? <ErrorState error={me.error} onRetry={me.reload} /> : null}
            {me.data && <p>{me.data.display_name ?? me.data.email} <span className="text-muted-foreground">({me.data.email})</span></p>}
            <p className="text-xs text-muted-foreground">API: <span className="font-mono">{API_URL}</span></p>
            <Button variant="secondary" size="sm" onClick={() => { tokenStore.clear(); router.replace("/login"); }}>Sign out</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>AI providers</CardTitle><CardDescription>Keys are configured on the server through environment variables and are never shown here. Default: {settings.data?.default_provider ?? "..."}.</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {providers.loading && <LoadingState rows={2} />}
            {providers.error ? <ErrorState error={providers.error} onRetry={providers.reload} /> : null}
            {providers.data?.providers.map((p) => (
              <div key={p.name} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <span className="font-medium">{p.name}</span>
                <span className="flex items-center gap-2">
                  {Boolean(p.default) && <Badge tone="blue">default</Badge>}
                  <Badge tone={p.configured ? "success" : "neutral"}>{p.configured ? "configured" : "no key"}</Badge>
                  {typeof p.provenance === "string" && <ProvenanceBadge provenance={p.provenance} />}
                </span>
                {typeof p.note === "string" && <span className="w-full text-xs text-muted-foreground">{p.note}</span>}
              </div>
            ))}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Default scoring weights</CardTitle><CardDescription>Used for your new discoveries unless overridden. Must total 100.{settings.data?.weights_are_default ? " Currently the built-in default." : ""}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              {WEIGHT_KEYS.map((k) => (
                <div key={k}><Label htmlFor={`s-${k}`}>{titleCase(k)}</Label><Input id={`s-${k}`} type="number" min={0} max={100} value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} /></div>
              ))}
            </div>
            <p role="status" className={weightsValid(weights) ? "text-xs text-success" : "text-xs text-danger"}>Total {weightsTotal(weights)} {weightsValid(weights) ? "" : "(must be 100)"}</p>
            <div className="flex gap-2">
              <Button size="sm" disabled={!weightsValid(weights)} onClick={save}>Save weights</Button>
              <Button size="sm" variant="ghost" onClick={() => setWeights({ ...DEFAULT_WEIGHTS })}>Reset to 25/25/20/15/10/5</Button>
            </div>
            {msg && <p role={msg.kind === "error" ? "alert" : "status"} className={`text-sm ${msg.kind === "error" ? "text-danger" : "text-success"}`}>{msg.text}</p>}
            <p className="text-xs text-muted-foreground">Advanced mode on New Discovery starts from these weights and sends them with the run. Guided mode uses the built-in defaults, because the server does not apply saved weights on its own.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
