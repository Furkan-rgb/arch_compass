import type {
  ArchitectureCaseInput,
  ArchitectureCaseUpdate,
  AtlasExploreRequest,
  AtlasQueryResult,
  CaseRevision,
  CaseSummary,
  ConsultationJob,
  ConsultationRun,
  Policy,
  PolicySource,
  ProblemDetail,
  ProgressEvent,
  RepositorySummary,
  RunSummary,
  WorkspaceSummary,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = "request_failed",
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail: Partial<ProblemDetail> = {};
    try {
      detail = (await response.json()) as typeof detail;
    } catch {
      detail = { message: response.statusText };
    }
    throw new ApiError(
      detail.message || "Arch Compass could not complete the request.",
      response.status,
      detail.code,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  workspace: () => request<WorkspaceSummary>("/api/workspace"),
  cases: () => request<CaseSummary[]>("/api/cases"),
  case: (caseId: string, revision?: number) =>
    request<CaseRevision>(
      `/api/cases/${caseId}${revision ? `?revision=${revision}` : ""}`,
    ),
  createCase: (value: ArchitectureCaseInput) =>
    request<{ case_id: string; revision: number }>("/api/cases", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  importCase: async (source: string) => {
    const response = await fetch("/api/cases/import-yaml", {
      method: "POST",
      headers: { "Content-Type": "text/yaml" },
      body: source,
    });
    if (!response.ok) {
      const detail = (await response.json()) as Partial<ProblemDetail>;
      throw new ApiError(detail.message || "Invalid case YAML.", response.status, detail.code);
    }
    return (await response.json()) as { case_id: string; revision: number };
  },
  updateCase: (caseId: string, value: ArchitectureCaseUpdate) =>
    request<CaseRevision>(`/api/cases/${caseId}`, {
      method: "PATCH",
      body: JSON.stringify(value),
    }),
  repositories: () => request<RepositorySummary[]>("/api/repositories"),
  indexRepository: (rootPath: string) =>
    request<RepositorySummary>("/api/repositories/index", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath }),
    }),
  repositorySummary: (rootPath: string) =>
    request<AtlasQueryResult>(
      `/api/repositories/summary?root_path=${encodeURIComponent(rootPath)}`,
    ),
  repositoryHotspots: (rootPath: string, metric = "reverse_dependency_reach") =>
    request<AtlasQueryResult>(
      `/api/repositories/hotspots?root_path=${encodeURIComponent(rootPath)}&metric=${encodeURIComponent(metric)}`,
    ),
  repositoryInspect: (rootPath: string, nodeId: string) =>
    request<AtlasQueryResult>(
      `/api/repositories/inspect?root_path=${encodeURIComponent(rootPath)}&node_id=${encodeURIComponent(nodeId)}`,
    ),
  repositoryExplore: (value: AtlasExploreRequest) =>
    request<AtlasQueryResult>("/api/repositories/explore", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  startConsultation: (caseId: string, repositoryRoot?: string) =>
    request<ConsultationJob>("/api/consultations", {
      method: "POST",
      body: JSON.stringify({
        case_id: caseId,
        repository_root: repositoryRoot || null,
      }),
    }),
  jobs: () => request<ConsultationJob[]>("/api/consultations"),
  job: (runId: string) => request<ConsultationJob>(`/api/consultations/${runId}`),
  events: (runId: string) =>
    request<ProgressEvent[]>(`/api/consultations/${runId}/events`),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (runId: string) => request<ConsultationRun>(`/api/runs/${runId}`),
  policies: () => request<Policy[]>("/api/policies"),
  policySources: () => request<PolicySource[]>("/api/policies/sources"),
  addPolicySource: (source: string) =>
    request<PolicySource>("/api/policies/sources", {
      method: "POST",
      body: JSON.stringify({ source }),
    }),
  removePolicySource: (source: string) =>
    request<{ removed: boolean }>(
      `/api/policies/sources?source=${encodeURIComponent(source)}`,
      { method: "DELETE" },
    ),
  rebuildPolicies: () =>
    request<Record<string, unknown>>("/api/policies/rebuild", {
      method: "POST",
      body: JSON.stringify({ repository_root: null }),
    }),
};
