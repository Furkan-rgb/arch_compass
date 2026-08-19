import type { components } from "./openapi.generated";

type Schema = components["schemas"];

export type Review = Schema["ReviewResponse"];
export type Finding = Schema["FindingResponse"];
export type Candidate = Schema["CandidateResponse"];
export type Question = Schema["QuestionResponse"];
export type Evidence = Schema["EvidenceResponse"];
export type RetrievalProvenance = Schema["RetrievalProvenanceResponse"];
export type PolicyDocument = Schema["PolicyDocument"];
export type PolicyDraft = Schema["PolicyDraft"];
export type PolicySourceRegistration = Schema["PolicySourceRegistration"];
export type DecisionDisposition = Schema["DecisionDisposition"];
export type Decision = Schema["DecisionResponse"];
export type ReviewConversation = Schema["ReviewConversationResponse"];
export type CaseSummary = Schema["archcompass__presentation__web__routes__cases__CaseResponse"];
export type ReviewCase = Schema["archcompass__presentation__web__routes__reviews__CaseResponse"];
export type RepositorySummary = Schema["RepositorySummary"];
export type RepositoryBranch = Schema["RepositoryBranch"];
export type RepositoryCheckout = Schema["RepositoryCheckout"];
export type CheckoutRefresh = Schema["CheckoutRefresh"];
export type BundledExample = Schema["BundledExample"];
export type ModelCatalog = Schema["ModelCatalogResponse"];
export type EmbeddingCatalog = Schema["EmbeddingCatalogResponse"];
export type Workspace = Schema["WorkspaceSummaryResponse"];
export type AtlasQueryResult = Schema["AtlasQueryResult"];
export type AtlasNodeSummary = Schema["AtlasNodeSummary"];
export type AtlasVersion = Schema["AtlasVersion"];
export type DirectoryListing = Schema["DirectoryListing"];
export type RepositoryFolderTree = Schema["RepositoryFolderTree"];

export type ReviewProgress = { event: string; review?: Review; message?: string };

async function problem(response: Response): Promise<Error> {
  const detail = (await response.json().catch(() => null)) as
    | { message?: string; field_errors?: string[] }
    | null;
  const suffix = detail?.field_errors?.length ? ` (${detail.field_errors.join("; ")})` : "";
  return new Error(`${detail?.message || `Request failed with ${response.status}`}${suffix}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) throw await problem(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(path);
  if (!response.ok) throw await problem(response);
  return response.text();
}

async function* ndjson(response: Response): AsyncGenerator<ReviewProgress> {
  if (!response.ok) throw await problem(response);
  if (!response.body) throw new Error("The server returned no review stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  while (true) {
    const { done, value } = await reader.read();
    buffered += decoder.decode(value, { stream: !done });
    const lines = buffered.split("\n");
    buffered = lines.pop() || "";
    for (const line of lines) if (line.trim()) yield JSON.parse(line) as ReviewProgress;
    if (done) break;
  }
  if (buffered.trim()) yield JSON.parse(buffered) as ReviewProgress;
}

const encode = encodeURIComponent;

export const coreApi = {
  // Workspace and models -----------------------------------------------------------------
  workspace: () => request<Workspace>("/api/workspace"),
  models: () => request<ModelCatalog>("/api/models"),
  selectModel: (provider: string, model: string, thinking: boolean | null) =>
    request<Workspace>("/api/models/selection", {
      method: "PUT",
      body: JSON.stringify({ provider, model, thinking }),
    }),
  embeddings: () => request<EmbeddingCatalog>("/api/embeddings"),
  selectEmbedding: (provider: string, model: string) =>
    request<Workspace>("/api/embeddings/selection", {
      method: "PUT",
      body: JSON.stringify({ provider, model }),
    }),
  directories: (path?: string) =>
    request<DirectoryListing>(`/api/filesystem/directories${path ? `?path=${encode(path)}` : ""}`),

  // Reviews ------------------------------------------------------------------------------
  reviews: () => request<Review[]>("/api/reviews"),
  review: (id: string) => request<Review>(`/api/reviews/${encode(id)}`),
  reviewSource: (id: string) => request<Evidence[]>(`/api/reviews/${encode(id)}/source`),
  reviewReport: (id: string) => requestText(`/api/reviews/${encode(id)}/report`),
  deleteReview: (id: string) => request<void>(`/api/reviews/${encode(id)}`, { method: "DELETE" }),
  startReview: (caseId: string, root: string) =>
    request<Review>("/api/reviews", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId, repository_root: root }),
    }),
  streamReview: async function* (caseId: string, root: string): AsyncGenerator<ReviewProgress> {
    const response = await fetch("/api/reviews/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId, repository_root: root }),
    });
    yield* ndjson(response);
  },
  answer: (
    reviewId: string,
    answers: Array<{ question_id: string; status: "answered" | "skipped"; value?: string | null }>,
    stop = false,
  ) =>
    request<Review>(`/api/reviews/${encode(reviewId)}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers, stop }),
    }),
  cancel: (reviewId: string) =>
    request<Review>(`/api/reviews/${encode(reviewId)}/cancel`, { method: "POST" }),

  // Repositories -------------------------------------------------------------------------
  repositories: () => request<RepositorySummary[]>("/api/repositories"),
  branches: () => request<RepositoryBranch[]>("/api/branches"),
  checkoutRepository: (url: string, branch: string | null) =>
    request<RepositoryCheckout>("/api/repositories/checkout", {
      method: "POST",
      body: JSON.stringify({ url, branch }),
    }),
  refreshRepository: (root: string) =>
    request<CheckoutRefresh>("/api/repositories/refresh", {
      method: "POST",
      body: JSON.stringify({ root_path: root }),
    }),
  indexRepository: (root: string) =>
    request<AtlasVersion>("/api/repositories/index", {
      method: "POST",
      body: JSON.stringify({ root_path: root }),
    }),
  repositorySummary: (root: string) =>
    request<AtlasQueryResult>(`/api/repositories/summary?root_path=${encode(root)}`),
  repositoryHotspots: (root: string, metric = "reverse_dependency_reach") =>
    request<AtlasQueryResult>(
      `/api/repositories/hotspots?root_path=${encode(root)}&metric=${encode(metric)}`,
    ),
  inspectNode: (root: string, nodeId: string) =>
    request<AtlasQueryResult>(
      `/api/repositories/inspect?root_path=${encode(root)}&node_id=${encode(nodeId)}`,
    ),
  exploreRepository: (
    root: string,
    body: Partial<Schema["AtlasExploreRequest"]> & { operation: Schema["AtlasExploreRequest"]["operation"] },
  ) =>
    request<AtlasQueryResult>("/api/repositories/explore", {
      method: "POST",
      body: JSON.stringify({ root_path: root, limit: 40, ...body }),
    }),
  searchAtlas: (root: string, terms: string[]) =>
    coreApi.exploreRepository(root, { operation: "search", terms }),
  startRepository: (root: string, startClean = false) =>
    request<Schema["StartedCaseResponse"]>("/api/repositories/start", {
      method: "POST",
      body: JSON.stringify({ root_path: root, start_clean: startClean }),
    }),

  // Examples -----------------------------------------------------------------------------
  examples: () => request<BundledExample[]>("/api/examples"),
  loadExample: (name: string) =>
    request<AtlasVersion>(`/api/examples/${encode(name)}/load`, { method: "POST" }),

  // Cases --------------------------------------------------------------------------------
  cases: () => request<CaseSummary[]>("/api/cases"),
  caseHistory: (id: string) => request<CaseSummary[]>(`/api/cases/${encode(id)}/history`),
  createCase: (goal: string) =>
    request<CaseSummary>("/api/cases", {
      method: "POST",
      body: JSON.stringify({ goal, constraints: [], decisions: [], policy_context: {} }),
    }),
  updateCase: (id: string, patch: Schema["CasePatch"]) =>
    request<CaseSummary>(`/api/cases/${encode(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // Policies -----------------------------------------------------------------------------
  policies: () => request<PolicyDocument[]>("/api/policies"),
  policySources: () => request<PolicySourceRegistration[]>("/api/policies/sources"),
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
  decisions: (branchId: string) =>
    request<Schema["BranchDecisionsResponse"]>(`/api/branches/${encode(branchId)}/decisions`),
  decisionHistory: (branchId: string, candidateId: string) =>
    request<Decision[]>(`/api/decisions/${encode(branchId)}/${encode(candidateId)}/history`),

  // Grounded follow-up questions -----------------------------------------------------------
  conversations: (reviewId: string) =>
    request<ReviewConversation[]>(`/api/review-conversations?review_id=${encode(reviewId)}`),
  createConversation: (reviewId: string) =>
    request<ReviewConversation>("/api/review-conversations", {
      method: "POST",
      body: JSON.stringify({ review_id: reviewId }),
    }),
  ask: (conversationId: string, question: string) =>
    request<ReviewConversation>(`/api/review-conversations/${encode(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
