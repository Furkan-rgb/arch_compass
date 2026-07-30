import type {
  AnswerProgress,
  BoundaryExcerpt,
  ArchitectureCase,
  AtlasExploreRequest,
  AtlasQueryResult,
  AtlasVersion,
  CaseRevision,
  CaseSummary,
  CaseUpdate,
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

/**
 * One NDJSON request, with each line handed over as it arrives.
 *
 * Shared by both streaming routes rather than written twice. The chunk arithmetic is the same
 * in either case and is the least interesting part of both: a decoder that has to be told
 * whether the stream is finished, and a trailing fragment that waits for the rest of its
 * chunk. Throwing from `onLine` stops reading, which is how a `failed` line becomes an error
 * rather than a value the caller has to remember to check.
 */
async function streamLines<Line>(
  path: string,
  body: unknown,
  refusal: string,
  onLine: (line: Line) => void,
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    // A failure before the stream opens is still a ProblemDetail, as on every route.
    let detail: Partial<ProblemDetail> = {};
    try {
      detail = (await response.json()) as typeof detail;
    } catch {
      detail = { message: response.statusText };
    }
    throw new ApiError(detail.message || refusal, response.status, detail.code);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  for (;;) {
    const { value, done } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const lines = pending.split("\n");
    // The last piece may be half a line; it waits for the rest of its chunk.
    pending = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      onLine(JSON.parse(line) as Line);
    }
    if (done) break;
  }
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
   * The code one finding was measured from, at the spans the detector recorded.
   *
   * Delivery rather than search: the review already says which lines are the evidence, so
   * there is nothing here to query. `contextLines` is how much surrounding code to unfold,
   * bounded by the workspace rather than by this call.
   */
  reviewSource: (reviewId: string, reference: string, contextLines = 0) =>
    request<BoundaryExcerpt[]>(
      `/api/reviews/${encodeURIComponent(reviewId)}/source` +
        `?reference=${encodeURIComponent(reference)}&context_lines=${contextLines}`,
    ),
  /**
   * Record a round of answers as one case revision that says what it answered.
   *
   * One call, not a case patch composed here. The server resolves each `Q-n` against the
   * review's own report and reads the destination field from the question, so a client
   * cannot route an answer into a list its question never named — and cannot produce a
   * revision that has lost the link back to what prompted it.
   *
   * Only answered questions are sent. Skipping is normal and is recorded as absence.
   */
  answerReview: (
    reviewId: string,
    answers: { question_reference: string; recorded_text: string }[],
  ) =>
    request<CaseRevision>(`/api/reviews/${encodeURIComponent(reviewId)}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  /**
   * Ask a running review to stop. Returns when the record says cancelled, which is before
   * the work has actually stopped: the run reads that record between model calls, so a
   * local model can take a few more minutes to notice.
   */
  cancelReview: (reviewId: string) =>
    request<BoundaryReview>(`/api/reviews/${encodeURIComponent(reviewId)}/cancel`, {
      method: "POST",
    }),
  // Not `request`: a 204 has no body to parse, and reading one as JSON would throw on the
  // one response that means it worked.
  deleteReview: async (reviewId: string): Promise<void> => {
    const response = await fetch(`/api/reviews/${encodeURIComponent(reviewId)}`, {
      method: "DELETE",
    });
    if (response.ok) return;
    let detail: Partial<ProblemDetail> = {};
    try {
      detail = (await response.json()) as typeof detail;
    } catch {
      detail = { message: response.statusText };
    }
    throw new ApiError(
      detail.message || "Arch Compass could not delete that review.",
      response.status,
      detail.code,
    );
  },

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
    /** The review this run answers, where it is the second pass of an elicitation. */
    elicitedFrom?: string | null,
  ): Promise<BoundaryReview> => {
    let review: BoundaryReview | null = null;
    await streamLines<ReviewProgress>(
      "/api/reviews/stream",
      {
        case_id: caseId,
        repository_root: repositoryRoot,
        elicited_from: elicitedFrom ?? null,
      },
      "Arch Compass could not start the review.",
      (event) => {
        onProgress(event);
        if (event.event === "failed") {
          throw new ApiError(event.problem.message, 200, event.problem.code);
        }
        if (event.event === "completed") review = event.review;
      },
    );
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
  createReviewConversation: (
    reviewId: string,
    title?: string,
    /**
     * `Q-n` to talk about one open question instead of the review as a whole. The only
     * conversation a review still waiting on answers will open: it is shown the boundaries
     * that question cites and none of the verdicts the page is withholding.
     */
    questionReference?: string,
  ): Promise<ReviewConversation> =>
    request<ReviewConversation>("/api/review-conversations", {
      method: "POST",
      body: JSON.stringify({
        review_id: reviewId,
        ...(title ? { title } : {}),
        ...(questionReference ? { question_reference: questionReference } : {}),
      }),
    }),
  askReviewQuestion: (conversationId: string, question: string) =>
    request<ReviewMessage>(
      `/api/review-conversations/${encodeURIComponent(conversationId)}/messages`,
      { method: "POST", body: JSON.stringify({ question }) },
    ),

  /**
   * The same turn, with the answer's prose arriving as it is written.
   *
   * `onProse` receives fragments to append, never a whole answer to replace what is showing.
   * The resolved message is the record: it carries the validated answer and its grounding, and
   * a provider that cannot stream simply calls `onProse` no times. Whatever the fragments
   * built is provisional until then — an answer that needed a repair round is rewritten
   * without being streamed, so the two can differ.
   */
  streamReviewQuestion: async (
    conversationId: string,
    question: string,
    onProse: (fragment: string) => void,
  ): Promise<ReviewMessage> => {
    let message: ReviewMessage | null = null;
    await streamLines<AnswerProgress>(
      `/api/review-conversations/${encodeURIComponent(conversationId)}/messages/stream`,
      { question },
      "Arch Compass could not ask that question.",
      (event) => {
        if (event.event === "prose") onProse(event.text);
        if (event.event === "failed") {
          throw new ApiError(event.problem.message, 200, event.problem.code);
        }
        if (event.event === "answered") message = event.message;
      },
    );
    if (!message) {
      throw new ApiError(
        "That question ended without an answer.",
        200,
        "incomplete_stream",
      );
    }
    return message;
  },

  cases: () => request<CaseSummary[]>("/api/cases"),
  case: (caseId: string, revision?: number) =>
    request<CaseRevision>(
      `/api/cases/${caseId}${revision ? `?revision=${revision}` : ""}`,
    ),
  createCase: (value: ArchitectureCase) =>
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
  updateCase: (caseId: string, value: CaseUpdate) =>
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
  // Indexes and opens a case about the repository in one step, with nothing written in it.
  // The entry for someone who has not authored a case and should not have to: the review
  // runs on the code alone and asks for what it lacked (master plan §6C.1).
  startFromRepository: (rootPath: string) =>
    request<CaseRevision>("/api/repositories/start", {
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
  /**
   * The neighbourhood of one review's boundaries, in a single call.
   *
   * One request rather than one inspection per boundary. A review examines a handful of them
   * and their neighbourhoods overlap heavily — the same package, the same imports, the same
   * edges returned once per finding — so asking per node paid for the overlap and gave the
   * page as many loading states as there were boundaries.
   *
   * An id the atlas no longer holds is skipped rather than refused, which is what lets a
   * review of a since-reindexed repository still draw the boundaries that survived.
   */
  reviewContext: (rootPath: string, nodeIds: string[], limit?: number) =>
    request<AtlasQueryResult>("/api/repositories/review-context", {
      method: "POST",
      body: JSON.stringify({
        root_path: rootPath,
        node_ids: nodeIds,
        ...(limit === undefined ? {} : { limit }),
      }),
    }),
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
};
