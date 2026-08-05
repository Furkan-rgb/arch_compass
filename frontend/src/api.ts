import type {
  AnswerProgress,
  BoundaryExcerpt,
  AtlasExploreRequest,
  AtlasQueryResult,
  AtlasVersion,
  CaseRevision,
  CaseSummary,
  CheckoutRefresh,
  DirectoryListing,
  Policy,
  PolicyDraft,
  PolicySource,
  ProblemDetail,
  BoundaryReview,
  BoundaryReviewSummary,
  BundledExample,
  BulkDecisionRequest,
  BulkDecisionResponse,
  DecisionComment,
  DecisionRequest,
  ReviewDetail,
  StandingDecision,
  ReviewConversation,
  ReviewMessage,
  ReviewProgress,
  RepositoryBranch,
  RepositoryCheckout,
  RepositorySummary,
  RevisionPreflight,
  ModelCatalog,
  WorkspaceSummary,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = "request_failed",
    /** The failure this one was translated from, where it was translated from one. */
    cause?: unknown,
    /**
     * Whether repeating this request could succeed, as the server judged it. Read from the
     * problem detail rather than guessed from the status, which cannot tell a provider that
     * is briefly busy from one whose quota is spent for the day.
     */
    public readonly retryable = false,
  ) {
    super(message, cause === undefined ? undefined : { cause });
  }
}

/** Nothing has been chosen to reason with. A required field, not a failure. */
export const NO_MODEL_CODE = "no_model_selected";

/**
 * The code every "nothing on the other end answered as this API" failure carries.
 *
 * Exported because `ErrorPanel` is what turns it into a cure on screen, and matching on a
 * code is the only way to do that without matching on the prose — which would break the
 * moment either half was reworded.
 */
export const UNREACHABLE_CODE = "workspace_unreachable";

/**
 * What the reader is told when the workspace is not there.
 *
 * The same sentence `ErrorPanel` already wrote for a `fetch` that never connected, because
 * these are one situation with two shapes. The other shape is the one that used to reach the
 * screen raw: with `archcompass web` stopped, the request falls through to whatever is still
 * serving the page, that returns `index.html` for any path it does not know, and the client
 * reported the result as `Unexpected token '<', "<!doctype "... is not valid JSON` — a
 * sentence about a parser, addressed to nobody, naming neither the cause nor the fix.
 */
export const UNREACHABLE_MESSAGE = "The workspace didn’t answer.";

/**
 * Every request in this module goes through here, so the translation happens once.
 *
 * `fetch` rejects with a `TypeError` when the connection itself fails, which is the case
 * where nothing was serving anything. `status` is kept where there was a response, because a
 * proxy's 502 is still a fact worth carrying even when its body was an HTML page.
 */
function unreachable(cause: unknown, status = 0): ApiError {
  return new ApiError(UNREACHABLE_MESSAGE, status, UNREACHABLE_CODE, cause);
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch (cause) {
    throw unreachable(cause);
  }
}

/**
 * The body, or the admission that whatever sent it is not this API.
 *
 * A JSON body is the contract on every route — a result on the way out, a `ProblemDetail` on
 * the way back — so a body that will not parse is not a server error to be reported, it is
 * evidence that the reply came from something else. Real refusals still arrive as JSON and
 * are read below, verbatim, exactly as they were.
 */
async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw unreachable(cause, response.status);
  }
}

/** The server's own words for a refusal, kept as it wrote them. */
async function refusal(response: Response, fallback: string): Promise<ApiError> {
  const detail = await readJson<Partial<ProblemDetail>>(response);
  return new ApiError(
    detail.message || fallback,
    response.status,
    detail.code,
    undefined,
    detail.retryable ?? false,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw await refusal(response, "Arch Compass could not complete the request.");
  }
  return await readJson<T>(response);
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
  refusalMessage: string,
  onLine: (line: Line) => void,
): Promise<void> {
  const response = await send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    // A failure before the stream opens is still a ProblemDetail, as on every route.
    throw await refusal(response, refusalMessage);
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

  /** Asks every configured provider what it has. Only called when the chooser opens. */
  models: () => request<ModelCatalog>("/api/models"),
  selectModel: (choice: { provider: string; model: string; thinking: boolean | null }) =>
    request<WorkspaceSummary>("/api/models/selection", {
      method: "PUT",
      body: JSON.stringify(choice),
    }),
  clearModelSelection: () =>
    request<void>("/api/models/selection", { method: "DELETE" }),

  examples: () => request<BundledExample[]>("/api/examples"),
  // Indexes the example's repository and nothing else: no case exists until the review's
  // questions write one, exactly as for a folder-picked repository.
  loadExample: (name: string) =>
    request<AtlasVersion>(`/api/examples/${encodeURIComponent(name)}/load`, {
      method: "POST",
    }),

  reviews: (caseId?: string) =>
    request<BoundaryReviewSummary[]>(
      `/api/reviews${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""}`,
    ),
  review: (reviewId: string) =>
    request<ReviewDetail>(`/api/reviews/${encodeURIComponent(reviewId)}`),
  /**
   * Record a standing decision about one boundary of one branch.
   *
   * The whole verdict context travels with it — review, reference, material, label — so the
   * decision permanently names what the team actually looked at, and a later run whose
   * verdict differs can say the ground moved rather than silently inheriting approval.
   */
  // Many boundaries, one decision, one transaction — the gesture that adopts a legacy
  // repository. Individual standing decisions are recorded, each with the same author,
  // which is the difference between sign-off and silence.
  postBulkDecisions: (decisions: BulkDecisionRequest) =>
    request<BulkDecisionResponse>("/api/decisions/bulk", {
      method: "POST",
      body: JSON.stringify(decisions),
    }),
  postDecision: (decision: DecisionRequest) =>
    request<StandingDecision>("/api/decisions", {
      method: "POST",
      body: JSON.stringify(decision),
    }),
  decisionComments: (branchId: string, fingerprint: string) =>
    request<DecisionComment[]>(
      `/api/decisions/${encodeURIComponent(branchId)}/${encodeURIComponent(fingerprint)}/comments`,
    ),
  postDecisionComment: (
    branchId: string,
    fingerprint: string,
    comment: { author: string; body: string },
  ) =>
    request<DecisionComment>(
      `/api/decisions/${encodeURIComponent(branchId)}/${encodeURIComponent(fingerprint)}/comments`,
      { method: "POST", body: JSON.stringify(comment) },
    ),
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
    const response = await send(`/api/reviews/${encodeURIComponent(reviewId)}`, {
      method: "DELETE",
    });
    if (response.ok) return;
    throw await refusal(response, "Arch Compass could not delete that review.");
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
  /**
   * One directory's immediate subdirectories, for the folder picker on the start step. No
   * path means the home directory.
   */
  directories: (path?: string) =>
    request<DirectoryListing>(
      `/api/filesystem/directories${path ? `?path=${encodeURIComponent(path)}` : ""}`,
    ),
  repositories: () => request<RepositorySummary[]>("/api/repositories"),
  // Every branch the workspace has a lineage for, with the repository it belongs to —
  // what turns a review's branch_id into a name, and the options a branch switch offers.
  branches: () => request<RepositoryBranch[]>("/api/branches"),
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
  // Clones the address into the workspace's own checkouts directory — or, for a local
  // path that is already a repository root, answers with that path reviewed in place.
  // Either way the folder handed back is a git root, which is what makes the repository
  // identity real rather than a path hash.
  checkoutRepository: (url: string, branch: string | null) =>
    request<RepositoryCheckout>("/api/repositories/checkout", {
      method: "POST",
      body: JSON.stringify({ url, branch }),
    }),
  // Catches a checkout Arch Compass made up with its remote, given only the folder — which
  // is all a page reviewing a repository holds. A folder that is not ours comes back
  // `managed: false` and untouched, so this is safe to call before any review.
  refreshRepository: (rootPath: string) =>
    request<CheckoutRefresh>("/api/repositories/refresh", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath }),
    }),
  // Whether a new revision would find anything, asked before one is created. The repository
  // is re-indexed and the delta is worked out; `changed: false` means every boundary would
  // carry, and in that case no case revision, no review and no ledger event were written —
  // the caller has been told the answer instead of being handed a revision that repeats the
  // one above it.
  preflightRepository: (rootPath: string) =>
    request<RevisionPreflight>("/api/repositories/preflight", {
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
  /**
   * Write a policy of this workspace's own. The id is the server's to derive from the
   * title, which is why nothing here sends one — and why a title whose slug is already
   * taken comes back as a 409 rather than quietly replacing what holds it.
   */
  createPolicy: (draft: PolicyDraft) =>
    request<Policy>("/api/policies", {
      method: "POST",
      body: JSON.stringify(draft),
    }),
  // PUT, because this is the policy stated again in full rather than a patch: a file is
  // rewritten from what the form holds, and a field left out would be a field cleared.
  updatePolicy: (policyId: string, draft: PolicyDraft) =>
    request<Policy>(`/api/policies/${encodeURIComponent(policyId)}`, {
      method: "PUT",
      body: JSON.stringify(draft),
    }),
  // Not `request`: a 204 has no body to parse, as on deleting a review.
  deletePolicy: async (policyId: string): Promise<void> => {
    const response = await send(`/api/policies/${encodeURIComponent(policyId)}`, {
      method: "DELETE",
    });
    if (response.ok) return;
    throw await refusal(response, "Arch Compass could not delete that policy.");
  },
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
