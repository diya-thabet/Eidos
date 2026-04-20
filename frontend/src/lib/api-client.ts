import { API_URL } from "./constants";

class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API Error ${status}`);
  }
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options?.headers as Record<string, string>) || {}),
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const res = await fetch(`${API_URL}${path}`, { ...options, headers });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  }

  // ?? Health ??
  ping = () => this.request<{ status: string }>("/health");
  version = () => this.request<{ version: string; edition: string }>("/version");

  // ?? Repos ??
  repos = {
    list: () => this.request<RepoOut[]>("/repos"),
    get: (id: string) => this.request<RepoOut>(`/repos/${id}`),
    create: (body: RepoCreate) =>
      this.request<RepoOut>("/repos", { method: "POST", body: JSON.stringify(body) }),
    ingest: (id: string) =>
      this.request<SnapshotOut>(`/repos/${id}/ingest`, { method: "POST" }),
    status: (id: string) => this.request<SnapshotOut[]>(`/repos/${id}/status`),
  };

  // ?? Snapshots ??
  snapshots = {
    get: (repoId: string, snapId: string) =>
      this.request<SnapshotOut>(`/repos/${repoId}/snapshots/${snapId}`),
  };

  // ?? Analysis ??
  analysis = {
    symbols: (repoId: string, snapId: string, params?: string) =>
      this.request<SymbolOut[]>(
        `/repos/${repoId}/snapshots/${snapId}/symbols${params ? `?${params}` : ""}`,
      ),
    symbol: (repoId: string, snapId: string, fq: string) =>
      this.request<SymbolOut>(`/repos/${repoId}/snapshots/${snapId}/symbols/${fq}`),
    edges: (repoId: string, snapId: string, params?: string) =>
      this.request<EdgeOut[]>(
        `/repos/${repoId}/snapshots/${snapId}/edges${params ? `?${params}` : ""}`,
      ),
    graph: (repoId: string, snapId: string, fq: string) =>
      this.request<GraphNeighborhood>(`/repos/${repoId}/snapshots/${snapId}/graph/${fq}`),
    overview: (repoId: string, snapId: string) =>
      this.request<AnalysisOverview>(`/repos/${repoId}/snapshots/${snapId}/overview`),
  };

  // ?? Code Health ??
  health = {
    rules: (repoId: string, snapId: string) =>
      this.request<RuleMetadata[]>(`/repos/${repoId}/snapshots/${snapId}/health/rules`),
    check: (repoId: string, snapId: string, body: HealthCheckRequest) =>
      this.request<HealthReport>(`/repos/${repoId}/snapshots/${snapId}/health`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  };

  // ?? Reasoning / Q&A ??
  reasoning = {
    ask: (repoId: string, snapId: string, body: { question: string }) =>
      this.request<AskResponse>(`/repos/${repoId}/snapshots/${snapId}/ask`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  };

  // ?? Reviews ??
  reviews = {
    submit: (repoId: string, snapId: string, body: { diff: string }) =>
      this.request<ReviewResult>(`/repos/${repoId}/snapshots/${snapId}/review`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    list: (repoId: string, snapId: string) =>
      this.request<ReviewResult[]>(`/repos/${repoId}/snapshots/${snapId}/reviews`),
  };

  // ?? Documentation ??
  docs = {
    generate: (repoId: string, snapId: string, body: DocGenRequest) =>
      this.request<DocOut>(`/repos/${repoId}/snapshots/${snapId}/docs`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    list: (repoId: string, snapId: string) =>
      this.request<DocOut[]>(`/repos/${repoId}/snapshots/${snapId}/docs`),
    get: (repoId: string, snapId: string, docId: string) =>
      this.request<DocOut>(`/repos/${repoId}/snapshots/${snapId}/docs/${docId}`),
  };

  // ?? Auth ??
  auth = {
    me: () => this.request<UserOut>("/auth/me"),
  };

  // ?? Admin ??
  admin = {
    system: () => this.request<SystemInfo>("/admin/system"),
    users: () => this.request<UserOut[]>("/admin/users"),
    updateRole: (userId: string, role: string) =>
      this.request<UserOut>(`/admin/users/${userId}/role`, {
        method: "PUT",
        body: JSON.stringify({ role }),
      }),
    plans: () => this.request<PlanOut[]>("/admin/plans"),
    createPlan: (body: PlanCreate) =>
      this.request<PlanOut>("/admin/plans", { method: "POST", body: JSON.stringify(body) }),
    assignSubscription: (userId: string, planId: string) =>
      this.request(`/admin/users/${userId}/subscription`, {
        method: "PUT",
        body: JSON.stringify({ plan_id: planId }),
      }),
    usage: (params?: string) =>
      this.request<UsageOut[]>(`/admin/usage${params ? `?${params}` : ""}`),
  };
}

export const api = new ApiClient();
export { ApiError };

// ?? Types (matching backend schemas) ??

export interface RepoOut {
  id: string;
  name: string;
  url: string;
  default_branch: string;
  git_provider: string;
  created_at: string;
  last_indexed_at: string | null;
}

export interface RepoCreate {
  name: string;
  url: string;
  default_branch?: string;
  git_provider?: string;
  git_token?: string;
}

export interface SnapshotOut {
  id: string;
  repo_id: string;
  commit_sha: string | null;
  status: "pending" | "running" | "completed" | "failed";
  file_count: number;
  error_message: string | null;
  created_at: string;
}

export interface SymbolOut {
  id: number;
  kind: string;
  name: string;
  fq_name: string;
  file_path: string;
  start_line: number;
  end_line: number;
  namespace: string;
  parent_fq_name: string | null;
  signature: string;
  modifiers: string;
  return_type: string;
}

export interface EdgeOut {
  id: number;
  source_fq_name: string;
  target_fq_name: string;
  edge_type: string;
  file_path: string;
  line: number;
}

export interface GraphNeighborhood {
  symbol: SymbolOut;
  callers: SymbolOut[];
  callees: SymbolOut[];
  children: SymbolOut[];
}

export interface AnalysisOverview {
  snapshot_id: string;
  total_symbols: number;
  total_edges: number;
  total_modules: number;
  symbols_by_kind: Record<string, number>;
  entry_points: string[];
  hotspots: string[];
}

export interface RuleMetadata {
  rule_id: string;
  rule_name: string;
  category: string;
  severity: string;
  description: string;
}

export interface HealthCheckRequest {
  categories?: string[];
  disabled_rules?: string[];
  max_method_lines?: number;
  max_class_lines?: number;
  max_parameters?: number;
  max_fan_out?: number;
  max_fan_in?: number;
  max_children?: number;
  max_inheritance_depth?: number;
  max_god_class_methods?: number;
  use_llm?: boolean;
}

export interface HealthFinding {
  rule_id: string;
  rule_name: string;
  category: string;
  severity: string;
  symbol: string;
  file: string;
  line: number;
  message: string;
  suggestion: string;
}

export interface HealthReport {
  total_symbols: number;
  total_files: number;
  findings_count: number;
  findings: HealthFinding[];
  summary: Record<string, number>;
  category_scores: Record<string, number>;
  overall_score: number;
  llm_insights: Array<{ category: string; title: string; recommendation: string }>;
}

export interface AskResponse {
  answer: string;
  confidence: string;
  evidence: Array<{ file: string; symbol: string; lines: string }>;
  verification: string[];
}

export interface ReviewResult {
  id?: string;
  findings: Array<{
    severity: string;
    file: string;
    line: number;
    message: string;
    suggestion: string;
  }>;
  created_at?: string;
}

export interface DocGenRequest {
  scope_type?: string;
  scope_id?: string;
  format?: string;
}

export interface DocOut {
  id: string;
  content: string;
  scope_type: string;
  scope_id: string;
  created_at: string;
}

export interface UserOut {
  id: string;
  github_login: string;
  name: string;
  email: string;
  role: string;
  created_at: string;
}

export interface SystemInfo {
  edition: string;
  version: string;
  auth_enabled: boolean;
  parsers: number;
  users: number;
  repos: number;
}

export interface PlanOut {
  id: string;
  name: string;
  description: string;
  limits: string;
  is_active: boolean;
}

export interface PlanCreate {
  name: string;
  description?: string;
  limits: Record<string, unknown>;
}

export interface UsageOut {
  user_id: string;
  action: string;
  tokens_used: number;
  created_at: string;
}
