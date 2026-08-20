import type {
  Finding,
  ModelCatalog,
  EmbeddingCatalog,
  PolicyDocument,
  Review,
  ReviewRun,
  Workspace,
} from "./api";

const repository = {
  id: "repo-1",
  path: "/work/payments-platform",
  branch_id: "branch-1",
  content_id: "content-1",
  remote_url: null,
  branch: "main",
  commit: "8f31c2a91b4d",
};

function finding(overrides: Partial<Finding> & { candidateId: string }): Finding {
  const { candidateId, ...rest } = overrides;
  const evidence = [
    {
      description: "The domain module imports the persistence adapter directly",
      location: { path: "domain/orders.py", start_line: 4, end_line: 4 },
      excerpt: "from adapters.db import Store",
      note: null,
    },
  ];
  return {
    candidate: {
      id: candidateId,
      pattern: "dependency_direction",
      summary: "Domain depends on an adapter",
      participants: [{ qualified_name: "domain.orders", role: "source" }],
      evidence,
      measurements: [
        {
          name: "imports",
          value: 1,
          unit: "imports",
          nature: "objective_measurement",
          definition: "Static imports of the adapter from the domain module.",
          limitations: "Static imports only.",
        },
      ],
      relationships: [
        {
          source: "domain.orders",
          target: "adapters.db.Store",
          kind: "imports",
          resolved_by: "parse",
        },
      ],
      detection_rationale: "Detected from the repository atlas.",
      limitations: "Static imports only.",
    },
    verdict: "held",
    reasoning: "Ownership determines whether this dependency is intentional.",
    policies: [
      {
        policy_id: "dependency-direction",
        policy_title: "Dependencies point inward",
        reasoning: "The import may reverse the intended direction.",
      },
    ],
    evidence,
    hinge: "Who owns persistence?",
    recommended_response: null,
    reused_from_review_id: null,
    model_identity: "fake:deterministic",
    prompt_identity: "judge:v1",
    retrieval_identity: "retrieval-1",
    ...rest,
  };
}

export function reviewFixture(overrides: Partial<Review> = {}): Review {
  const held = finding({ candidateId: "candidate-1" });
  const material = finding({
    candidateId: "candidate-2",
    verdict: "material",
    hinge: null,
    recommended_response: "Introduce a port owned by the domain.",
  });
  material.candidate.pattern = "sole_implementation";
  material.candidate.summary = "The provider abstraction carries one implementation";
  const cleared = finding({ candidateId: "candidate-3", verdict: "cleared", hinge: null });
  cleared.candidate.pattern = "boundary_shape";
  cleared.candidate.summary = "The invoice boundary is appropriate";

  return {
    id: "review-1",
    sequence: 1,
    status: "awaiting_answers",
    previous_review_id: null,
    repository,
    atlas: {
      id: "atlas-1",
      repository,
      node_count: 128,
      edge_count: 214,
      metric_count: 12,
      fact_count: 7,
      signal_count: 3,
      parser_configuration: { parser: "python-ast" },
    },
    case: {
      id: "case-1",
      revision: 1,
      goal: "Keep the domain independent of delivery mechanisms",
      constraints: [{ text: "Stripe is the only provider today", facet: "constraint", source: null }],
      decisions: [{ text: "Provider code stays at the infrastructure edge", source: null }],
      answers: [],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    findings: [cleared, held, material],
    questions: [
      {
        id: "question-1",
        text: "Who owns persistence?",
        facet: "decision",
        candidate_ids: ["candidate-1"],
        round: 1,
        equivalence_key: "decision:candidate-1",
        options: [
          "The domain owns it and adapters implement its ports",
          "The persistence layer owns it and the domain adapts",
        ],
      },
    ],
    delta: { unchanged: ["candidate-3"], changed: [], new: ["candidate-1", "candidate-2"], addressed: [] },
    retrieval_manifest: [
      {
        candidate_id: "candidate-1",
        retriever: "dense-scoped",
        version: "1-k8",
        corpus_fingerprint: "corpus-fingerprint",
        selected_policy_ids: ["dependency-direction"],
        model_identity: "ollama:nomic-embed-text",
        query_fingerprint: "query-fingerprint",
        metadata: { top_k: "8" },
      },
    ],
    markdown_report: null,
    model_identity: "fake:deterministic",
    prompt_identity: "judge:v1",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    failure: null,
    ...overrides,
  };
}

/** A run that has begun and has no review yet, as the listings show it. */
export function runFixture(overrides: Partial<ReviewRun> = {}): ReviewRun {
  return {
    run_id: "thread-9",
    status: "running",
    review_id: null,
    failure: "",
    sequence: 2,
    stage: "judge_candidate",
    stages: ["load_context", "analyze_repository", "judge_candidate"],
    repository_name: "payments-platform",
    repository_root: "/work/payments-platform",
    branch_name: "main",
    branch_id: "branch-1",
    case_id: "case-1",
    ...overrides,
  };
}

export function policyFixture(overrides: Partial<PolicyDocument> = {}): PolicyDocument {
  return {
    id: "dependency-direction",
    title: "Dependencies point inward",
    description: "Domain code should not import its adapters.",
    scope: "general",
    applies_to: null,
    strength: "required",
    tags: ["boundaries", "domain"],
    source: { author: "ArchCompass", inspiration: [] },
    body: "## When this applies\n\nDomain modules **must not** import adapters.\n\n- Ports belong to the domain\n- Adapters implement them\n",
    source_path: "policies/dependency-direction.md",
    content_hash: "abc123def456789",
    origin: "external",
    ...overrides,
  };
}

export function workspaceFixture(overrides: Partial<Workspace> = {}): Workspace {
  return {
    workspace: "/home/engineer/.archcompass",
    models: {
      reasoning: { provider: "fake", model: "deterministic", thinking: null },
      embedding: { provider: "ollama", model: "nomic-embed-text", dimensions: 768 },
      pinned: false,
      embedding_pinned: false,
    },
    hosted: false,
    source_hosts: [],
    ...overrides,
  };
}

export function modelCatalogFixture(): ModelCatalog {
  return {
    providers: [
      {
        provider: "ollama",
        label: "Ollama",
        available: true,
        detail: "",
        probed_at: "2026-01-01T00:00:00Z",
      },
      {
        provider: "groq",
        label: "Groq",
        available: true,
        detail: "",
        probed_at: "2026-01-01T00:00:00Z",
      },
      {
        provider: "google",
        label: "Google",
        available: false,
        detail: "The google provider needs an API key: set GOOGLE_API_KEY",
        probed_at: "2026-01-01T00:00:00Z",
      },
    ],
    candidates: [
      { provider: "ollama", model: "qwen3:8b", thinking: true, label: "local", is_selected: true },
      {
        provider: "groq",
        model: "openai/gpt-oss-120b",
        thinking: null,
        label: "GPT-OSS 120B",
        is_selected: false,
      },
      { provider: "google", model: "gemini-3.6-flash", thinking: false, label: "hosted", is_selected: false },
    ],
  };
}

export function embeddingCatalogFixture(): EmbeddingCatalog {
  return {
    providers: [
      {
        provider: "ollama",
        label: "Ollama",
        available: true,
        detail: "",
        probed_at: "2026-01-01T00:00:00Z",
      },
    ],
    candidates: [
      {
        provider: "ollama",
        model: "nomic-embed-text",
        dimensions: 768,
        label: "local",
        is_selected: true,
      },
    ],
  };
}
