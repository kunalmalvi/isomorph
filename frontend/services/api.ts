import type {
  DbMatch, Discovery, Domain, Page, PersistedHypothesis, Problem, Project, ProviderStatus, Report, SettingsOut,
  ServerAnnotation, StageRecord, SystemSummary, TokenOut, UploadResult, User, ValidationRecordOut, Graph,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "isomorph.token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: unknown[] = []) {
    super(message);
    this.name = "ApiError";
  }
}

export const tokenStore = {
  get(): string | null {
    return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
  },
  set(token: string): void {
    window.localStorage.setItem(TOKEN_KEY, token);
  },
  clear(): void {
    window.localStorage.removeItem(TOKEN_KEY);
  },
};

/** Turn a failed response body into an ApiError using the backend error envelope. */
export function toApiError(status: number, body: unknown): ApiError {
  const env = (body as { error?: { code?: string; message?: string; details?: unknown[] } } | null)?.error;
  return new ApiError(status, env?.code ?? "http_error", env?.message ?? `Request failed with status ${status}`, env?.details ?? []);
}

export function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown, init: { form?: FormData; raw?: boolean } = {}): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (init.form) payload = init.form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { method, headers, body: payload, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    tokenStore.clear();
    if (!window.location.pathname.startsWith("/login")) window.location.assign("/login");
  }
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* non JSON error */
    }
    throw toApiError(res.status, parsed);
  }
  if (res.status === 204) return undefined as T;
  if (init.raw) return (await res.text()) as T;
  return (await res.json()) as T;
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const patch = <T,>(p: string, b: unknown) => request<T>("PATCH", p, b);
const put = <T,>(p: string, b: unknown) => request<T>("PUT", p, b);

export interface Paging {
  limit?: number;
  offset?: number;
}

export const api = {
  auth: {
    register: (email: string, password: string, display_name?: string) =>
      post<TokenOut>("/auth/register", { email, password, display_name: display_name || null }),
    login: (email: string, password: string) => post<TokenOut>("/auth/login", { email, password }),
    me: () => get<User>("/auth/me"),
  },
  projects: {
    list: (p: Paging = {}) => get<Page<Project>>(`/projects${buildQuery({ ...p })}`),
    create: (name: string, description?: string) => post<Project>("/projects", { name, description: description || null }),
  },
  problems: {
    list: (p: Paging = {}) => get<Page<Problem>>(`/problems${buildQuery({ ...p })}`),
    get: (id: string) => get<Problem>(`/problems/${id}`),
    create: (b: { project_id: string; title: string; statement: string; goal?: string | null }) => post<Problem>("/problems", b),
    addEntity: (id: string, b: { name: string; kind?: string; description?: string }) => post(`/problems/${id}/entities`, b),
    addConstraint: (id: string, b: { description: string; kind: "hard" | "soft" }) => post(`/problems/${id}/constraints`, b),
    upload: (id: string, file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<UploadResult>("POST", `/problems/${id}/uploads`, undefined, { form });
    },
  },
  discoveries: {
    list: (p: Paging & { problem_id?: string } = {}) => get<Page<Discovery>>(`/discoveries${buildQuery({ ...p })}`),
    get: (id: string) => get<Discovery>(`/discoveries/${id}`),
    create: (b: { problem_id: string; weights?: Record<string, number> | null; threshold?: number | null; top_k?: number; provider?: string | null }) =>
      post<{ id: string; status: string }>("/discoveries", b),
    cancel: (id: string) => post<{ id: string; status: string }>(`/discoveries/${id}/cancel`),
    matches: (id: string, p: Paging = {}) => get<Page<DbMatch>>(`/discoveries/${id}/matches${buildQuery({ ...p })}`),
    stages: (id: string) => get<{ stages: StageRecord[]; order: string[] }>(`/discoveries/${id}/stages`),
    stage: (id: string, stage: string) => get<StageRecord>(`/discoveries/${id}/stages/${stage}`),
    editStage: (id: string, stage: string, output: Record<string, unknown>) => put(`/discoveries/${id}/stages/${stage}`, { output }),
    rerun: (id: string, stage: string, mode: "downstream" | "from") =>
      post<{ id: string; status: string }>(`/discoveries/${id}/stages/${stage}/rerun${buildQuery({ mode })}`),
    annotations: (id: string) => get<{ items: Record<string, ServerAnnotation> }>(`/discoveries/${id}/annotations`),
    putAnnotation: (id: string, hypothesisId: string, b: { decision: string; note: string }) =>
      put<ServerAnnotation>(`/discoveries/${id}/annotations/${encodeURIComponent(hypothesisId)}`, b),
    eventsUrl: (id: string) => `${API_URL}/discoveries/${id}/events`,
  },
  structural: {
    graph: (modelId: string) => get<{ graph: Graph }>(`/structural-models/${modelId}/graph`),
  },
  knowledge: {
    domains: (p: Paging = {}) => get<Page<Domain>>(`/domains${buildQuery({ limit: 100, ...p })}`),
    systems: (q: { domain?: string; q?: string } & Paging = {}) => get<Page<SystemSummary>>(`/knowledge-systems${buildQuery({ limit: 100, ...q })}`),
    system: (id: string) => get<Record<string, unknown>>(`/knowledge-systems/${id}`),
    systemGraph: (id: string) => get<Graph>(`/knowledge-systems/${id}/graph`),
    mechanisms: (q: { domain?: string } & Paging = {}) => get<Page<SystemSummary>>(`/mechanisms${buildQuery({ limit: 100, ...q })}`),
  },
  pipeline: {
    createMapping: (match_id: string) => post<{ id: string }>("/mappings", { match_id }),
    createTransformation: (mapping_id: string, concept_type?: string) =>
      post<{ id: string; available_concept_types?: string[] }>("/transformations", { mapping_id, concept_type: concept_type ?? null }),
    createHypothesis: (transformation_id: string) => post<PersistedHypothesis>("/hypotheses", { transformation_id }),
    hypotheses: (p: Paging = {}) => get<Page<PersistedHypothesis>>(`/hypotheses${buildQuery({ ...p })}`),
    patchHypothesis: (id: string, b: { statement?: string; prediction?: string; falsifier?: string }) => patch<PersistedHypothesis>(`/hypotheses/${id}`, b),
    validate: (hypothesis_id: string, seeds: number) => post<ValidationRecordOut>("/validation", { hypothesis_id, seeds }),
    validations: (hypothesis_id?: string, p: Paging = {}) => get<Page<ValidationRecordOut>>(`/validation${buildQuery({ hypothesis_id, ...p })}`),
  },
  archive: {
    list: (p: Paging = {}) => get<Page<Project>>(`/archive${buildQuery({ ...p })}`),
    archive: (projectId: string) => post<Project>(`/archive/${projectId}`),
    restore: (projectId: string) => post<Project>(`/archive/${projectId}/restore`),
  },
  reports: {
    list: (p: Paging & { project_id?: string } = {}) => get<Page<Report>>(`/reports${buildQuery({ ...p })}`),
    create: (b: { project_id: string; discovery_session_id: string; title: string }) => post<Report>("/reports", b),
    export: (id: string, format: "md" | "json") => request<string>("GET", `/reports/${id}/export${buildQuery({ format })}`, undefined, { raw: true }),
  },
  settings: {
    get: () => get<SettingsOut>("/settings"),
    patch: (preferences: Record<string, unknown>) => patch<SettingsOut>("/settings", { preferences }),
    providers: () => get<{ providers: ProviderStatus[] }>("/settings/providers"),
    setWeights: (weights: Record<string, number>) => patch<SettingsOut>("/settings/weights", { weights }),
  },
};

/** Trigger a browser download of text content. */
export function downloadText(filename: string, content: string, mime = "text/plain"): void {
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
