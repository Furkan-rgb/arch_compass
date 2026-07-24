# ArchCompass

**Context-aware software architecture advice grounded in requirements, repository evidence, design policy and expected change.**

ArchCompass is a local-first software architecture advisor for developers and coding agents. It helps answer not only _how to implement a feature_, but **how the surrounding software should be structured so that it remains understandable and changeable over time**.

The project is built around a simple observation: AI-assisted coding is making it much easier to produce working code, but it does not remove the harder problem of managing complexity. A system can function correctly today while still being difficult to understand, expensive to modify and fragile under future requirements.

ArchCompass is intended to help with that problem.

---

## Why ArchCompass Exists

Modern coding agents can quickly generate features, patches and entire applications. They are often effective at making a test pass or connecting several components into a working flow.

However, a working implementation is not automatically a good design.

Questions such as these still require architectural judgement:

- Where should this responsibility live?
- Which concepts are stable, and which are implementation details?
- Is a new abstraction justified?
- Is provider-specific knowledge leaking into the rest of the application?
- How many parts of the system will need to change when this decision changes?
- Is complexity being removed, or merely spread across more files?
- Does an interface simplify the system, or only add another layer?
- Which future requirements are credible enough to design for now?

These decisions become more important as generating code becomes cheaper. The value increasingly lies in **containing complexity, limiting change amplification and making important relationships easy to discover**.

ArchCompass gives the developer and coding agent a persistent, evidence-backed architecture context in which to make those decisions.

---

## What ArchCompass Does

ArchCompass supports two kinds of consultation through the same workflow.

### Greenfield architecture

When no repository exists yet, ArchCompass reasons from:

- The problem being solved.
- Users and workflows.
- Functional requirements.
- Quality attributes.
- Technical and organisational constraints.
- Expected future changes.
- Non-goals.
- Explicit assumptions.

For example:

> I want to build a local audiobook application using Qwen TTS. It needs voice design, voice cloning, narration, resumable jobs and may support hosted TTS providers later. How should I structure it?

ArchCompass can recommend initial responsibility boundaries, pipeline stages, provider boundaries, state ownership and implementation order.

### Brownfield architecture

When an existing repository is available, ArchCompass adds deterministic repository evidence:

- Packages, modules and symbols.
- Imports and dependency direction.
- Known call relationships.
- Interfaces and implementations.
- Tests and configuration.
- Dependency reach and likely blast radius.
- Structural metrics.
- Obscurity signals.
- Relevant source excerpts.

For example:

> Qwen-specific voice logic currently appears in the frontend, preflight checks and workflow. I may add another TTS provider later. Where should this logic live?

ArchCompass can map the affected area, retrieve the relevant architectural policies and recommend how responsibilities should be moved or preserved.

Repository analysis is optional. Greenfield and brownfield advice are not separate products.

---

## What ArchCompass Is Not

ArchCompass is not:

- A generic chatbot over a repository.
- A code generator.
- A linter that automatically labels patterns as violations.
- A universal maintainability scoring system.
- An autonomous refactoring agent.
- A tool that assumes more interfaces and modules are always better.
- A replacement for human architectural judgement.

A valid ArchCompass recommendation may be:

- Introduce a focused abstraction.
- Move a responsibility behind an existing boundary.
- Keep the implementation local.
- Preserve the current design.
- Delay the decision.
- Gather more information.
- Reject all proposed approaches and recommend another.
- Conclude that no architectural change is justified.

---

## Core Concepts

ArchCompass is organised around five durable concepts.

### ArchitectureCase

An `ArchitectureCase` is the persistent, revisioned context for one architectural decision.

It contains:

- The problem and desired outcome.
- Requirements and quality attributes.
- Constraints and non-goals.
- Future plans.
- Confirmed facts.
- Derived constraints.
- Assumptions.
- Unresolved questions.
- Design forces.
- Candidate alternatives.
- The current recommendation.
- Confidence.
- Reversal conditions.
- Revisit triggers.

An ArchitectureCase is not a temporary prompt. It evolves as new information is discovered and as the system is implemented.

Every revision is preserved.

### RepositoryAtlas

A `RepositoryAtlas` is a deterministic, versioned map of an existing Python repository.

The atlas contains nodes such as:

- Repositories.
- Packages.
- Modules.
- Classes.
- Functions and methods.
- Protocols and abstract interfaces.
- Test modules and test functions.
- Configuration files and modules.

It records relationships such as:

- Containment.
- Imports.
- Calls.
- Inheritance.
- Interface implementations.
- References.
- Test relationships.
- Configuration relationships.

The analysed repository is never imported, executed or modified.

### PolicyCorpus

The `PolicyCorpus` contains reusable architectural guidance.

Policies may be:

- General software-design guidance.
- User-authored preferences.
- Team or organisation standards.
- Repository-specific conventions.
- Guidance derived from accepted architecture decisions.

A policy contains more than a slogan. It includes:

- Intent.
- Guidance.
- Signals.
- Diagnostic questions.
- Likely consequences.
- Exceptions.
- Positive examples.
- Counterexamples.
- Related policies.

Policies guide reasoning. They do not automatically determine the answer.

### ConsultationRun

A `ConsultationRun` is an immutable record of one advisory execution.

It records:

- The exact ArchitectureCase revision.
- The RepositoryAtlas version, when present.
- The policy-index version.
- Model and prompt identities.
- Design forces.
- Atlas queries and focused evidence.
- Retrieved policies.
- Alternatives.
- Scenario analysis.
- The final report.
- Evidence-validation results.
- Execution metadata.

This makes recommendations reproducible and auditable.

### ReportConversation

A `ReportConversation` is an append-only discussion pinned to one successful
`ConsultationRun`. It preserves the exact case revision, atlas version, and policy-index version.
Each turn sends all compact finding digests plus the exact pinned problem, desired outcome,
workflows, requirements, constraints, facts, future changes, non-goals, and assumptions; detailed
finding evidence remains question-specific. Messages retain the validated retrieval plan, exact
artifact evidence scopes, model/prompt identities, and context hash used for the answer. Factual
answer statements carry validated support links. A conversation never revises the case or rewrites
the historical recommendation.

Questions resolve findings by canonical ID, exact title, numeric or word ordinal, or an
unambiguous recent reference. Deterministic handling covers report and finding summaries,
all-finding qualitative priority, comparisons, evidence and source traces, policy applicability
and exceptions, alternatives, scenarios, assumptions, implementation order, strengthening or
weakening counterfactuals, and unsupported questions. Typed rolling summaries retain narrative,
discussed finding/evidence IDs, and source-ordinal-linked user corrections, hypotheticals, and
unresolved questions in a first batch of 12 messages and fixed batches of 8 thereafter.

---

## How It Works

The current advisory flow is:

```text
Question, requirement or proposed change
                    │
                    ▼
             ArchitectureCase
                    │
                    ▼
          Discover design forces
                    │
                    ├── no repository: use case context
                    │
                    └── repository: query RepositoryAtlas
                    │
                    ▼
          Retrieve relevant policies
                    │
                    ▼
         Analyse focused evidence
                    │
                    ▼
       Generate credible alternatives
                    │
                    ▼
   Evaluate future scenarios and trade-offs
                    │
                    ▼
      Synthesize one recommendation and ADR
                    │
                    ▼
        Validate every evidence reference
                    │
                    ▼
 Persist ConsultationRun and update the case
```

Repository exploration is bounded and progressive. The model does not receive the complete source tree or raw atlas.

Instead, it begins with concise context and requests focused information such as:

```text
repository
  → package
    → module
      → symbol
        → dependencies, callers, tests and excerpts
```

This reduces model overload and prevents the model from having to reconstruct the repository structure from raw code.

---

## Repository Mapping and Complexity

ArchCompass is influenced by the distinction between two broad causes of software complexity:

- **Dependencies:** code cannot be understood or changed in isolation.
- **Obscurity:** important information or relationships are difficult to discover.

These can result in:

- Change amplification.
- Increased cognitive load.
- Unknown dependencies and consequences.

ArchCompass cannot objectively measure how difficult code feels to a human. It therefore reports separate structural dimensions and explicit proxies rather than inventing one universal complexity score.

### Local structural metrics

Examples include:

- Physical lines.
- Logical statements.
- Branch count.
- Maximum nesting depth.
- Parameter count.
- Public API surface.
- Imported modules.
- Known incoming and outgoing calls.

### Dependency metrics

Examples include:

- Fan-in and fan-out.
- Direct dependencies and dependants.
- Forward and reverse dependency reach.
- Dependency depth.
- Cycles.
- Interface implementations.
- Associated tests.

### Change-amplification proxies

Examples include:

- Modules likely affected by a change.
- Implementations requiring coordinated updates.
- Configuration locations involved.
- Tests in the reverse dependency neighbourhood.

### Cognitive-scope proxies

Examples include:

- The size of the relevant dependency neighbourhood.
- The number of boundaries involved.
- Related configuration locations.
- Local control-flow complexity.
- Public API surface.

### Obscurity signals

Examples include:

- Wildcard imports.
- Dynamic imports.
- Module-level mutable state.
- Cyclic dependencies.
- Duplicate constants.
- Unresolved static calls.
- Public callables without documentation.
- Important behaviour distributed across multiple locations.

These are signals for architectural interpretation, not automatic design failures.

A module may be locally complicated while still improving the system by hiding that complexity behind a simple interface.

---

## Policy Retrieval

ArchCompass uses embeddings and `sqlite-vec` to retrieve relevant architectural policies.

At index-build time:

```text
Policy Markdown
    → validate metadata and sections
    → create section-aware chunks
    → generate embeddings
    → store versioned vectors in sqlite-vec
```

At consultation time:

```text
Design forces and architectural concern
    → retrieval query
    → query embedding
    → nearest policy sections
    → original policy text and metadata
    → architectural reasoning
```

Embeddings are used only for retrieval.

The reasoning model receives the original policy text, policy ID, scope and strength. It does not receive the numerical vectors.

A recommendation may cite only policies that were actually retrieved.

---

## Evidence Discipline

Every important claim in an ArchCompass report is classified as one of:

- Confirmed user requirement.
- Derived constraint.
- Repository observation.
- Policy guidance.
- Scenario assumption.
- Advisor inference.

Repository observations must reference atlas nodes that were surfaced during the consultation.

Policy-guidance claims must reference policies retrieved for the run.

Unsupported or invented references are rejected. ArchCompass permits one constrained repair attempt. If validation still fails, the consultation fails and the ArchitectureCase is not updated.

This separation is central to the project:

```text
Deterministic code maps, measures and validates.
Language models interpret, compare and advise.
```

---

## Recommendation Output

ArchCompass produces validated JSON and deterministic Markdown from the same report model.

A report contains:

1. Decision summary.
2. Problem and desired outcome.
3. Confirmed context.
4. Assumptions and unresolved questions.
5. Important design forces.
6. Canonical architectural findings.
7. Repository observations and quantified signals.
8. Relevant policies.
9. Recommended architecture.
10. Responsibility allocation.
11. Conceptual interfaces.
12. Alternatives considered.
13. Scenario analysis.
14. Change-amplification and blast-radius analysis.
15. Trade-offs.
16. Implementation sequence.
17. Confidence and rationale.
18. Reversal conditions.
19. Revisit triggers.
20. ADR-style decision record.
21. Evidence appendix.

Reports are saved under:

```text
reports/<run-id>.json
reports/<run-id>.md
```

---

## Current V1.2 Capabilities

The current implementation includes:

- Persistent, append-only ArchitectureCase revisions.
- Immutable ConsultationRun records.
- Python repository analysis using the built-in AST.
- Versioned RepositoryAtlas storage.
- Structural nodes, edges, metrics and obscurity signals.
- Bounded atlas queries and source excerpts.
- Markdown policy parsing and validation.
- Section-aware embedding retrieval through `sqlite-vec`.
- Configurable Ollama reasoning and embedding providers.
- Deterministic fake providers for tests and evaluations.
- Evidence-reference validation.
- One constrained report-repair attempt.
- Stable canonical findings with contextual importance, confidence, response, uncertainty, and
  exact application-projected focused-packet evidence.
- Durable report conversations pinned to one validated successful run.
- Recent-context-aware conversation classification and cumulative bounded retrieval with
  exact-artifact original-run versus additional-conversation evidence labels.
- Support-linked structured answer validation, one constrained repair, complete failed-attempt
  records, and typed fixed-batch rolling summaries.
- JSON and Markdown reports.
- Conversation CLI and local FastAPI routes; no conversation UI in this milestone.
- Greenfield and brownfield evaluation fixtures.

ArchCompass is currently an experimental V1.2. Report conversations are read-only explanations
of persisted recommendations, not a generic repository agent or a path for changing a case.

---

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A SQLite build supporting loadable extensions
- Optional: a local Ollama service for real-model consultations

ArchCompass defaults to local Ollama models configured in:

```text
config/models.yaml
```

The reasoning model's `context_window_tokens` controls Ollama's total context
window (`num_ctx`), including input and generated output.
`max_output_tokens` separately caps generated output.

The checked-in `config/models.yaml` expects `gemma4:26b`; the packaged fallback copied into a
new workspace expects `gemma4:12b`. Pull the model named by the configuration you use, plus the
embedding model:

```bash
ollama pull gemma4:26b
# Or, for the packaged fallback: ollama pull gemma4:12b
ollama pull embeddinggemma
```

Models are not downloaded automatically.

---

## Installation

Clone the repository and install the locked environment:

```bash
git clone https://github.com/Furkan-rgb/archcompass.git
cd archcompass

uv sync --locked
uv run archcompass init
```

Build the policy index:

```bash
uv run archcompass policies rebuild
```

State is stored locally under:

```text
.archcompass/archcompass.db
```

---

## Quick Start

### Create a greenfield case

Use the included audiobook example:

```bash
uv run archcompass case create \
  --from eval/cases/audiobook-greenfield/case.yaml
```

The command returns a case ID.

Inspect the case:

```bash
uv run archcompass case show <case-id>
```

Run a consultation:

```bash
uv run archcompass advise <case-id>
```

Print JSON instead of Markdown:

```bash
uv run archcompass advise <case-id> --json
```

### Analyse an existing repository

Index a Python repository:

```bash
uv run archcompass repo index /path/to/repository
```

Inspect its high-level atlas summary:

```bash
uv run archcompass atlas summary /path/to/repository
```

Show structural hotspots:

```bash
uv run archcompass atlas hotspots /path/to/repository \
  --metric reverse-dependency-reach
```

Run a brownfield consultation:

```bash
uv run archcompass advise <case-id> \
  --repo /path/to/repository
```

### Update a case

Create a partial YAML update and apply it:

```bash
uv run archcompass case update <case-id> \
  --from update.yaml
```

Inspect the complete revision history:

```bash
uv run archcompass case history <case-id>
```

### Inspect policies and runs

```bash
uv run archcompass policies list
uv run archcompass policies show <policy-id>
uv run archcompass run show <run-id>
```

### Discuss a completed report

```bash
uv run archcompass conversation create --run <run-id>
uv run archcompass conversation ask <conversation-id> "Which finding is highest priority?"
uv run archcompass conversation history <conversation-id>
uv run archcompass conversation export <conversation-id> --format markdown
```

Use `conversation ask --json` for the canonical structured answer. Conversations can be created
only for successful validated runs. The equivalent local routes are under `/api/conversations`;
their OpenAPI document declares stable problem responses and typed JSON/Markdown exports. V1.2
does not add a React conversation UI. The deprecated follow-up table is retained during migration,
but its old API/UI are unavailable and its rows are not converted.

---

## Architecture

ArchCompass follows an inward dependency direction:

```text
Presentation
    → application services and workflows
        → domain models and ports
            ← adapters
```

The main responsibilities are:

- `domain/` — validated application concepts and explicit errors.
- `ports/` — interfaces for persistence, repository analysis, retrieval and reasoning.
- `application/` — case operations, evidence validation and report rendering.
- `workflows/` — the unified consultation process.
- `adapters/persistence/` — SQLite storage and migrations.
- `adapters/repository/` — AST analysis, graph metrics and deterministic queries.
- `adapters/retrieval/` — policy parsing, embeddings and `sqlite-vec`.
- `adapters/models/` — Ollama and deterministic model providers.
- `presentation/cli/` — command-line input and output.
- `bootstrap.py` — the composition root and only location that selects concrete adapters.

The domain and application layers do not depend on Typer, HTTPX, SQLite, `sqlite-vec` or AST implementation details.

---

## Development

Run all standard checks:

```bash
make check
```

Run the architectural evaluation cases:

```bash
make eval
```

Build the package:

```bash
make build
```

The mandatory test suite uses deterministic embedding and reasoning providers. It does not require a live Ollama service.

Optional model-integration tests are marked separately.

---

## Project Direction

The long-term goal is for ArchCompass to become a persistent architectural reasoning layer around software development.

Potential future stages include:

- Concern-clustered repository investigation.
- Explicit acceptance and supersession of architecture decisions.
- Coding-agent integration.
- Implementation-plan review.
- Branch and diff analysis.
- Architectural drift detection.
- Comparison between repository atlas versions.
- Revisit-trigger evaluation.
- Git co-change evidence.
- Additional programming languages.

These are roadmap directions, not current V1 capabilities.

ArchCompass will continue to avoid a universal complexity score and will not treat design policies as automatic enforcement rules.

---

## Documentation

- [Master plan](docs/master-plan.md)
- [Product definition](docs/product-design.md)
- [Architecture](docs/architecture.md)
- [Domain model](docs/domain-model.md)
- [Repository atlas](docs/repository-atlas.md)
- [Atlas metrics](docs/atlas-metrics.md)
- [Policy format](docs/policy-format.md)
- [Advisory workflow](docs/advisory-workflow.md)
- [Persistence model](docs/persistence-model.md)
- [Report contract](docs/report-contract.md)
- [Report conversations](docs/report-conversations.md)
- [Evaluation methodology](docs/evaluation.md)

---

## License

ArchCompass is licensed under the Apache License 2.0.
