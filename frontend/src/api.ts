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
  ReviewProgress,
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

  /**
   * The same review, reported as it happens.
   *
   * One request, one review, no polling and no shared server state: the run's progress is
   * a property of the request doing the work. `onProgress` sees every line; the resolved
   * value is the composed review, and a `failed` line becomes a thrown `ApiError` so a
   * caller cannot mistake a failure for a result.
   */
  streamReview: async (
    caseId: string,
    repositoryRoot: string,
    onProgress: (event: ReviewProgress) => void,
  ): Promise<BoundaryReview> => {
    const response = await fetch("/api/reviews/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId, repository_root: repositoryRoot }),
    });
    if (!response.ok || !response.body) {
      // A failure before the stream opens is still a ProblemDetail, as on every route.
      let detail: Partial<ProblemDetail> = {};
      try {
        detail = (await response.json()) as typeof detail;
      } catch {
        detail = { message: response.statusText };
      }
      throw new ApiError(
        detail.message || "Arch Compass could not start the review.",
        response.status,
        detail.code,
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let review: BoundaryReview | null = null;
    for (;;) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split("\n");
      // The last piece may be half a line; it waits for the rest of its chunk.
      pending = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as ReviewProgress;
        onProgress(event);
        if (event.event === "failed") {
          throw new ApiError(event.problem.message, 200, event.problem.code);
        }
        if (event.event === "completed") review = event.review;
      }
      if (done) break;
    }
    if (!review) {
      throw new ApiError(
        "The review ended without producing a result.",
        200,
        "incomplete_stream",
      );
    }
    return review;
  },

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
    request<CaseRevision>("/api/cases", {
      method: "POST",
      body: JSON.stringify(value),
    }),
  // Not `request`: the body is YAML rather than JSON, and the route's media type is part
  // of how it tells a case document from a case object.
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
    return (await response.json()) as CaseRevision;
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
