import type { components } from "./openapi.generated";

type Schema = components["schemas"];

export type Review = Schema["ReviewResponse"];
/** One review as a listing reads it: the same identity, with counts in place of collections. */
export type ReviewSummary = Schema["ReviewSummaryResponse"];
export type Finding = Schema["FindingResponse"];
export type Candidate = Schema["CandidateResponse"];
export type Question = Schema["QuestionResponse"];
export type Evidence = Schema["EvidenceResponse"];
export type RetrievalProvenance = Schema["RetrievalProvenanceResponse"];
export type Investigation = Schema["RecordedInvestigationResponse"];
export type InvestigationLookup = Schema["InvestigationLookupResponse"];
export type PolicyDocument = Schema["PolicyDocument"];
export type PolicyDraft = Schema["PolicyDraft"];
export type PolicySourceRegistration = Schema["PolicySourceRegistration"];
export type DecisionDisposition = Schema["DecisionDisposition"];
export type Decision = Schema["DecisionResponse"];
export type ReviewConversation = Schema["ReviewConversationResponse"];
export type CaseSummary = Schema["archcompass__presentation__web__routes__cases__CaseResponse"];
export type ReviewCase = Schema["archcompass__presentation__web__routes__reviews__CaseResponse"];
/** Which policies a case can retrieve. The one thing about a case a person still sets. */
export type PolicyContext = Schema["PolicyContextDTO"];
export type RepositorySummary = Schema["RepositorySummary"];
export type RepositoryBranch = Schema["RepositoryBranch"];
export type RepositoryCheckout = Schema["RepositoryCheckout"];
export type CheckoutRefresh = Schema["CheckoutRefresh"];
export type BundledExample = Schema["BundledExample"];
export type ModelCatalog = Schema["ModelCatalogResponse"];
/** How hard a model is asked to think: a level where the provider has levels, else a switch. */
export type ThinkingMode = Schema["ModelSelectionRequest"]["thinking"];
export type EmbeddingCatalog = Schema["EmbeddingCatalogResponse"];
export type Workspace = Schema["WorkspaceSummaryResponse"];
export type AtlasQueryResult = Schema["AtlasQueryResult"];
export type AtlasNodeSummary = Schema["AtlasNodeSummary"];
export type AtlasEdge = Schema["AtlasEdge"];
export type ObscuritySignal = Schema["ObscuritySignal"];
export type AtlasVersion = Schema["AtlasVersion"];
export type DirectoryListing = Schema["DirectoryListing"];
export type RepositoryFolderTree = Schema["RepositoryFolderTree"];
export type RepositoryFolder = Schema["RepositoryFolder"];
export type ProviderAvailability = Schema["ProviderAvailabilityResponse"];

export type ReviewRun = Schema["ReviewRunResponse"];

/**
 * A caller's cancellation, however it was handed over.
 *
 * React Query calls a `queryFn` with its whole context rather than with a signal, so a
 * method used directly as one — `queryFn: api.reviews` — receives an object. Accepting
 * both means the readers that take no arguments cancel with the query that asked for them
 * without a single call site having to unwrap anything.
 */
export type Abortable = AbortSignal | { signal?: AbortSignal } | undefined;

/**
 * How long a read waits before giving up on its own.
 *
 * Thirty seconds is far longer than any of these takes and short enough that a request
 * lost to a sleeping laptop or a dead proxy fails visibly instead of spinning for ever.
 *
 * It is only for reads, and for the writes that are over when the server answers. Anything
 * that starts real work — cloning a repository, indexing one, judging a review, answering
 * a question — gets none: the work carries on after a timeout fires, so aborting says
 * nothing true about it and takes away the answer that would have.
 */
const READ_TIMEOUT_MS = 30_000;

/** No deadline: the server is doing something this request cannot put a clock on. */
const NO_TIMEOUT = null;

type RequestOptions = Omit<RequestInit, "signal"> & {
  abort?: Abortable;
  timeout?: number | null;
};

function signalOf(source: Abortable): AbortSignal | undefined {
  if (source === undefined) return undefined;
  return source instanceof AbortSignal ? source : source.signal;
}

function deadline(abort: Abortable, timeout: number | null): AbortSignal | undefined {
  const caller = signalOf(abort);
  const limit = timeout === null ? undefined : AbortSignal.timeout(timeout);
  if (caller && limit) return AbortSignal.any([caller, limit]);
  return caller ?? limit;
}

async function problem(response: Response): Promise<Error> {
  const detail = (await response.json().catch(() => null)) as
    | { message?: string; field_errors?: string[] }
    | null;
  const suffix = detail?.field_errors?.length ? ` (${detail.field_errors.join("; ")})` : "";
  return new Error(`${detail?.message || `Request failed with ${response.status}`}${suffix}`);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { abort, timeout = READ_TIMEOUT_MS, ...init } = options;
  const response = await fetch(path, {
    ...init,
    signal: deadline(abort, timeout),
    headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (!response.ok) throw await problem(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestText(path: string, abort?: Abortable): Promise<string> {
  const response = await fetch(path, { signal: deadline(abort, READ_TIMEOUT_MS) });
  if (!response.ok) throw await problem(response);
  return response.text();
}

const encode = encodeURIComponent;

export const api = {
  // Workspace and models -----------------------------------------------------------------
  workspace: (abort?: Abortable) => request<Workspace>("/api/workspace", { abort }),
  models: (abort?: Abortable) => request<ModelCatalog>("/api/models", { abort }),
  selectModel: (provider: string, model: string, thinking: ThinkingMode) =>
    request<Workspace>("/api/models/selection", {
      method: "PUT",
      body: JSON.stringify({ provider, model, thinking }),
    }),
  /**
   * Forget the reasoning model this workspace was set to.
   *
   * The way back out of a choice that turned out to be wrong — which matters most when the
   * provider has stopped answering, because then the chooser cannot offer the selected
   * model as a tile to click away from.
   */
  clearModelSelection: () =>
    request<void>("/api/models/selection", { method: "DELETE" }),
  embeddings: (abort?: Abortable) => request<EmbeddingCatalog>("/api/embeddings", { abort }),
  selectEmbedding: (provider: string, model: string) =>
    request<Workspace>("/api/embeddings/selection", {
      method: "PUT",
      body: JSON.stringify({ provider, model }),
    }),
  clearEmbeddingSelection: () =>
    request<void>("/api/embeddings/selection", { method: "DELETE" }),
  directories: (path?: string, abort?: Abortable) =>
    request<DirectoryListing>(
      `/api/filesystem/directories${path ? `?path=${encode(path)}` : ""}`,
      { abort },
    ),

  // Reviews ------------------------------------------------------------------------------
  reviewRuns: (abort?: Abortable) => request<ReviewRun[]>("/api/reviews/runs", { abort }),
  reviews: (abort?: Abortable) => request<Review[]>("/api/reviews", { abort }),
  /**
   * The review list as a list: identity, lineage and counts, without the reviews.
   *
   * A stored review is most of a repository's atlas, and the screens that list reviews read
   * a name, a number and a few counts off each one — so the full list was megabytes a row
   * to draw a line of text, and the server decoded every one of those rows to count five
   * integers off it. Ask for this everywhere except the page that renders a review.
   */
  reviewSummaries: (abort?: Abortable) =>
    request<ReviewSummary[]>("/api/reviews?view=summary", { abort }),
  review: (id: string, abort?: Abortable) =>
    request<Review>(`/api/reviews/${encode(id)}`, { abort }),
  reviewReport: (id: string, abort?: Abortable) =>
    requestText(`/api/reviews/${encode(id)}/report`, abort),
  deleteReview: (id: string) => request<void>(`/api/reviews/${encode(id)}`, { method: "DELETE" }),
  /**
   * Start a review that is not held open by this tab.
   *
   * The workspace answers with a run id before there is a review, which is what makes the
   * page reloadable: the run is somewhere to come back to, however many minutes the
   * judging takes.
   */
  startReviewRun: (caseId: string, root: string) =>
    request<ReviewRun>("/api/reviews/runs", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId, repository_root: root }),
      timeout: NO_TIMEOUT,
    }),
  reviewRun: (runId: string, abort?: Abortable) =>
    request<ReviewRun>(`/api/reviews/runs/${encode(runId)}`, { abort }),
  /**
   * Stop a run somebody no longer wants, and read what became of it.
   *
   * The run keeps its id and its stages under the status `cancelled`, so the address the
   * page is already watching goes on answering. It stops at the next stage boundary rather
   * than instantly — the stage in flight finishes — which is why this answers with the run
   * rather than with nothing.
   */
  cancelRun: (runId: string) =>
    request<ReviewRun>(`/api/reviews/runs/${encode(runId)}/cancel`, { method: "POST" }),
  /**
   * Answer a clarification round and wait for the whole rejudgement in this request.
   *
   * Minutes long, with nowhere to come back to if the tab closes. Prefer `answerRun`.
   */
  answer: (
    reviewId: string,
    answers: Array<{ question_id: string; status: "answered" | "skipped"; value?: string | null }>,
    stop = false,
  ) =>
    request<Review>(`/api/reviews/${encode(reviewId)}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers, stop }),
      timeout: NO_TIMEOUT,
    }),
  /**
   * Answer a clarification round and get a run to watch the rejudgement on.
   *
   * The same fix `startReviewRun` was for, on the other half of a review. Answering
   * rejudges every extant candidate, which is minutes of model work — and holding that
   * inside one request made the browser tab the thing keeping it alive, so a reload left
   * the person unable to tell whether their answers had been recorded at all.
   *
   * The run id is the one the review has been on all along, so `/runs/{run_id}` is where
   * to navigate and the existing run page takes it from there.
   *
   * `NO_TIMEOUT`, like every other call that starts work. This looks like it should be
   * quick — it validates the answers and hands back a run — but it decodes the whole review
   * to do it, and on a large one that took longer than the thirty seconds it was inheriting.
   * The abort put the button back with the answers still in it, a second identical POST
   * went out, and by then the first had opened the next round: the retry then resumed a
   * round it was not written for and destroyed the case. The server refuses that now, and
   * this is the half that stops it being provoked in the first place.
   */
  answerRun: (
    reviewId: string,
    answers: Array<{ question_id: string; status: "answered" | "skipped"; value?: string | null }>,
    stop = false,
  ) =>
    request<ReviewRun>(`/api/reviews/${encode(reviewId)}/answers/runs`, {
      method: "POST",
      body: JSON.stringify({ answers, stop }),
      timeout: NO_TIMEOUT,
    }),
  cancel: (reviewId: string) =>
    request<Review>(`/api/reviews/${encode(reviewId)}/cancel`, { method: "POST" }),

  // Repositories -------------------------------------------------------------------------
  repositories: (abort?: Abortable) =>
    request<RepositorySummary[]>("/api/repositories", { abort }),
  branches: (abort?: Abortable) => request<RepositoryBranch[]>("/api/branches", { abort }),
  /**
   * The branches an address publishes, read off the remote without cloning it.
   *
   * An empty array is a real answer — a private remote git has no credentials for, a wrong
   * address, or a deployment that fetches archives and never runs git — so a caller filling
   * in a chooser has to be able to fall back to a name being typed.
   */
  remoteBranches: (url: string, abort?: Abortable) =>
    request<string[]>(`/api/repositories/remote-branches?url=${encode(url)}`, { abort }),
  checkoutRepository: (url: string, branch: string | null) =>
    request<RepositoryCheckout>("/api/repositories/checkout", {
      method: "POST",
      body: JSON.stringify({ url, branch }),
      timeout: NO_TIMEOUT,
    }),
  refreshRepository: (root: string) =>
    request<CheckoutRefresh>("/api/repositories/refresh", {
      method: "POST",
      body: JSON.stringify({ root_path: root }),
      timeout: NO_TIMEOUT,
    }),
  indexRepository: (root: string, excludedPaths?: string[]) =>
    request<AtlasVersion>("/api/repositories/index", {
      method: "POST",
      // Omitted, not null: absent keeps the scope this repository was last indexed under,
      // and `[]` is somebody saying "all of it". Re-indexing from a page that never asked
      // about scope must not silently widen a review somebody narrowed.
      body: JSON.stringify({ root_path: root, ...(excludedPaths ? { excluded_paths: excludedPaths } : {}) }),
      timeout: NO_TIMEOUT,
    }),
  repositoryTree: (root: string, abort?: Abortable) =>
    request<RepositoryFolderTree>("/api/repositories/tree", {
      method: "POST",
      body: JSON.stringify({ root_path: root }),
      abort,
    }),
  repositoryHotspots: (root: string, metric = "reverse_dependency_reach", abort?: Abortable) =>
    request<AtlasQueryResult>(
      `/api/repositories/hotspots?root_path=${encode(root)}&metric=${encode(metric)}`,
      { abort },
    ),
  /**
   * The subgraph around a set of atlas nodes, in one round trip.
   *
   * The same question asked about a whole set rather than one node, with the neighbours
   * included — which is what makes one request enough to draw a review's map rather than
   * one request per finding, and what leaves no edge whose other end was never named.
   *
   * Ids the atlas no longer holds are skipped rather than refused, so a map drawn against a
   * rebuilt atlas is short a card rather than absent.
   */
  reviewContext: (
    root: string,
    nodeIds: string[],
    qualifiedNames: string[] = [],
    limit = 25,
    abort?: Abortable,
  ) =>
    request<AtlasQueryResult>("/api/repositories/review-context", {
      method: "POST",
      body: JSON.stringify({
        root_path: root,
        node_ids: nodeIds,
        qualified_names: qualifiedNames,
        limit,
      }),
      abort,
    }),
  exploreRepository: (
    root: string,
    body: Partial<Schema["AtlasExploreRequest"]> & { operation: Schema["AtlasExploreRequest"]["operation"] },
    abort?: Abortable,
  ) =>
    request<AtlasQueryResult>("/api/repositories/explore", {
      method: "POST",
      body: JSON.stringify({ root_path: root, limit: 40, ...body }),
      abort,
    }),
  searchAtlas: (root: string, terms: string[], abort?: Abortable) =>
    api.exploreRepository(root, { operation: "search_nodes", terms }, abort),
  startRepository: (root: string, startClean = false, excludedPaths?: string[]) =>
    request<Schema["StartedCaseResponse"]>("/api/repositories/start", {
      method: "POST",
      body: JSON.stringify({
        root_path: root,
        start_clean: startClean,
        ...(excludedPaths ? { excluded_paths: excludedPaths } : {}),
      }),
      timeout: NO_TIMEOUT,
    }),

  // Examples -----------------------------------------------------------------------------
  examples: (abort?: Abortable) => request<BundledExample[]>("/api/examples", { abort }),
  loadExample: (name: string) =>
    request<AtlasVersion>(`/api/examples/${encode(name)}/load`, {
      method: "POST",
      timeout: NO_TIMEOUT,
    }),

  // Cases --------------------------------------------------------------------------------
  cases: (abort?: Abortable) => request<CaseSummary[]>("/api/cases", { abort }),
  caseHistory: (id: string, abort?: Abortable) =>
    request<CaseSummary[]>(`/api/cases/${encode(id)}/history`, { abort }),
  createCase: (policyContext: PolicyContext = {}) =>
    request<CaseSummary>("/api/cases", {
      method: "POST",
      body: JSON.stringify({ policy_context: policyContext }),
    }),
  /**
   * Re-scope which policies a case can retrieve.
   *
   * The only thing on a case that is patched rather than answered, and the only reason a
   * scoped policy is ever reachable: a policy that names a user, an organisation or a
   * repository never enters the mandatory lane unless the case matches it. Intent does not
   * come in here — it arrives as an answer to a question a judgement raised.
   */
  rescopeCase: (id: string, policyContext: PolicyContext) =>
    request<CaseSummary>(`/api/cases/${encode(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ policy_context: policyContext }),
    }),

  // Policies -----------------------------------------------------------------------------
  /**
   * The corpus a review would judge against.
   *
   * `repositoryRoot` adds that repository's own `.archcompass/policies`, which is what
   * every review loads and therefore the only corpus that matches what the findings cite.
   * Without it a team keeping its rules in the repository sees them applied in every
   * finding and absent from the page called Policies.
   *
   * An options object rather than a positional argument because this is passed straight to
   * React Query as a `queryFn` in places, and a `queryFn` is called with its context — a
   * positional first parameter would quietly receive that object instead of a path.
   */
  policies: (options: { repositoryRoot?: string | null; signal?: AbortSignal } = {}) =>
    request<PolicyDocument[]>(
      `/api/policies${options.repositoryRoot ? `?repository_root=${encode(options.repositoryRoot)}` : ""}`,
      { abort: options.signal },
    ),
  /** One policy, by the id a finding cites it under. */
  policy: (id: string, repositoryRoot?: string | null, abort?: Abortable) =>
    request<PolicyDocument>(
      `/api/policies/${encode(id)}${repositoryRoot ? `?repository_root=${encode(repositoryRoot)}` : ""}`,
      { abort },
    ),
  policySources: (abort?: Abortable) =>
    request<PolicySourceRegistration[]>("/api/policies/sources", { abort }),
  /** Read a folder of Markdown policies on this machine into every review. */
  addPolicySource: (source: string) =>
    request<PolicySourceRegistration>("/api/policies/sources", {
      method: "POST",
      body: JSON.stringify({ source }),
    }),
  /** Stop reading one. `removed: false` means it was not registered in the first place. */
  removePolicySource: (source: string) =>
    request<Schema["PolicySourceRemovalResponse"]>(
      `/api/policies/sources?source=${encode(source)}`,
      { method: "DELETE" },
    ),
  createPolicy: (draft: PolicyDraft) =>
    request<PolicyDocument>("/api/policies", { method: "POST", body: JSON.stringify(draft) }),
  updatePolicy: (id: string, draft: PolicyDraft) =>
    request<PolicyDocument>(`/api/policies/${encode(id)}`, {
      method: "PUT",
      body: JSON.stringify(draft),
    }),
  deletePolicy: (id: string) => request<void>(`/api/policies/${encode(id)}`, { method: "DELETE" }),

  // Decisions ----------------------------------------------------------------------------
  decide: (
    reviewId: string,
    candidateId: string,
    disposition: DecisionDisposition,
    reasoning: string | null,
  ) =>
    request<Decision>("/api/decisions", {
      method: "POST",
      body: JSON.stringify({
        review_id: reviewId,
        candidate_id: candidateId,
        disposition,
        author: "user",
        reasoning,
      }),
    }),
  /**
   * One disposition, recorded against several candidates, in one round trip.
   *
   * For accepting or parking a run of candidates that were settled together. A waiver takes
   * one reasoning string, and a reason that fits twelve findings is usually not a reason —
   * so a bulk waiver is a shape the server will take and the interface should not offer.
   */
  decideMany: (
    reviewId: string,
    candidateIds: string[],
    disposition: DecisionDisposition,
    reasoning: string | null = null,
  ) =>
    request<Schema["BulkDecisionResponse"]>("/api/decisions/bulk", {
      method: "POST",
      body: JSON.stringify({
        review_id: reviewId,
        disposition,
        author: "user",
        reasoning,
        candidates: candidateIds.map((candidate_id) => ({ candidate_id })),
      }),
    }),
  decisions: (branchId: string, abort?: Abortable) =>
    request<Schema["BranchDecisionsResponse"]>(`/api/branches/${encode(branchId)}/decisions`, {
      abort,
    }),
  /**
   * Every decision ever recorded about one candidate on one branch, newest first.
   *
   * What the bar beside a standing decision cannot say on its own: the disposition it
   * carries is the current one, and the question a reader has in front of a re-raised row
   * is what was decided the last four times, by whom, and against which verdict. Each entry
   * pins the finding it answered — its verdict and its model, prompt and retrieval
   * identities — so a decision taken when a different model judged is visible as one.
   */
  decisionHistory: (branchId: string, candidateId: string, abort?: Abortable) =>
    request<Decision[]>(`/api/decisions/${encode(branchId)}/${encode(candidateId)}/history`, {
      abort,
    }),

  // Grounded follow-up questions -----------------------------------------------------------
  conversations: (reviewId: string, abort?: Abortable) =>
    request<ReviewConversation[]>(`/api/review-conversations?review_id=${encode(reviewId)}`, {
      abort,
    }),
  createConversation: (reviewId: string) =>
    request<ReviewConversation>("/api/review-conversations", {
      method: "POST",
      body: JSON.stringify({ review_id: reviewId }),
    }),
  deleteConversation: (conversationId: string) =>
    request<void>(`/api/review-conversations/${encode(conversationId)}`, { method: "DELETE" }),
  ask: (conversationId: string, question: string) =>
    request<ReviewConversation>(`/api/review-conversations/${encode(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ question }),
      timeout: NO_TIMEOUT,
    }),
};
