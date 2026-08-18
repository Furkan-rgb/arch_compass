import type { Review } from "./api";

export function reviewFixture(overrides: Partial<Review> = {}): Review {
  const candidate = {
    id: "candidate-1",
    pattern: "dependency_direction",
    summary: "Domain depends on an adapter",
    participants: [{ qualified_name: "domain.orders", role: "source" }],
    evidence: [{ description: "Import crosses the boundary", location: { path: "domain/orders.py", start_line: 4, end_line: 4 }, excerpt: "from adapters.db import Store" }],
    measurements: { imports: "1" },
    detection_rationale: "Detected from the repository atlas.",
    limitations: "Static imports only.",
  };
  return {
    id: "review-1",
    sequence: 1,
    status: "awaiting_answers",
    previous_review_id: null,
    repository: { id: "repo-1", path: "/work/repository", branch_id: "branch-1", content_id: "content-1", remote_url: null, branch: "main", commit: "abcdef123456" },
    atlas: { id: "atlas-1", repository: { id: "repo-1", path: "/work/repository", branch_id: "branch-1", content_id: "content-1", remote_url: null, branch: "main", commit: "abcdef123456" }, node_count: 12, edge_count: 18, metric_count: 4, fact_count: 3, signal_count: 1, parser_configuration: { parser: "python-ast" } },
    case: { id: "case-1", revision: 1, goal: "Keep the domain independent", constraints: [], decisions: [], answers: [], created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
    findings: [{ candidate, verdict: "held", reasoning: "Ownership determines whether this dependency is intentional.", policies: [{ policy_id: "dependency-direction", policy_title: "Dependencies point inward", reasoning: "The import may reverse the intended direction." }], evidence: candidate.evidence, hinge: "Who owns persistence?", recommended_response: null, reused_from_review_id: null, model_identity: "fake:deterministic", prompt_identity: "judge:v1", retrieval_identity: "retrieval-1" }],
    questions: [{ id: "question-1", text: "Who owns persistence?", facet: "decision", candidate_ids: ["candidate-1"], round: 1, equivalence_key: "decision:candidate-1" }],
    delta: { unchanged: [], changed: [], new: ["candidate-1"], addressed: [] },
    retrieval_manifest: [{ candidate_id: "candidate-1", retriever: "dense-scoped", version: "1-k8", corpus_fingerprint: "corpus-fingerprint", selected_policy_ids: ["dependency-direction"], model_identity: "google:text-embedding", query_fingerprint: "query-fingerprint", metadata: { top_k: "8" } }],
    markdown_report: null,
    model_identity: "fake:deterministic",
    prompt_identity: "judge:v1",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    failure: null,
    ...overrides,
  };
}
