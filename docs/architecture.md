# Architecture

## Dependency direction

The domain contains validated application data and explicit errors. Ports describe persistence,
repository analysis, source/freshness checks, retrieval, reasoning, and report output.
Application services and workflows depend on domain contracts and cohesive ports. Adapters
implement ports. The CLI is a thin presentation adapter. `bootstrap.py` is the composition root
and the only module that chooses providers.

```mermaid
flowchart LR
    PRESENTATION[Typer CLI / local FastAPI + React] --> BOOT[Composition root]
    PRESENTATION --> APP[Application services and workflows]
    APP --> DOMAIN[Domain models]
    APP --> PORTS[Ports]
    ADAPTERS[SQLite / AST / sqlite-vec / Ollama adapters] --> PORTS
    ADAPTERS --> DOMAIN
    BOOT --> APP
    BOOT --> ADAPTERS
```

The domain, application, workflow, and port packages do not import Typer, HTTPX, SQLite,
`sqlite-vec`, or adapter implementations. Structural tests enforce this boundary and ensure CLI
commands use application services instead of concrete repositories, analyzers, or stores.

## Responsibilities

- Domain: immutable schemas, IDs, classifications, source locations, and errors.
- Application: case, policy-source/index, repository-index, fresh-atlas-query, advice, report,
  report-conversation planning/retrieval/context/validation, run, workspace-initialization,
  safety, and evidence-validation use cases.
- Workflows: the unified consultation sequence and its audit/failure envelope.
- Ports: narrow model/reasoning, atlas/source/freshness, policy, persistence, and reporting
  interfaces.
- Persistence adapters: connection lifecycle, migrations, immutable revisions and versions.
- Repository adapters: one-snapshot Python parsing, graph metrics, safe source reads, and
  deterministic typed queries.
- Retrieval adapters: policy parsing, chunking, embeddings, and vector search.
- Model adapters: structured reasoning tasks, closed-set reference mapping, and embeddings.
- Presentation: input validation, application-service calls, output, and exit behavior only.

The local web adapter adds no alternate domain path. FastAPI routes call the same application
services as the CLI, while the React bundle consumes JSON and server-sent progress events from
that adapter. A single-worker application queue fixes a run ID and input case revision before
calling the consultation workflow.

Report-conversation access remains in the CLI and local FastAPI routes. The retained React
workspace has no report-conversation or generic chat controls in V1.2.

Model transport is bounded and explicit. Before any request is sent, the Ollama adapter
estimates the serialized prompt plus the response schema against the context window and
refuses with `PromptBudgetExceededError` when the request cannot fit, naming the stage and
both sizes; Ollama would otherwise truncate from the front and discard the system prompt,
producing degraded output that fails validation with no attributable cause. Transport
failures that a later identical request might survive — timeouts, network and remote
protocol errors, proxy errors, 408/429/5xx — are retried up to three times with
exponential backoff. Configuration faults and structured-output failures are never
retried; the single sanctioned schema-repair round remains the only second attempt at
content. Stages are timed by class, with the single configured timeout as the fallback so
a workspace written before the classes existed behaves identically.

Heavyweight or provider-specific behavior is constructed explicitly. Imports have no side effects.
The packaged model configuration is a resource; workspace initialization copies it only when the
selected configuration path does not exist.

Persisted-report conversations use the same dependency direction. The application builds a
bounded planning dossier from compact finding digests, the exact pinned case summary, the current
typed summary, and recent message views. It resolves finding references, validates at most eight
discriminated retrieval actions, applies all evidence ceilings cumulatively across the turn, and
executes only against the run's exact case/Atlas/policy pins.

Retrieval returns a transient evidence payload for reasoning and a separate lightweight audit
record for persistence. The transient `ReportConversationContext` preserves exact relationship
edges, dependency-path order, tests, concern implications, query summaries, excerpts, and
unavailable reasons without containing an `Atlas` aggregate, repository root, source tree, full
policy corpus, or unlimited history. Durable message rows retain ordered scoped artifact
references, actual supplied IDs, truncation metadata, recent-message ordinals, summary revision,
and a canonical context hash; they do not duplicate findings, claims, Atlas query results, or
policy documents.

The narrow `ReportConversationReasoner` receives only provider-neutral typed dossiers. The
application owns reference resolution, exact artifact scope, cumulative budgets, validation,
repair allowlists, rendering, and summary coverage. Model adapters serialize the same canonical
JSON used for hashes and do not choose evidence, history, citation, or truncation rules. A
structural test enforces that direction: `adapters/models` may not import the application or
workflow packages.

Domain rules have one implementation. Whether a cited source span is supported by a surfaced
node is decided by `domain/evidence_rules.py`, used by concern-analysis validation in the
workflow, report and conversation evidence validation in the application, and claim-survival
checks in the Ollama adapter. A structural test fails if a hand-rolled containment check
reappears. Reasoning stages are named once by the `ReasoningTask` enum rather than by repeated
string literals, and the enum is asserted to match the prompt registry.

A finding's evidence is scoped by ownership rather than by absence. A claim owned by another
concern cluster is foreign and rejected; a claim owned by no cluster — a case statement, an
advisor claim — belongs to the consultation, so any finding may rest on it. Every finding must
still cite at least one claim from its own cluster, and an ID absent from the report's claim
registry is rejected as unknown before scope is considered. See
[adr/0005-scope-of-finding-evidence-and-typed-importance.md](adr/0005-scope-of-finding-evidence-and-typed-importance.md).

`bootstrap.Runtime` names its dependencies by port, so nothing outside the composition root
depends on a concrete SQLite, AST, or vector-store type. Conversation adapters and services are
composed only in `bootstrap.py`.

## Information flow

Global context remains concise. Detailed code is requested only through a validated
`AtlasQueryPlan`; the query executor bounds types, IDs, result sizes, depth, and source excerpts.
Design forces are partitioned into validated concern clusters, and detailed results are assembled
into one focused packet per cluster under cumulative node and excerpt budgets. Final synthesis
receives the case, global context, forces, concern analyses, alternatives, scenarios, and a pool
of citable claims under request-local handles. Focused packets remain internal evidence
allowlists and are not sent to synthesis. The model never receives an `Atlas` aggregate,
repository root, or complete source tree.

Synthesis returns a `ProposedRecommendation`, not a report. The proposal carries the disposition,
prose, findings, and the claim handles that support them; it has no field for design forces,
alternatives, scenarios, policy evidence, claim identity, section placement, or finding evidence,
because ArchCompass owns all of those. `application/synthesis.py` composes the persisted report by
resolving handles, placing claims into sections by classification, assigning content-derived claim
IDs, and injecting the workflow's canonical artifacts. See
[adr/0001-composed-synthesis.md](adr/0001-composed-synthesis.md).

Embedding retrieval and exact reference selection are intentionally separate. Policies are an
open corpus, so their sections are embedded and retrieved before the original text is supplied to
reasoning. The force list at clustering is already complete and bounded, so the adapter uses
schema-constrained request-local handles and deterministic mapping instead of vector similarity.
