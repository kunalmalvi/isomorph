"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { api } from "@/services/api";
import { useAsync } from "@/lib/hooks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { ErrorState, LoadingState, Unavailable, errorMessage } from "@/components/ui/states";
import { JsonView } from "@/components/json-view";
import { DEFAULT_WEIGHTS, WEIGHT_KEYS, titleCase, weightsTotal, weightsValid, type Weights } from "@/lib/format";
import type { Problem, UploadResult } from "@/services/types";

const ACCEPT = ".txt,.md,.csv,.pdf,.png,.jpg,.jpeg";

export default function NewDiscoveryPage() {
  const router = useRouter();
  const projects = useAsync(() => api.projects.list({ limit: 100 }), []);
  const saved = useAsync(() => api.settings.get().catch(() => null), []);
  const [mode, setMode] = React.useState("guided");
  const [projectId, setProjectId] = React.useState("");
  const [newProject, setNewProject] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [statement, setStatement] = React.useState("");
  const [goal, setGoal] = React.useState("");
  const [entities, setEntities] = React.useState("");
  const [constraints, setConstraints] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);
  const [weights, setWeights] = React.useState<Weights>({ ...DEFAULT_WEIGHTS });
  const [threshold, setThreshold] = React.useState("0");
  const [topK, setTopK] = React.useState("10");
  const [provider, setProvider] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [problem, setProblem] = React.useState<Problem | null>(null);
  const [uploads, setUploads] = React.useState<Array<UploadResult | { filename: string; error: string }>>([]);

  React.useEffect(() => {
    if (saved.data?.weights) setWeights({ ...DEFAULT_WEIGHTS, ...(saved.data.weights as Partial<Weights>) });
  }, [saved.data]);

  const items = projects.data?.items ?? [];
  const activeProject = projectId || items[0]?.id || "";
  const advancedOk = mode === "guided" || weightsValid(weights);

  async function saveProblem(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let pid = activeProject;
      if (!pid) {
        const p = await api.projects.create(newProject.trim() || "My investigations");
        pid = p.id;
      }
      const created = await api.problems.create({ project_id: pid, title: title.trim(), statement: statement.trim(), goal: goal.trim() || null });
      for (const line of entities.split("\n").map((l) => l.trim()).filter(Boolean)) {
        const [name, kind] = line.split("|").map((s) => s.trim());
        await api.problems.addEntity(created.id, { name, kind: kind || undefined });
      }
      for (const line of constraints.split("\n").map((l) => l.trim()).filter(Boolean)) {
        await api.problems.addConstraint(created.id, { description: line, kind: "hard" });
      }
      const results: typeof uploads = [];
      for (const f of files) {
        try {
          results.push(await api.problems.upload(created.id, f));
        } catch (err) {
          results.push({ filename: f.name, error: errorMessage(err) });
        }
      }
      setUploads(results);
      setProblem(created);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!problem) return;
    setBusy(true);
    setError(null);
    try {
      const body: Parameters<typeof api.discoveries.create>[0] = { problem_id: problem.id };
      if (mode === "advanced") {
        body.weights = weights;
        body.threshold = Number(threshold) || 0;
        body.top_k = Number(topK) || 10;
        body.provider = provider || null;
      }
      const d = await api.discoveries.create(body);
      router.push(`/investigations/${d.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  if (projects.loading) return <LoadingState />;
  if (projects.error) return <ErrorState error={projects.error} onRetry={projects.reload} />;

  return (
    <>
      <PageHeader title="New Discovery" description="Describe a problem in plain language. ISOMORPH extracts its structure and searches other domains for systems with a similar structure." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <form onSubmit={saveProblem} className="space-y-4" aria-label="Problem description">
          <Tabs label="Input mode" value={mode} onChange={setMode} items={[{ id: "guided", label: "Guided" }, { id: "advanced", label: "Advanced" }]} />
          <Card>
            <CardContent className="space-y-4 pt-4">
              {items.length > 0 ? (
                <div>
                  <Label htmlFor="project">Project</Label>
                  <Select id="project" value={activeProject} onChange={(e) => setProjectId(e.target.value)} disabled={!!problem}>
                    {items.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : (
                <div>
                  <Label htmlFor="newproject">Project name (a project is created for you)</Label>
                  <Input id="newproject" value={newProject} onChange={(e) => setNewProject(e.target.value)} placeholder="My investigations" disabled={!!problem} />
                </div>
              )}
              <div>
                <Label htmlFor="title">Title</Label>
                <Input id="title" required maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} disabled={!!problem} />
              </div>
              <div>
                <Label htmlFor="statement">Problem statement</Label>
                <Textarea
                  id="statement"
                  required
                  rows={6}
                  maxLength={20000}
                  value={statement}
                  onChange={(e) => setStatement(e.target.value)}
                  disabled={!!problem}
                  placeholder="Describe what the system does, what it is made of, what must not be violated, and what you want to improve."
                />
              </div>
              <div>
                <Label htmlFor="goal">Goal (optional)</Label>
                <Input id="goal" maxLength={5000} value={goal} onChange={(e) => setGoal(e.target.value)} disabled={!!problem} />
              </div>
              {mode === "guided" && (
                <>
                  <div>
                    <Label htmlFor="entities">Known components (optional, one per line, as name | kind)</Label>
                    <Textarea id="entities" rows={3} value={entities} onChange={(e) => setEntities(e.target.value)} disabled={!!problem} placeholder={"roller | component\nstrip | material"} />
                  </div>
                  <div>
                    <Label htmlFor="constraints">Hard constraints (optional, one per line)</Label>
                    <Textarea id="constraints" rows={3} value={constraints} onChange={(e) => setConstraints(e.target.value)} disabled={!!problem} placeholder="Roll force must not exceed 90 kN" />
                  </div>
                </>
              )}
              <div>
                <Label htmlFor="files">Files (optional)</Label>
                <Input id="files" type="file" multiple accept={ACCEPT} disabled={!!problem} onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
                <p className="mt-1 text-xs text-muted-foreground">
                  Text, Markdown and CSV files are read and a proposed structure is shown for your review. Nothing is stored from a file automatically.
                </p>
              </div>
              <Unavailable>
                PDF and image files are validated and accepted, but their content is not interpreted in this version (no OCR or vision dependency). Describe them in the statement instead.
              </Unavailable>
              {!problem && (
                <Button type="submit" disabled={busy || !title.trim() || !statement.trim()}>
                  {busy ? "Saving..." : "Save problem"}
                </Button>
              )}
            </CardContent>
          </Card>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </form>

        <div className="space-y-4">
          {mode === "advanced" && (
            <Card>
              <CardHeader>
                <CardTitle>Scoring weights</CardTitle>
                <CardDescription>Must total 100. Starts from your saved defaults (built-in 25/25/20/15/10/5).</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {WEIGHT_KEYS.map((k) => (
                  <div key={k} className="flex items-center gap-2">
                    <Label htmlFor={`w-${k}`} className="mb-0 w-28">
                      {titleCase(k)}
                    </Label>
                    <Input id={`w-${k}`} type="number" min={0} max={100} step={1} value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
                  </div>
                ))}
                <p className={weightsValid(weights) ? "text-xs text-success" : "text-xs text-danger"} role="status">
                  Total {weightsTotal(weights)} {weightsValid(weights) ? "" : "(must be 100)"}
                </p>
                <div>
                  <Label htmlFor="threshold">Minimum score (0 to 100)</Label>
                  <Input id="threshold" type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="topk">Matches to keep</Label>
                  <Input id="topk" type="number" min={1} max={100} value={topK} onChange={(e) => setTopK(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="provider">AI provider for perception</Label>
                  <Select id="provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
                    <option value="">Server default</option>
                    <option value="local">local (deterministic)</option>
                    <option value="openai">openai</option>
                    <option value="gemini">gemini</option>
                    <option value="anthropic">anthropic</option>
                  </Select>
                  <p className="mt-1 text-xs text-muted-foreground">A remote provider without a configured key makes the run fail visibly. There is no silent fallback.</p>
                </div>
              </CardContent>
            </Card>
          )}
          {problem && (
            <Card>
              <CardHeader>
                <CardTitle>Problem saved</CardTitle>
                <CardDescription>{problem.title}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {uploads.map((u, i) => (
                  <div key={i} className="space-y-1 text-xs">
                    <p className="font-medium">{u.filename}</p>
                    {"error" in u ? (
                      <p className="text-danger">{u.error}</p>
                    ) : u.processed ? (
                      <>
                        <p className="text-muted-foreground">Proposed structure (review only):</p>
                        <JsonView value={u.proposal} className="max-h-48" />
                      </>
                    ) : (
                      <p className="text-warning">{u.reason ?? "Validated, not interpreted."}</p>
                    )}
                  </div>
                ))}
                <Button onClick={start} disabled={busy || !advancedOk}>
                  {busy ? "Starting..." : "Start discovery"}
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
