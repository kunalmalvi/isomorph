/** Types mirror backend/api (see docs/api-contracts.md). Stage outputs are engine dicts and typed loosely on purpose. */

export type Provenance = "source" | "computation" | "user" | "ai_hypothesis";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  display_name: string | null;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_by: string;
  archived_at: string | null;
  created_at: string;
  role?: string | null;
}

export interface Problem {
  id: string;
  project_id: string;
  title: string;
  statement: string;
  goal: string | null;
  status: string;
  created_at: string;
}

export interface Discovery {
  id: string;
  problem_id: string;
  project_id?: string;
  status: string;
  threshold: number | null;
  weights: Record<string, number> | null;
  error: string | null;
  created_at: string;
  progress?: Progress | null;
}

export interface StageProgress {
  name: string;
  status: string;
  version: number;
  source: string;
}

export interface Progress {
  run_id: string;
  status: string;
  completed: number;
  total: number;
  error: string | null;
  stages: StageProgress[];
}

export interface StageRecord {
  name: string;
  status: string;
  error: string | null;
  source: string;
  version: number;
  started_at: number | null;
  finished_at: number | null;
  output?: Record<string, unknown> | null;
}

export interface DbMatch {
  id: string;
  rank: number;
  system_key: string;
  score: number;
  domain_distance: number | null;
  domain: string | null;
  system_name: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  kind?: string;
  role?: string;
  confidence?: number;
  provenance?: Provenance;
  attrs?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  weight?: number;
  confidence?: number;
  provenance?: Provenance;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface MatchComponents {
  functional: number;
  relationship: number;
  topological: number;
  dynamic: number;
  constraint: number;
  semantic: number;
}

export interface StageMatch {
  id: string;
  system_id: string;
  system_name: string;
  domain: string;
  score: number;
  domain_distance: number;
  components: MatchComponents;
  differences: string[];
  limitations: string[];
  same_domain?: boolean;
  mapping?: {
    node_pairs: Array<[string, string]> | Array<Record<string, unknown>>;
    edge_pairs: unknown[];
    unmapped_source: string[];
    unmapped_target: string[];
    confidence: number;
  };
}

export interface Concept {
  id: string;
  concept_type: string;
  name: string;
  analog_id: string;
  analog_name: string;
  analog_score: number;
  rationale: string;
  expected_effect: string;
  preconditions: string[];
  caveats: string[];
  status: "ok" | "blocked" | string;
  constraint_report: { status: string; results: Array<Record<string, unknown>>; warnings: unknown[] };
  parameter_overrides: Record<string, unknown>;
}

export interface HypothesisRecord {
  id: string;
  statement: string;
  prediction: string;
  falsifier: string;
  category: string;
  provenance: Provenance;
  status: string;
  based_on: string[];
  experiment: Record<string, unknown> | null;
}

export interface ValidationEntry {
  hypothesis_id: string;
  outcome: string;
  method: string;
  caveats: string;
  evidence: Record<string, unknown>;
}

export interface Domain {
  id: string;
  name: string;
  family: string;
  description: string;
  vocabulary: string[];
  system_count: number;
}

export interface SystemSummary {
  id: string;
  name: string;
  domain: string;
  kind: string;
  summary: string;
  confidence: number | string | null;
  node_count: number;
  edge_count: number;
  sources: unknown[];
}

export interface Report {
  id: string;
  project_id: string;
  discovery_session_id: string;
  title: string;
  created_at: string;
}

export interface ProviderStatus {
  name: string;
  configured?: boolean;
  available?: boolean;
  [key: string]: unknown;
}

export interface SettingsOut {
  weights: Record<string, number>;
  weights_are_default: boolean;
  preferences: Record<string, unknown>;
  default_provider: string;
}

export interface UploadResult {
  filename: string;
  kind: string;
  size: number;
  processed: boolean;
  proposal: Record<string, unknown> | null;
  reason?: string;
}

export interface PersistedHypothesis {
  id: string;
  transformation_id: string;
  project_id: string;
  statement: string;
  prediction: string | null;
  falsifier: string | null;
  provenance: Provenance;
  status: string;
  experiment: Record<string, unknown> | null;
  created_at: string;
}

export interface ValidationRecordOut {
  id: string;
  hypothesis_id: string;
  outcome: string;
  caveats: string | null;
  method: string | null;
  created_at: string;
  evidence?: Record<string, unknown>;
}

/** Reviewer decision and note stored by the server for one generated hypothesis. */
export interface ServerAnnotation {
  hypothesis_id: string;
  decision: "none" | "saved" | "rejected" | "promoted";
  note: string;
  provenance: "user";
  updated_at: number;
}
