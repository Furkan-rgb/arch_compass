import type {
  ArchitectureCaseInput,
  ArchitectureCaseUpdate,
  AtlasExploreRequest,
  AtlasQueryResult,
  AtlasVersion,
  CaseRevision,
  CaseSummary,
  Policy,
  PolicySource,
  ProblemDetail,
  BoundaryReview,
  BoundaryReviewSummary,
  BundledCase,
  ReviewConversation,
  ReviewMessage,
  ReviewScore,
  RepositorySummary,
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

  bundledCases: () => request<BundledCase[]>("/api/bundled-cases"),
  loadBundledCase: (name: string) =>
    request<CaseRevision>(`/api/bundled-cases/${encodeURIComponent(name)}/load`, {
      method: "POST",
    }),

  reviews: (caseId?: string) =>
    request<BoundaryReviewSummary[]>(
      `/api/reviews${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""}`,
    ),
  review: (reviewId: string) =>
    request<BoundaryReview>(`/api/reviews/${encodeURIComponent(reviewId)}`),
  reviewScore: (reviewId: string) =>
    request<ReviewScore | null>(`/api/reviews/${encodeURIComponent(reviewId)}/score`),
  createReview: (caseId: string, repositoryRoot: string) =>
    request<BoundaryReview>("/api/reviews", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId, repository_root: repositoryRoot }),
    }),

  reviewConversations: (reviewId: string) =>
    request<ReviewConversation[]>(
      `/api/review-conversations?review_id=${encodeURIComponent(reviewId)}`,
    ),
  reviewConversation: (conversationId: string) =>
    request<ReviewConversation>(
      `/api/review-conversations/${encodeURIComponent(conversationId)}`,
    ),
  createReviewConversation: (reviewId: string, title?: string): Promise<ReviewConversation> =>
    request<ReviewConversation>("/api/review-conversations", {
      method: "POST",
      body: JSON.stringify({ review_id: reviewId, ...(title ? { title } : {}) }),
    }),
  askReviewQuestion: (conversationId: string, question: string) =>
    request<ReviewMessage>(
      `/api/review-conversations/${encodeURIComponent(conversationId)}/messages`,
      { method: "POST", body: JSON.stringify({ question }) },
    ),

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
  // Indexing answers with the atlas version it created, not a repository summary: the
  // node and edge counts belong to the listing, and claiming them here would be a type
  // that promises fields the response does not carry.
  indexRepository: (rootPath: string) =>
    request<AtlasVersion>("/api/repositories/index", {
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
