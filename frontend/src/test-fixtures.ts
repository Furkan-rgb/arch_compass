import type {
  Finding,
  Investigation,
  ModelCatalog,
  EmbeddingCatalog,
  PolicyDocument,
  Review,
  ReviewRun,
  ReviewSummary,
  Workspace,
} from "./api";

/**
 * The repository a review names, as the wire says it.
 *
 * Exported as a builder rather than kept as one constant, because a lineage is a branch and
 * more than one test now needs a *second* repository to tell one line of work from another.
 * Building the second one by hand next to this file is how two notions of a repository get
 * into one suite, which is the shape of the fault this fixture set is used to pin.
 */
export function repositoryFixture(
  overrides: Partial<Review["repository"]> = {},
): Review["repository"] {
  return {
    id: "repo-1",
    path: "/work/payments-platform",
    branch_id: "branch-1",
    content_id: "content-1",
    remote_url: null,
    branch: "main",
    commit: "8f31c2a91b4d",
    ...overrides,
  };
}

const repository = repositoryFixture();

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
      participants: [
        { qualified_name: "domain.orders", role: "source", node_id: `node-${candidateId}` },
      ],
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
    investigation_identity: "",
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

  // The atlas names the same checkout the review does. Overriding one and leaving the other
  // pointing at the default made a review of a second repository carry the first one's atlas.
  const named = overrides.repository ?? repository;

  return {
    id: "review-1",
    sequence: 1,
    round: 1,
    status: "awaiting_answers",
    // The round is open *now*, which is a different fact from the status and is why it is
    // stated separately: a snapshot that asked says `awaiting_answers` for ever, and a
    // fixture carrying only that describes a superseded round as a live one.
    answerable: true,
    previous_review_id: null,
    repository: named,
    atlas: {
      id: "atlas-1",
      repository: named,
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
    investigation_manifest: [],
    synopsis: null,
    synopsis_identity: "",
    model_identity: "fake:deterministic",
    prompt_identity: "judge:v1",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    failure: null,
    ...overrides,
  };
}

/**
 * The same review as a listing reads it: counts in place of the collections they count.
 *
 * Kept beside `reviewFixture` rather than derived from it, because the wire shapes are
 * different records and a fixture that computed one from the other would hide a listing
 * that had drifted from the review it lists.
 */
export function reviewSummaryFixture(overrides: Partial<ReviewSummary> = {}): ReviewSummary {
  return {
    id: "review-1",
    sequence: 1,
    round: 1,
    status: "awaiting_answers",
    previous_review_id: null,
    repository,
    case_id: "case-1",
    case_revision: 1,
    answer_count: 0,
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    finding_count: 3,
    material_count: 1,
    held_count: 1,
    cleared_count: 1,
    question_count: 1,
    unchanged_count: 1,
    changed_count: 0,
    new_count: 2,
    addressed_count: 0,
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
    started_at: "2026-01-01T00:00:00Z",
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
        detail: "The openrouter provider needs an API key: set OPENROUTER_API_KEY",
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
      { provider: "google", model: "gemini-3.5-flash-lite", thinking: false, label: "hosted", is_selected: false },
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

export function investigationFixture(
  overrides: Partial<Investigation> = {},
): Investigation {
  return {
    candidate_id: "candidate-1",
    lookups: [
      {
        tool: "search_code",
        arguments: { name: "PersistenceGateway" },
        result: "billing.gateway.PersistenceGateway  [interface]  billing/gateway.py:4-18",
      },
      {
        tool: "related_code",
        arguments: {
          qualified_name: "billing.gateway.PersistenceGateway",
          relation: "implementations",
        },
        result: "1 implementation\n  billing.sql.SqlGateway  [class]  billing/sql.py:9-40",
      },
    ],
    closing: "One implementation, and no test reaches it.",
    withheld: "",
    termination: "natural_end" as const,
    atlas_fingerprint: "content-fingerprint",
    prompt_identity: "investigate-hinge:v1",
    model_identity: "fake:deterministic",
    ...overrides,
  };
}
