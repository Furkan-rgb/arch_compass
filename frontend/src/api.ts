import type { components } from "./openapi.generated";

type Schema = components["schemas"];

export type Review = Schema["ReviewResponse"];
export type Finding = Schema["FindingResponse"];
export type Question = Schema["QuestionResponse"];
export type Evidence = Schema["EvidenceResponse"];
export type RetrievalProvenance = Schema["RetrievalProvenanceResponse"];
export type PolicyDocument = Schema["PolicyDocument"];
export type DecisionDisposition = Schema["DecisionDisposition"];
export type Decision = Schema["DecisionResponse"];
export type ReviewConversation = Schema["ReviewConversationResponse"];
export type CaseSummary = Schema["archcompass__presentation__web__routes__cases__CaseResponse"];
export type RepositorySummary = Schema["RepositorySummary"];
export type RepositoryBranch = Schema["RepositoryBranch"];
export type BundledExample = Schema["BundledExample"];
export type ModelCatalog = Schema["ModelCatalogResponse"];
export type Workspace = Schema["WorkspaceSummaryResponse"];
export type AtlasQueryResult = Schema["AtlasQueryResult"];

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

export const coreApi = {
  workspace: () => request<Workspace>("/api/workspace"),
  models: () => request<ModelCatalog>("/api/models"),
  selectModel: (provider: string, model: string, thinking: boolean | null) =>
    request<Workspace>("/api/models/selection", {
      method: "PUT",
      body: JSON.stringify({ provider, model, thinking }),
    }),
  reviews: () => request<Review[]>("/api/reviews"),
  review: (id: string) => request<Review>(`/api/reviews/${encodeURIComponent(id)}`),
  reviewSource: (id: string) => request<Evidence[]>(`/api/reviews/${encodeURIComponent(id)}/source`),
  reviewReport: (id: string) => requestText(`/api/reviews/${encodeURIComponent(id)}/report`),
  deleteReview: (id: string) => request<void>(`/api/reviews/${encodeURIComponent(id)}`, { method: "DELETE" }),
  repositories: () => request<RepositorySummary[]>("/api/repositories"),
  checkoutRepository: (url: string, branch: string | null) =>
    request<Schema["RepositoryCheckout"]>("/api/repositories/checkout", {
      method: "POST",
      body: JSON.stringify({ url, branch }),
    }),
  branches: () => request<RepositoryBranch[]>("/api/branches"),
  repositorySummary: (root: string) =>
    request<AtlasQueryResult>(`/api/repositories/summary?root_path=${encodeURIComponent(root)}`),
  exploreRepository: (root: string, terms: string[]) =>
    request<AtlasQueryResult>("/api/repositories/explore", {
      method: "POST",
      body: JSON.stringify({
        root_path: root,
        operation: "search",
        terms,
        limit: 40,
      }),
    }),
  examples: () => request<BundledExample[]>("/api/examples"),
  loadExample: (name: string) =>
    request<Schema["AtlasVersion"]>(`/api/examples/${encodeURIComponent(name)}/load`, { method: "POST" }),
  cases: () => request<CaseSummary[]>("/api/cases"),
  caseHistory: (id: string) => request<CaseSummary[]>(`/api/cases/${encodeURIComponent(id)}/history`),
  createCase: (goal: string) =>
    request<CaseSummary>("/api/cases", {
      method: "POST",
      body: JSON.stringify({ goal, constraints: [], decisions: [], policy_context: {} }),
    }),
  policies: () => request<PolicyDocument[]>("/api/policies"),
  createPolicy: (draft: Schema["PolicyDraft"]) =>
    request<PolicyDocument>("/api/policies", {
      method: "POST",
      body: JSON.stringify(draft),
    }),
  deletePolicy: (id: string) =>
    request<void>(`/api/policies/${encodeURIComponent(id)}`, { method: "DELETE" }),
  startRepository: (root: string, startClean = false) =>
    request<Schema["StartedCaseResponse"]>("/api/repositories/start", {
      method: "POST",
      body: JSON.stringify({ root_path: root, start_clean: startClean }),
    }),
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
  answer: (reviewId: string, answers: Array<{ question_id: string; status: "answered" | "skipped"; value?: string | null }>, stop = false) =>
    request<Review>(`/api/reviews/${encodeURIComponent(reviewId)}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers, stop }),
    }),
  cancel: (reviewId: string) => request<Review>(`/api/reviews/${encodeURIComponent(reviewId)}/cancel`, { method: "POST" }),
  decide: (reviewId: string, candidateId: string, disposition: DecisionDisposition, reasoning: string | null) =>
    request<Decision>("/api/decisions", {
      method: "POST",
      body: JSON.stringify({ review_id: reviewId, candidate_id: candidateId, disposition, author: "user", reasoning }),
    }),
  decisions: (branchId: string) => request<Schema["BranchDecisionsResponse"]>(`/api/branches/${encodeURIComponent(branchId)}/decisions`),
  decisionHistory: (branchId: string, candidateId: string) =>
    request<Decision[]>(`/api/decisions/${encodeURIComponent(branchId)}/${encodeURIComponent(candidateId)}/history`),
  conversations: (reviewId: string) => request<ReviewConversation[]>(`/api/review-conversations?review_id=${encodeURIComponent(reviewId)}`),
  createConversation: (reviewId: string) => request<ReviewConversation>("/api/review-conversations", { method: "POST", body: JSON.stringify({ review_id: reviewId }) }),
  ask: (conversationId: string, question: string) => request<ReviewConversation>(`/api/review-conversations/${encodeURIComponent(conversationId)}/messages`, { method: "POST", body: JSON.stringify({ question }) }),
};
