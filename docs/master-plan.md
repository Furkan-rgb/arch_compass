# ArchCompass Master Plan

**Status:** Living architecture document
**Authority:** Product direction and architectural ground truth
**Project:** ArchCompass
**Repository:** `Furkan-rgb/archcompass`

## 1. Purpose of This Document

This document records the long-term product vision, architectural principles, central domain concepts and planned development sequence for ArchCompass.

It is the primary reference for developers and coding agents working on the project. Before proposing or implementing substantial changes, contributors should read this document and verify that the change supports the intended product rather than only improving an isolated implementation detail.

This document describes **what ArchCompass is meant to become and which architectural boundaries must remain stable**. More detailed documents describe how individual subsystems currently work.

When documentation conflicts:

1. This master plan governs product direction and core architectural boundaries.
2. Accepted ADRs govern deliberate exceptions and later decisions.
3. Subsystem documentation governs implementation details.
4. Existing code does not automatically override documented architectural intent.

Changes to this document should be explicit and reviewed as architectural decisions.

---

# 2. Product Vision

ArchCompass is a persistent, context-aware software architecture advisor for developers and coding agents.

Its purpose is to help answer questions such as:

- How should a new software system be structured?
- Where should a new responsibility live?
- Is an abstraction justified by credible variation?
- Which implementation details should be hidden?
- What parts of an existing repository are affected by a proposed change?
- Where are dependencies, obscurity and change amplification concentrated?
- How will a proposed architecture behave under expected future requirements?
- Is the simplest local implementation currently the better design?

ArchCompass should operate throughout the software lifecycle:

```text
Greenfield idea
    → initial architecture
    → implementation planning
    → implementation review
    → later architectural changes
    → architectural memory and governance
```

It should be useful when no code exists and become more evidence-rich when a repository is available.

ArchCompass is not intended to replace the developer’s judgement. It provides structured evidence, relevant policies, alternatives and contextual reasoning so that the developer can make a better architectural decision.

---

# 3. Core Product Thesis

Software architecture is the placement and containment of complexity under specific circumstances.

A design cannot be assessed only from generic principles. Its suitability depends on:

- The actual problem.
- Functional requirements.
- Quality attributes.
- Technical and organisational constraints.
- Known future plans.
- Credible forms of variation.
- Existing repository structure.
- Migration cost.
- Team and repository conventions.
- Relevant design policies.
- The consequences of likely future changes.

The central question ArchCompass should answer is:

> Given the available context and expected changes, where should the complexity live?

ArchCompass should not assume that more modularisation, more interfaces or more patterns automatically produce a better design.

A locally complicated module may improve the overall system when it hides complexity from the rest of the application. Conversely, a simple-looking value or function may create substantial system-wide complexity when many unrelated parts depend on it.

## 3.1 The failure ArchCompass exists to correct

Code generation is no longer the constraint. Structure is.

A coding agent asked to satisfy a requirement will satisfy it, and will tend to reach for
an interface, a layer, a registry or a configuration point at each decision — each one
locally defensible, and collectively producing software that is more complex than the
problem requires and harder to understand than the code it replaced. The agent has no
memory of the decisions it already made, no view of the system it is adding to, and no
cost model for indirection, so it cannot tell a boundary that hides complexity from one
that only forwards calls across it.

The result is not incorrect code. It is unnecessarily complex code: abstractions without
credible variation, knowledge duplicated because nothing looked for it first, and
behaviour spread across locations that must now change together.

ArchCompass exists to make that visible and to argue the other way. Its most valuable
answer is frequently **"do not add that"** — and a system that cannot say so is an
abstraction generator, not an advisor.

---

# 4. Unified Greenfield and Brownfield Model

Greenfield and brownfield consultations use **one advisory architecture**.

The only fundamental difference is the availability of repository evidence.

## Greenfield

A greenfield case may include:

- Problem statement.
- Desired outcome.
- Actors and workflows.
- Requirements.
- Quality attributes.
- Constraints.
- Future plans.
- Non-goals.
- Assumptions.
- Proposed technologies.

No repository map exists.

## Brownfield

A brownfield case includes the same contextual information and may additionally include:

- Repository structure.
- Modules and symbols.
- Dependencies and dependants.
- Call relationships.
- Interfaces and implementations.
- Tests and configuration.
- Quantified structural signals.
- Existing architectural decisions.
- Migration constraints.

Repository analysis enriches the consultation. It does not create a separate product or workflow.

---

# 5. Five Durable Domain Concepts

ArchCompass is organised around five persistent concepts.

## 5.1 ArchitectureCase

`ArchitectureCase` is the persistent, revisioned model of the architectural decision currently being considered.

It owns case-specific context:

- Problem statement.
- Desired outcome.
- Actors and workflows.
- Functional requirements.
- Quality attributes.
- Technical constraints.
- Organisational constraints.
- Expected future changes.
- Non-goals.
- Confirmed facts.
- Derived constraints.
- Assumptions.
- Unresolved questions.
- Design forces.
- Repository reference when available.
- Candidate alternatives.
- Current recommendation.
- Confidence.
- Reversal conditions.
- Revisit triggers.
- Relevant policy references.

An ArchitectureCase is not a temporary prompt. It evolves throughout the consultation and may continue evolving during implementation.

Every revision must remain available. Updates must not silently erase user-authored context or previous architectural reasoning.

## 5.2 RepositoryAtlas

`RepositoryAtlas` is a deterministic, versioned and queryable map of an existing repository.

It owns objective repository information:

- Containment structure.
- Packages, modules and symbols.
- Imports and dependencies.
- Known call relationships.
- Interfaces and implementations.
- Tests.
- Configuration relationships.
- Source locations.
- Structural metrics.
- Change-amplification proxies.
- Cognitive-scope proxies.
- Obscurity signals.

The atlas is not an LLM-generated repository summary. Language-specific analyzers construct it without executing or importing the analysed code.

The complete atlas must not be sent to the reasoning model. ArchCompass should expose a bounded overview and allow progressive zoom into relevant areas.

## 5.3 PolicyCorpus

`PolicyCorpus` owns reusable normative guidance.

Policy scopes include:

- General design policies.
- User-authored policies.
- Organisation or team policies.
- Repository-specific policies.
- Policies derived from accepted ADRs.

Examples include:

- Hide implementation details behind the boundary that owns them.
- Keep knowledge that changes together in one place.
- Prefer stable application concepts over incidental implementation details.
- Do not introduce an abstraction without credible variation.
- Pull unavoidable complexity into the module best equipped to manage it.

Policies are reasoning lenses, not automatic violations.

Policies must include:

- Intent.
- Guidance.
- Signals.
- Diagnostic questions.
- Likely consequences.
- Exceptions.
- Positive examples.
- Counterexamples.
- Related policies.

Case-specific circumstances remain in `ArchitectureCase`. Reusable normative guidance belongs in `PolicyCorpus`.

## 5.4 ConsultationRun

`ConsultationRun` is the immutable record of one advisory execution.

It records:

- Input ArchitectureCase revision.
- Atlas version when present.
- Policy-index version.
- Model and prompt identities.
- Design forces.
- Concern clusters.
- Atlas query plans and results.
- Focused analysis packets.
- Retrieved policies.
- Alternatives.
- Scenarios.
- Recommendation report.
- Evidence-validation results.
- Execution metadata.

A successful run may create a new ArchitectureCase revision. A failed or invalid run must not mutate the case.

## 5.5 ReportConversation

`ReportConversation` is the durable, append-only explanation thread for one successful
`ConsultationRun`. It is pinned to the run's exact input case revision, Atlas version,
policy-index version, and validated schema-v3 report.

It owns immutable messages, structured answers, question plans, bounded retrieval records,
exact-artifact original-run versus additional-conversation evidence scopes, model/prompt
identities, context hashes, rolling typed summary revisions, optimistic revision ordering, and
explicit failed assistant attempts. Compact finding digests and an exact pinned-case summary keep
global context available while detailed evidence remains question-specific. It is read-only with
respect to the ArchitectureCase and historical recommendation.

Every planning and answering turn receives all one to twelve finding digests and the exact input
case revision's problem, desired outcome, workflows, requirements, quality attributes, technical,
organisational and derived constraints, confirmed facts, expected changes, non-goals, and
assumptions. Direct answers, supporting points, and uncertainty are typed statements with explicit
support; repository answer claims cite exact node, relationship, metric, signal, or excerpt
artifacts rather than treating a node ID or retrieval result as sufficient evidence.

---

# 6. Unified Advisory Architecture

The target advisory flow is:

```text
Question, requirement, plan or change
                  │
                  ▼
          ArchitectureCase
                  │
                  ▼
       Build concise global context
                  │
                  ├──── Optional RepositoryAtlas overview
                  │
                  ▼
        Discover design forces
                  │
                  ▼
       Group forces into concern clusters
                  │
                  ▼
      Investigate each cluster independently
          ├── bounded atlas zoom
          ├── quantified evidence
          ├── source excerpts
          ├── relevant tests
          ├── policy retrieval
          └── uncertainty
                  │
                  ▼
       Analyse each focused packet
                  │
                  ▼
        Generate credible alternatives
                  │
                  ▼
 Evaluate scenarios, blast radius and trade-offs
                  │
                  ▼
       Cross-cluster architectural synthesis
                  │
                  ▼
        Validate every evidence reference
                  │
                  ▼
 Persist ConsultationRun and revise ArchitectureCase
```

This is a bounded reasoning loop rather than a single monolithic model call.

The system may perform additional atlas queries when an investigation exposes an important unknown, but every consultation must respect explicit query and context budgets.

---

# 7. Global Context and Focused Evidence

ArchCompass must balance system-wide context with focused analysis.

## Global context

Every reasoning stage may receive a concise global context containing:

- Problem and desired outcome.
- Requirements and quality attributes.
- Constraints.
- Future changes.
- Non-goals.
- Confirmed facts.
- Important assumptions.
- High-level RepositoryAtlas overview when available.

The global context preserves architectural coherence.

## Focused analysis packets

Detailed analysis operates on one concern cluster at a time.

A focused packet should contain:

- Cluster title and rationale.
- Associated design forces.
- Investigation questions.
- Relevant atlas nodes.
- Relevant metric observations.
- Dependency and blast-radius information.
- Relevant obscurity signals.
- Small source excerpts.
- Related tests.
- Retrieved policy evidence.
- Assumptions.
- Remaining uncertainty.

The model should not receive unrelated code or the complete repository map.

## Final synthesis

Final synthesis receives all structured concern analyses and the global context.

This allows ArchCompass to recognise that:

- Several local findings have one common architectural cause.
- Solving one concern makes another concern irrelevant.
- Two recommendations conflict.
- A local patch is more appropriate than a broad abstraction.
- Multiple individually reasonable decisions combine into excessive system complexity.

---

# 8. Design Forces and Concern Clusters

The unified reasoning concept is **design forces**, not only findings.

Design forces may include:

- Expected provider variation.
- Long-running or expensive operations.
- Resource constraints.
- Auditability.
- Backwards compatibility.
- Data ownership.
- Failure recovery.
- Independent deployment.
- Migration cost.
- Stable domain operations.
- Implementation volatility.
- A deliberately local behaviour with no credible variation.

In a brownfield system, a force may be supported by findings such as duplicated knowledge or dependency spread. In a greenfield system, it may be derived from requirements and constraints.

Related forces should be grouped into concern clusters. Typical clusters include:

- Responsibility ownership.
- Dependency containment.
- Change locality.
- Resource lifecycle.
- State and data ownership.
- Provider or implementation variation.
- Interface stability.
- Operational resilience.
- Premature abstraction.
- Discoverability and obscurity.

Concern clusters are an internal reasoning mechanism. The user does not need to provide multiple candidate plans.

Clusters group **finding candidates that share participants**, which is a fact about the
graph rather than a partition of abstract forces. Grouping this way is derivable, stable and
explainable, and it makes the workspace's islands correspond to something real in the code.
Design forces remain what they are — the case-level pressures the model weighs when deciding
whether a candidate matters here — but they no longer need to be partitioned to bound
evidence, because a candidate carries its own participants.

---

# 8A. Finding Candidates

## 8A.1 What a finding candidate is

> A finding candidate is a structural pattern that could make a policy in the corpus
> relevant.

The policy corpus is the specification. Every policy that can be violated *structurally*
implies a detector; the detector finds where the policy might apply; the model decides
whether it does. Policies that cannot be checked structurally — deliberate consistency,
designing it twice — remain judgement input rather than detector targets.

A candidate carries:

- **Pattern** — which shape of complexity was detected.
- **Participants** — every node involved, located. A candidate is **N-ary by construction**:
  duplicated knowledge is a fact about a set of modules, and a type that holds one node
  would discard the finding while appearing to record it.
- **Measurements** — what made it detectable, so the candidate is evidence rather than
  opinion, with each measurement's nature and limitations retained (§9.3, §9.4).
- **Relationships** — the dependencies, dependants and implementations that connect the
  participants, so the model can judge blast radius rather than inspecting nodes in
  isolation.

A candidate is explicitly **not a violation**. Materiality depends on circumstances the
static view cannot see, so "this does not matter here" must remain a first-class answer at
every stage that consumes one.

## 8A.2 Detection is relational, not isolated

A pattern found by looking at one node in isolation is nearly always a lint, not an
architectural finding. Architecture is about placement, so the detectable evidence is
almost always a relationship: the same knowledge in several modules, one concept edited in
several places, an abstraction with nothing behind it, several implementations with no
common owner.

Detectors therefore read the atlas graph — edges, implementations, callers, reverse reach —
and not only node attributes. A detector that cannot express "these N nodes, related this
way" cannot express the findings that matter.

## 8A.3 The catalogue is symmetric

Unnecessary complexity has two directions, and an advisor that detects only one becomes an
advocate for the other.

**Indirection without hiding** — an abstraction that adds a boundary while hiding nothing:
an interface with a single implementation and no credible variation, a module whose public
surface only forwards calls, a configuration point with one value. The advice is usually
*remove it, or do not add it*.

**Repetition without ownership** — the same knowledge or shape repeated with no common
owner: a constant duplicated across modules, several bespoke implementations preparing the
same request in parallel, one concept requiring coordinated edits in unrelated locations.
The advice is usually *give this one owner* — an agnostic boundary with specific
implementations behind it.

Both are the same underlying judgement — where should the complexity live — reached from
opposite sides. A single-implementation interface and three parallel bespoke providers are
each a candidate; only the case can say which one is wrong here, and often neither is.

## 8A.4 What a detector may not do

A detector may not decide importance, assign severity, or state that a policy was violated.
It reports that a pattern is present, with the evidence that establishes it and the
limitations of the method that found it. Ranking and prioritisation, when they exist, are
application concerns computed from measurements — never from model output, and never
smuggled into the detector as a threshold that encodes an opinion.

---

# 9. RepositoryAtlas Principles

## 9.1 Objective map first

The LLM should not be responsible for reconstructing repository structure from raw source files.

Language-specific analyzers should produce a canonical structural graph before model reasoning begins.

For Python V1, analysis uses the built-in AST without importing or executing repository code.

## 9.2 Progressive zoom

Atlas exploration follows:

```text
repository
  → subsystem
    → package
      → module
        → symbol
          → relations, metrics, tests and excerpts
```

The model begins with a bounded overview and requests more detail only where required by the ArchitectureCase and concern cluster.

## 9.3 Self-describing evidence

Atlas query results should identify:

- What the node is.
- Where it exists.
- Why it was selected.
- Which metric or signal made it relevant.
- Which dependencies and dependants are involved.
- Which tests may be affected.

Opaque IDs remain necessary for validation but are insufficient as reasoning context.

## 9.4 No universal complexity score

ArchCompass must preserve separate metric dimensions.

A module may have:

- High local control-flow complexity.
- Low outward dependency impact.
- Strong information hiding.
- Low change amplification.

Collapsing these into one score would erase the distinction between contained implementation complexity and complexity imposed on the rest of the system.

---

# 10. Complexity Model

ArchCompass uses the following broad model.

## Causes of complexity

- **Dependencies:** code cannot be understood or changed in isolation.
- **Obscurity:** important information or relationships are difficult to discover.

## Symptoms of complexity

- **Change amplification:** a conceptually small change requires many coordinated edits.
- **Cognitive load:** a developer must understand too much information to complete a task.
- **Unknown unknowns:** important dependencies or consequences are not apparent.

ArchCompass cannot measure human cognitive load or obscurity directly. It reports objective proxies and evidence-backed signals.

## Structural dimensions

The atlas may quantify:

- Physical size.
- Logical statements.
- Branching and nesting.
- Parameters.
- Public API surface.
- Fan-in and fan-out.
- Forward and reverse dependency reach.
- Dependency depth.
- Cycles.
- Number of implementations.
- Known callers.
- Associated tests.
- Configuration relationships.

## Change-amplification proxies

Examples include:

- Likely affected modules.
- Interfaces crossed.
- Implementations requiring coordinated changes.
- Configuration locations involved.
- Tests in the reverse dependency neighbourhood.

## Cognitive-scope proxies

Examples include:

- Modules in the relevant dependency neighbourhood.
- Symbols on representative paths.
- Boundaries traversed.
- Related configuration locations.
- Local control-flow complexity.
- Public API surface.

## Obscurity signals

Examples include:

- Wildcard imports.
- Dynamic imports.
- Implicit registration.
- Shared mutable state.
- Duplicate sources of truth.
- Cyclic dependencies.
- Unresolved calls.
- Similar constants across modules.
- Important behaviour spread across unrelated locations.
- Misleading relationships between a domain category and an incidental implementation property.

Signals require architectural interpretation. They are not automatic violations.

---

# 11. Policy Retrieval

Policies are stored as validated Markdown documents with structured metadata.

At index-build time:

```text
Policy Markdown
    → parse and validate
    → section-aware chunks
    → embedding provider
    → sqlite-vec
    → immutable policy-index version
```

At consultation time:

```text
Concern cluster
    + design forces
    + relevant requirements
    + repository observations
        → structured retrieval query
        → embedding
        → nearest policy sections
        → original policy text and metadata
```

Embeddings are used only for retrieval.

The reasoning model receives:

- Policy ID.
- Title.
- Scope.
- Strength.
- Applicability.
- Original retrieved text.

It never receives numerical embedding vectors.

Repository, organisation, user and accepted-ADR policies must be isolated by explicit applicability. Repository-local policies must never leak into consultations for another repository.

Conflicting relevant policies should remain visible so the advisor can explain the trade-off.

---

# 12. Evidence and Claim Discipline

## 12.0 Division of labour

> **The application decides what to look at. The model decides what it means. Nothing the model writes is ever used as a key.**

This governs every reasoning stage.

*What to look at* is search and bookkeeping: which nodes are relevant, which policies were
retrieved, which cluster a packet describes, which claim supports which finding. All of it
is derivable, reproducible and testable, and the application already holds the answer on
both sides of the call.

*What it means* is judgement: whether a structural pattern matters given this case,
which policies bear on it, what the consequence is, what should change. Only the model can
do this, and it is the only thing worth spending a model call on.

The third clause is the operational one. A model that must reproduce an identifier to be
understood will eventually reproduce it wrongly — not by inventing it, but by copying it
imperfectly — and the failure is silent because the value looks plausible. So an
application-owned identifier must never cross the wire in either direction. Where a stage
needs the model to point at something, it presents a bounded set and takes back either a
short request-local handle constrained by the response schema, or a position in the set it
presented. Where the application already knows the answer, the stage does not ask.

This extends §9.3: opaque IDs are necessary for validation and insufficient as reasoning
context — and they are also unsafe as model output.

## 12.1 Claim classification

Every important report claim must be classified as one of:

- Confirmed user requirement.
- Derived constraint.
- Repository observation.
- Policy guidance.
- Scenario assumption.
- Advisor inference.

Repository observations must reference atlas evidence surfaced during the consultation.

Policy-guidance claims must reference policies retrieved for the consultation.

The final report may not cite arbitrary valid atlas nodes that were never supplied to the relevant reasoning stage.

Unknown or unsupported references must fail validation. ArchCompass may perform one constrained repair attempt that removes or corrects unsupported references. If validation still fails, the run fails explicitly and the ArchitectureCase remains unchanged.

ArchCompass must never present assumptions or model interpretations as repository facts.

---

# 13. Recommendation Contract

The canonical recommendation should include:

1. Decision summary.
2. Problem and desired outcome.
3. Confirmed context.
4. Assumptions and unresolved questions.
5. Important design forces.
6. Repository observations and quantified signals.
7. Relevant policies.
8. Recommended architecture.
9. Responsibility allocation.
10. Conceptual interfaces.
11. Alternatives considered.
12. Scenario analysis.
13. Change-amplification and blast-radius analysis.
14. Trade-offs.
15. Implementation sequence.
16. Confidence and rationale.
17. Conditions that could reverse the recommendation.
18. Revisit triggers.
19. ADR-style decision record.
20. Evidence appendix.

Valid outcomes include:

- Introduce an abstraction.
- Move a responsibility.
- Keep behaviour local.
- Preserve the current design.
- Delay a decision.
- Gather more information.
- Reject all proposed alternatives and recommend another.
- Conclude that no architectural change is justified.

---

# 14. Persistent Advisor Vision

ArchCompass should eventually act as a continuous architectural reasoning layer around development.

## Before implementation

It advises on:

- Responsibility boundaries.
- Initial architecture.
- Alternatives.
- Risks.
- Expected change.

## During implementation

It may later advise a coding agent by checking:

- Whether the implementation plan matches the accepted architectural direction.
- Whether responsibilities are moving into the intended modules.
- Whether new dependencies are being introduced.
- Whether the implementation creates unplanned blast radius.

## After implementation

It may later analyse:

- Whether the resulting repository aligns with the decision.
- Whether complexity leaked into unrelated areas.
- Whether revisit triggers have become true.
- Whether the decision should be superseded.

This continuous-advisor vision is a long-term goal. It must not cause premature implementation of monitoring, autonomous modification or governance infrastructure.

---

# 15. Current Baseline

The repository already contains a substantial V1 foundation:

- Typed domain models.
- Immutable ArchitectureCase revisions.
- Immutable ConsultationRun persistence.
- Versioned Python AST atlases.
- Nodes, edges, metrics and obscurity signals.
- Deterministic atlas queries.
- Markdown policy parsing.
- Embedding-based sqlite-vec retrieval.
- Fake reasoning and embedding providers.
- Ollama adapters.
- Evidence validation.
- JSON and Markdown reports.
- Greenfield and brownfield evaluation fixtures.
- CLI commands.
- Documentation for the main subsystems.

The broad dependency architecture is correct:

```text
Presentation
    → application workflows
        → domain models and ports
            ← adapters

bootstrap.py = composition root
```

Domain and application code must remain independent from Typer, HTTPX, SQLite, sqlite-vec and AST implementation details.

---

# 16. Current Priority: V1.2

The active milestone is:

## Evidence-Grounded Report Conversations

The milestone should deliver:

- Schema-v3 reports and runs with stable canonical architectural findings.
- Application-projected finding evidence derived exactly from each finding's focused packet.
- Durable conversations pinned to one successful run.
- Validated recent-context-aware classification and cumulative bounded retrieval against exact
  persisted artifact identities.
- Deterministic resolution of explicit finding references (canonical ID, exact title; a shared
  title resolves to every finding that carries it). Interpretation of phrasing — ordinals,
  demonstratives, comparison wording — belongs to the classifier, whose output is validated
  against the pinned report's closed identity sets.
- Provider-neutral bounded contexts with all finding digests, the pinned case summary, typed
  rolling summaries, and eight recent messages.
- Per-turn retrieval ceilings on actions, findings, Atlas/path nodes, policies, neighbourhood
  depth and excerpt lines, plus a serialized-evidence budget derived from the configured model
  context window, with truncation and unavailability retained in the audit.
- Support-linked structured answers, exact item-level evidence scopes, one constrained repair,
  and complete failed-attempt records.
- Compare-and-swap append ordering and immutable summary revisions covering exactly twelve
  messages initially and fixed batches of eight thereafter. Invalid summaries do not advance
  coverage, and post-answer summary failures do not invalidate an already committed answer.
- Deterministic behavior for report/finding summaries, details, qualitative priority across all
  findings, comparisons, evidence/source traces, policy applicability and exceptions,
  alternatives, scenarios, assumptions, implementation order, strengthening/weakening
  counterfactuals, and unsupported questions.
- Canonical JSON for Ollama prompt inputs and context hashes, with every executed prompt identity
  versioned and recorded.
- CLI, FastAPI, and local web-workspace create/list/show/ask/history/export access.
- Removal of the legacy follow-up API, React controls, and storage, replaced by a
  report-conversation panel on the run detail page.
- Deterministic conversation evaluations and complete documentation.

The V1.1 clustered advisory workflow remains authoritative. V1.2 adds this read-only path:

```text
successful run
    → create pinned conversation
    → classify question
    → validate and execute bounded retrieval
    → build bounded context
    → answer and validate
    → optionally repair once
    → append or record failure
    → revise rolling summary after a committed answer when due
```

No unrelated product features should be added during this milestone.

---

# 17. Planned Development Sequence

## Phase 1 — Reliable advisory core

- Complete self-describing atlas evidence.
- Complete concern clustering.
- Complete per-cluster retrieval and analysis.
- Validate policy applicability.
- Strengthen prompt contracts.
- Verify metric semantics.
- Establish CI and deterministic evaluations.

## Phase 2 — Decision lifecycle

Introduce explicit states for architectural recommendations:

- Proposed.
- Accepted.
- Rejected.
- Superseded.
- Deferred.

Allow accepted decisions to become repository-local architectural memory or accepted-ADR policies.

Do not automatically promote every recommendation to policy.

## Phase 3 — Coding-agent advisory integration

Expose structured consultation and decision context to coding agents.

Possible capabilities:

- Review an implementation plan against an accepted decision.
- Request focused atlas evidence.
- Surface architectural drift before code changes.
- Generate an implementation outline without modifying code.

MCP or another integration may be considered here, but only after the advisory contracts are stable.

## Phase 4 — Change and implementation review

Add support for:

- Branch or diff analysis.
- Comparing repository atlas versions.
- Estimating introduced or reduced blast radius.
- Checking whether accepted responsibilities remain contained.
- Detecting architecture drift.

## Phase 5 — Longitudinal architectural memory

Potential additions:

- Git co-change evidence.
- Decision histories.
- Revisit-trigger evaluation.
- Supersession chains.
- Trend analysis for dependency and obscurity signals.

## Phase 6 — Broader analysis

Only after the Python architecture is proven:

- Additional programming languages.
- Runtime evidence.
- Data-flow models.
- Deployment topology.
- Service and infrastructure relationships.

---

# 18. Explicit Non-Goals for the Current Stage

Do not currently add:

- Autonomous code modification.
- Automatic pull-request comments.
- Continuous repository monitoring.
- Fine-tuning.
- Model training.
- Multiple programming languages.
- Runtime tracing.
- Git co-change analysis.
- Whole-program data flow.
- Cloud accounts or multi-tenancy.
- A generic agent framework.
- A universal complexity or maintainability score.
- Automatic enforcement of every policy.
- A broad plugin marketplace.
- Architecture changes without evidence.

Interfaces may permit later adapters, but the project should not contain unused extension infrastructure.

---

# 19. Architectural Invariants

Contributors and coding agents must preserve these invariants.

1. Greenfield and brownfield use one consultation architecture.
2. `ArchitectureCase` owns case-specific context.
3. `RepositoryAtlas` owns deterministic repository evidence.
4. `PolicyCorpus` owns reusable normative guidance.
5. `ConsultationRun` is immutable.
6. `ReportConversation` is append-only and pinned to one successful run.
7. The analysed repository is never imported, executed or modified.
8. The complete atlas or repository is never passed to the reasoning model.
9. Detailed reasoning uses bounded focused packets or bounded conversation contexts.
10. Final synthesis sees all concern analyses.
11. Metrics remain separate dimensions.
12. Policies are guidance, not automatic violations.
13. Facts, assumptions, policies and inferences remain distinguishable.
14. Every repository or policy reference is validated.
15. Failed validation cannot mutate the ArchitectureCase.
16. A local or unchanged design is a valid recommendation.
17. No provider-specific technology may leak into the domain or application core.
18. `bootstrap.py` remains the composition root.
19. New abstractions require a concrete responsibility and credible need.
20. Documentation and tests must describe metric limitations honestly.
21. Old consultations retain the exact case, atlas and policy versions they used.

---

# 20. Guidance for Coding Agents

Before changing ArchCompass:

1. Read this document.
2. Read the relevant subsystem documentation.
3. Inspect the current implementation and tests.
4. State which master-plan objective the change supports.
5. Identify affected domain concepts and responsibility boundaries.
6. Avoid broad refactoring unless required by the requested capability.
7. Preserve evidence validation and versioning.
8. Add deterministic tests before relying on a live model.
9. Update documentation when a public contract changes.
10. Do not add features listed as non-goals.

A coding agent should not treat this document as permission to implement the entire roadmap. Implement only the current requested milestone.

When a requested change conflicts with this master plan, stop and describe the conflict rather than silently changing the project direction.

---

# 21. Documentation Map

This document governs product direction.

Detailed documents should include:

- `docs/product-design.md` — product purpose and boundaries.
- `docs/architecture.md` — dependency direction and subsystem relationships.
- `docs/domain-model.md` — central domain objects.
- `docs/repository-atlas.md` — atlas construction and query model.
- `docs/atlas-metrics.md` — exact metric definitions and limitations.
- `docs/policy-format.md` — policy schema, applicability and retrieval.
- `docs/advisory-workflow.md` — consultation sequence and bounded reasoning.
- `docs/persistence-model.md` — immutable versions and storage ownership.
- `docs/report-contract.md` — output structure and evidence rules.
- `docs/report-conversations.md` — pinned conversation lifecycle, evidence scopes and budgets.
- `docs/evaluation.md` — evaluation cases and acceptance criteria.
- `docs/adr/` — accepted architectural decisions.

Subsystem documentation should not repeat the entire master plan. It should link back to it and explain the concrete implementation.

---

# 22. Maintaining This Master Plan

Update this document when:

- The product purpose materially changes.
- A core durable domain concept is added or removed.
- The advisory pipeline changes.
- A new roadmap phase is accepted.
- An architectural invariant is intentionally changed.
- A major non-goal becomes an active product capability.

Do not update it for:

- Internal refactoring.
- Dependency upgrades.
- Minor CLI changes.
- New tests that do not change product behaviour.
- Implementation details already covered by subsystem documentation.

Material changes should be accompanied by an ADR explaining:

- The previous direction.
- The new direction.
- Why the change is justified.
- Consequences.
- Migration implications.

---

# 23. Definition of Long-Term Success

ArchCompass succeeds when it can help a developer or coding agent make architecture decisions that are:

- Grounded in the actual problem.
- Informed by available repository evidence.
- Explained using relevant design policies.
- Sensitive to future change.
- Honest about uncertainty.
- Explicit about trade-offs.
- Careful about introducing abstractions.
- Traceable through validated evidence.
- Persistent across the development lifecycle.

The intended value is not generating more code.

The intended value is helping software systems remain understandable and changeable as code generation becomes easier.
