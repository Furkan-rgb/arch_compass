import type { Finding, Investigation, RetrievalProvenance, Review } from "../../api";

/**
 * One review, written out, so the landing page can show the workbench rather than draw it.
 *
 * The section this feeds used to be a picture: a hand-built copy of the finding surface,
 * kept in this file's place by nothing but somebody remembering to update it. It outlived
 * the thing it was a picture of — the attribution gutter it drew was deleted when the queue
 * and the workbench became one docket — and a landing page showing a component the product
 * no longer has is worse than showing nothing.
 *
 * So the page renders `FindingBody`, the real one, and this is what it renders it from.
 * These are `Review` and `Finding` off the wire, which is the whole point: the shapes are
 * checked by the compiler, and a field the API adds or drops breaks the build here rather
 * than quietly leaving the marketing page a version behind.
 *
 * Nothing here is measured from a repository — the landing page reads nothing from a
 * workspace by design — but everything is shaped like what a real run records, and the three
 * candidates are the same three the hero shows. See `bearings.ts`, which makes the same
 * argument about the specimen in the hero.
 */

const REPOSITORY = {
  id: "repo-payments",
  path: "/work/payments-platform",
  branch_id: "branch-main",
  content_id: "content-8f31c2a",
  remote_url: null,
  branch: "main",
  commit: "8f31c2a91b4d",
};

const GATEWAY: Finding = {
  candidate: {
    id: "candidate-gateway",
    pattern: "sole_implementation",
    summary:
      "The payment provider abstraction carries a single implementation, and the protocol names one provider's error type.",
    participants: [
      {
        qualified_name: "payments.gateway.PaymentGateway",
        role: "the abstraction",
        node_id: "node_gateway",
      },
      {
        qualified_name: "payments.adapters.stripe.StripeGateway",
        role: "the only implementation of it in this repository",
        node_id: "node_stripe",
      },
    ],
    evidence: [],
    measurements: [
      {
        name: "implementations",
        value: 1,
        unit: "",
        nature: "objective_measurement",
        definition: "Classes in this repository that satisfy the protocol.",
        limitations: "Structural satisfaction only; a runtime registration would not be seen.",
      },
      {
        name: "dependants_of_abstraction",
        value: 5,
        unit: "",
        nature: "objective_measurement",
        definition: "Modules outside the package that reference the abstraction.",
        limitations: "Static references only.",
      },
      {
        name: "modules_naming_it_from_outside",
        value: 3,
        unit: "",
        nature: "structural_proxy",
        definition: "Modules in the domain that mention a provider term.",
        limitations: "A name is a proxy for a dependency, not a dependency.",
      },
    ],
    relationships: [
      {
        source: "payments.adapters.stripe.StripeGateway",
        target: "payments.gateway.PaymentGateway",
        kind: "implements",
        resolved_by: "parse",
      },
    ],
    detection_rationale:
      "The atlas records one implementing type for this protocol, and the protocol's own signature mentions a symbol defined in that implementation's package.",
    limitations:
      "A second implementation registered at runtime, or living outside this repository, would not appear in the atlas.",
  },
  verdict: "material",
  reasoning:
    "The port was introduced to keep payment providers replaceable, and it is not doing that. One adapter implements it, and the protocol itself names stripe_retry_after — so a second provider could not satisfy the interface without inheriting Stripe's error vocabulary. The indirection currently costs a hop and buys nothing your guidance asked for.",
  policies: [
    {
      policy_id: "delay-premature-abstraction",
      policy_title: "Delay abstractions until variation is credible",
      reasoning:
        "The variation this abstraction was guessing at never arrived: one implementation, and no second one planned. The policy asks for the seam to be found rather than predicted.",
    },
    {
      policy_id: "design-for-replaceability",
      policy_title: "Design components to be replaceable, not eternal",
      reasoning:
        "Replaceability is the stated reason this port exists, and naming a provider's error type in the interface is what stops it being replaceable.",
    },
  ],
  evidence: [
    {
      description: "The protocol names one provider's error type in its own signature",
      location: { path: "payments/gateway.py", start_line: 12, end_line: 26 },
      excerpt: `class PaymentGateway(Protocol):
    def charge(self, amount: Money, *, idempotency_key: str) -> Charge: ...
    def stripe_retry_after(self, err: StripeError) -> float: ...`,
      note: null,
    },
    {
      description: "The only implementation, which the protocol was shaped around",
      location: { path: "payments/adapters/stripe.py", start_line: 31, end_line: 38 },
      excerpt: `class StripeGateway:
    def charge(self, amount: Money, *, idempotency_key: str) -> Charge:
        return self._client.PaymentIntent.create(...)`,
      note: null,
    },
  ],
  hinge: null,
  recommended_response:
    "Inline the adapter until a second provider is committed, or take the provider's error type out of the interface so the port is one a second provider could satisfy.",
  reused_from_review_id: null,
  model_identity: "google:gemini-3.6",
  prompt_identity: "judge:v1",
  retrieval_identity: "9d41b7c0e5a2f38b6c1d4e7a9058f2b3c6d81e4a7b02c95f3e6a1d84b7c0e529",
  investigation_identity: "",
};

const ORDERS: Finding = {
  candidate: {
    id: "candidate-orders",
    pattern: "dependency_direction",
    summary:
      "The orders domain imports the persistence adapter directly, and two modules outside it write through the same adapter.",
    participants: [
      { qualified_name: "domain.orders", role: "source", node_id: "node_orders" },
      { qualified_name: "adapters.db.Store", role: "target", node_id: "node_store" },
    ],
    evidence: [],
    measurements: [
      {
        name: "dependants_of_abstraction",
        value: 5,
        unit: "",
        nature: "objective_measurement",
        definition: "Modules outside the domain that reach this adapter.",
        limitations: "Static imports only.",
      },
      {
        name: "modules_stating_it",
        value: 2,
        unit: "",
        nature: "objective_measurement",
        definition: "Modules that write through the adapter rather than read from it.",
        limitations: "A write is inferred from the method called, not from what it does.",
      },
    ],
    relationships: [
      { source: "domain.orders", target: "adapters.db.Store", kind: "imports", resolved_by: "parse" },
    ],
    detection_rationale:
      "The atlas has an import edge from a domain module to an adapter module, and the adapter is written to from more than one package.",
    limitations: "Static imports only.",
  },
  verdict: "held",
  reasoning:
    "Five modules outside the domain reach this adapter and two of them write through it, so the state has more than one writer. Whether that breaks the policy depends on which component is meant to own it — and the repository does not say.",
  policies: [
    {
      policy_id: "give-state-one-writer",
      policy_title: "Give every piece of shared state one writing owner",
      reasoning:
        "The policy asks for one writing owner per datum. There are two here, which is the finding; which of them should have been the owner is not something the code records.",
    },
  ],
  evidence: [
    {
      description: "The domain module imports the persistence adapter directly",
      location: { path: "domain/orders.py", start_line: 4, end_line: 4 },
      excerpt: "from adapters.db import Store",
      note: null,
    },
  ],
  hinge: "who owns the adapter — the platform team, or the domain.",
  recommended_response: null,
  reused_from_review_id: null,
  model_identity: "google:gemini-3.6",
  prompt_identity: "judge:v1",
  retrieval_identity: "4c7e1a9b03d5f682e4a7c0b19d3f6528a1b4c7e0d3f69258a1c4b7e0d3f69258",
  investigation_identity: "b2f5c8e1a4d70396b5e8c1a4d70396b5e8c1a4d70396b5e8c1a4d70396b5e8c1",
};

const INVOICE: Finding = {
  candidate: {
    id: "candidate-invoice",
    pattern: "boundary_shape",
    summary:
      "The invoice boundary is the only path to the ledger, and every posting resolves through it.",
    participants: [
      {
        qualified_name: "billing.invoice.InvoiceBoundary",
        role: "the boundary",
        node_id: "node_invoice",
      },
    ],
    evidence: [],
    measurements: [
      {
        name: "modules_naming_it_from_outside",
        value: 7,
        unit: "",
        nature: "objective_measurement",
        definition: "Modules that post through the boundary.",
        limitations: "Static references only.",
      },
    ],
    relationships: [],
    detection_rationale:
      "The atlas shows every write edge to the ledger passing through one module, and no edge going around it.",
    limitations: "Static references only.",
  },
  verdict: "cleared",
  reasoning:
    "Every posting path resolves through this boundary and no other module writes the ledger directly, so the authoritative place is both singular and visible. The seam does exactly what the policy asks of it.",
  policies: [
    {
      policy_id: "explicit-source-of-truth",
      policy_title: "Make the source of truth explicit",
      reasoning:
        "One place defines the ledger's state and everything else is visibly derived from it, which is what the policy asks for.",
    },
  ],
  evidence: [
    {
      description: "The single write path to the ledger",
      location: { path: "billing/invoice.py", start_line: 8, end_line: 14 },
      excerpt: `class InvoiceBoundary:
    def post(self, entry: LedgerEntry) -> Posting:
        return self._ledger.append(entry)`,
      note: null,
    },
  ],
  hinge: null,
  recommended_response: null,
  reused_from_review_id: null,
  model_identity: "google:gemini-3.6",
  prompt_identity: "judge:v1",
  retrieval_identity: "7a0d3f69258c1b4e7a0d3f69258c1b4e7a0d3f69258c1b4e7a0d3f69258c1b4e",
  investigation_identity: "",
};

/** Retrieval pulled several policies for each candidate; only some of them bore. */
const RETRIEVAL: RetrievalProvenance[] = [
  {
    candidate_id: "candidate-gateway",
    retriever: "dense-scoped",
    version: "1-k8",
    corpus_fingerprint: "3f6a1d84b7c0e5299d41b7c0e5a2f38b6c1d4e7a9058f2b3c6d81e4a7b02c95f",
    selected_policy_ids: [
      "delay-premature-abstraction",
      "design-for-replaceability",
      "prefer-deep-modules",
      "contain-dependencies",
      "hide-implementation-details",
      "name-for-meaning",
    ],
    model_identity: "ollama:nomic-embed-text",
    query_fingerprint: "c95f3e6a1d84b7c0",
    metadata: { top_k: "8" },
  },
  {
    candidate_id: "candidate-orders",
    retriever: "dense-scoped",
    version: "1-k8",
    corpus_fingerprint: "3f6a1d84b7c0e5299d41b7c0e5a2f38b6c1d4e7a9058f2b3c6d81e4a7b02c95f",
    selected_policy_ids: [
      "give-state-one-writer",
      "contain-dependencies",
      "explicit-source-of-truth",
      "prefer-deep-modules",
      "keep-effects-at-the-edges",
    ],
    model_identity: "ollama:nomic-embed-text",
    query_fingerprint: "1d84b7c0e5293e6a",
    metadata: { top_k: "8" },
  },
  {
    candidate_id: "candidate-invoice",
    retriever: "dense-scoped",
    version: "1-k8",
    corpus_fingerprint: "3f6a1d84b7c0e5299d41b7c0e5a2f38b6c1d4e7a9058f2b3c6d81e4a7b02c95f",
    selected_policy_ids: [
      "explicit-source-of-truth",
      "prefer-deep-modules",
      "give-state-one-writer",
      "contain-dependencies",
      "delay-premature-abstraction",
      "design-for-replaceability",
      "separate-commands-from-queries",
    ],
    model_identity: "ollama:nomic-embed-text",
    query_fingerprint: "b7c0e5293e6a1d84",
    metadata: { top_k: "8" },
  },
];

/**
 * What the judgement looked up before it decided it could not settle the hinge on its own.
 *
 * This is the fold that separates "the repository is silent" from "nothing checked", and it
 * is the newest thing on the finding surface — which is exactly the kind of thing a picture
 * of the workbench would never have grown.
 */
const INVESTIGATION: Investigation[] = [
  {
    candidate_id: "candidate-orders",
    lookups: [
      {
        tool: "related_code",
        arguments: { node_id: "node_store", kind: "dependants" },
        result: `domain.orders          imports  adapters.db.Store
reporting.exports      imports  adapters.db.Store
platform.migrations    imports  adapters.db.Store
billing.reconcile      imports  adapters.db.Store
ops.backfill           imports  adapters.db.Store`,
      },
      {
        tool: "find_code",
        arguments: { name: "CODEOWNERS" },
        result: "no node in the atlas matches that name",
      },
    ],
    closing:
      "Five modules reach the adapter and two write through it. Nothing in the repository says which component is meant to own it, so the question stands.",
    withheld: "",
    abandoned: "",
    resolved: false,
    atlas_fingerprint: "8f31c2a91b4d0e5a2f38b6c1d4e7a9058f2b3c6d81e4a7b02c95f3e6a1d84b7c",
    prompt_identity: "investigate:v1",
    model_identity: "google:gemini-3.6",
  },
];

/**
 * The review the section shows: three candidates, one of each verdict, one still waiting on
 * a person. `status` is `awaiting_answers` because the held one has an open question against
 * it, which is what makes the surface show the question rather than a settled record.
 */
export const CASE_FILE: Review = {
  id: "review-4",
  sequence: 4,
  round: 1,
  status: "awaiting_answers",
  previous_review_id: "review-3",
  repository: REPOSITORY,
  atlas: {
    id: "atlas-8f31c2a",
    repository: REPOSITORY,
    node_count: 1284,
    edge_count: 3106,
    metric_count: 14,
    fact_count: 9,
    signal_count: 4,
    parser_configuration: { parser: "python-ast" },
  },
  case: {
    id: "case-payments",
    revision: 3,
    answers: [
      {
        question: {
          id: "question-second-provider",
          text: "Is a second payment provider planned this year?",
          facet: "decision",
          candidate_ids: ["candidate-gateway"],
          round: 3,
          equivalence_key: "decision:candidate-gateway",
          options: ["Yes, and it is committed", "No, and none is on the roadmap"],
        },
        status: "answered",
        value: "No, and none is on the roadmap.",
        actor: "priya",
        answered_at: "2026-08-14T09:12:00Z",
      },
      {
        question: {
          id: "question-ledger-owner",
          text: "Which component owns the ledger?",
          facet: "ownership",
          candidate_ids: ["candidate-invoice"],
          round: 2,
          equivalence_key: "ownership:candidate-invoice",
          options: ["Billing owns it", "The platform owns it"],
        },
        status: "answered",
        value: "Billing owns it, and everything else posts through the boundary.",
        actor: "priya",
        answered_at: "2026-07-30T15:40:00Z",
      },
    ],
    created_at: "2026-06-02T10:00:00Z",
    updated_at: "2026-08-14T09:12:00Z",
  },
  findings: [GATEWAY, ORDERS, INVOICE],
  questions: [
    {
      id: "question-adapter-owner",
      text: "Who owns the persistence adapter — the platform team, or the orders domain?",
      facet: "ownership",
      candidate_ids: ["candidate-orders"],
      round: 4,
      equivalence_key: "ownership:candidate-orders",
      options: [
        "The domain owns it and adapters implement its ports",
        "The platform owns it and the domain adapts",
      ],
    },
  ],
  delta: {
    unchanged: ["candidate-invoice"],
    changed: [
      {
        candidate_id: "candidate-gateway",
        causes: ["an answer was recorded against it"],
        predecessor_id: "candidate-gateway",
      },
    ],
    new: ["candidate-orders"],
    addressed: [],
  },
  retrieval_manifest: RETRIEVAL,
  investigation_manifest: INVESTIGATION,
  markdown_report: null,
  synopsis: null,
  synopsis_identity: "",
  model_identity: "google:gemini-3.6",
  prompt_identity: "judge:v1",
  started_at: "2026-08-21T08:30:00Z",
  finished_at: "2026-08-21T08:34:00Z",
  failure: null,
};

/** The row the section opens on: the one with a verdict a reader has to weigh. */
export const LEAD_CANDIDATE_ID = GATEWAY.candidate.id;
