# Implementation Plan: LLM Boundary Hardening and Codebase Cleanup

**Status:** Accepted plan, implementation pending
**Scope:** Master plan Phase 1 ("Strengthen prompt contracts", "Complete per-cluster retrieval
and analysis") plus removal of speculative and dead structures. No new product capabilities,
no roadmap phases pulled forward.
**Drives:** Removal of model-output brittleness and accumulated implementation debt identified
in the July 2026 architecture review (two passes).

## 1. Problem Statement

### 1.1 The reasoning boundary

The model is asked to produce far more than it uniquely contributes, and the system
compensates with eight distinct repair/normalization mechanisms across three layers:

| # | Mechanism | Layer |
|---|-----------|-------|
| 1 | Schema-failure JSON repair round (`_complete`) | Ollama adapter |
| 2 | `_normalize_output` payload rewriting (canonical restore, claim moves, ID reassignment) | Ollama adapter |
| 3 | `_link_report_support` second-chance statement/claim mapping | Ollama adapter |
| 4 | Query-plan repair (`_repair_cluster_plans`, `_drop_unsurfaced_query_references`) | Workflow |
| 5 | Concern-analysis repair (`_prepare_concern_analysis`, `_drop_unsupported_concern_evidence`) | Workflow |
| 6 | `_restore_synthesis_artifacts` canonical restore (duplicate of #2) | Workflow |
| 7 | `repair_report_evidence_with_history` deterministic evidence repair | Application |
| 8 | `repair_conversation_answer` constrained answer repair | Application |

### 1.2 Evidence-discipline holes

- **Latent bug — silent legacy migration of fresh output:**
  `RecommendationReport.upgrade_schema_v1` treats any payload without `schema_version` as
  legacy v1. The JSON schema sent to Ollama does not require `schema_version` (defaulted
  field), so fresh model output can silently fall into keyword-based disposition inference
  and `_legacy_findings` fabrication.
- **Latent hole — the `legacy` escape hatch:** `SupportedStatement.legacy` is part of the
  model-facing JSON schema. A statement with `legacy: true` bypasses the
  supporting-claim-IDs requirement (`domain/consultation.py:462`) and is skipped by evidence
  validation (`application/evidence.py:138,380`). The model can opt out of the evidence
  contract in-band.

### 1.3 Speculative legacy compatibility and dead code

The codebase carries three schema generations of in-validator migration code for a
pre-release, single-user tool whose earlier schemas were never shipped:

- Legacy upgrade validators embedded in domain models: `RecommendationReport.upgrade_schema_v1`,
  `ADRRecord.upgrade_legacy_strings`, `FocusedAnalysisPacket.upgrade_legacy_packet`,
  `ConcernAnalysis.upgrade_legacy_results`, the `ConsultationRun` legacy branch,
  `SupportedStatement.legacy_value`, `_legacy_statement`, `_legacy_findings`,
  `_upgrade_scenario_mappings`.
- Masking defaults: `ConcernAnalysis.cluster_id = "cluster_legacy"` hides missing data.
- Schema-v1 metric-name aliases and compat properties in `domain/atlas.py`
  (`public_interfaces_crossed`, `symbols_in_representative_path`).
- The `legacy` flag threading through `application/evidence.py` and
  `application/reporting.py`.
- Dead code: `CaseExtraction` (zero references), `ports/services.py` compat re-export module
  (zero importers), `prompt_identities` property on both providers (never called),
  `DEFAULT_CONFIG_TEXT` (unused alias, evaluated at import time), the `advise(atlas=...)`
  schema-v1 shim parameter (no caller passes it).

### 1.4 Evaluation circularity

`DeterministicReasoningProvider` (1,971 lines — larger than the real adapter) is not a
neutral fake: it keys behavior off eval-fixture tokens (`"qwen"`, `"provider"`, `"voice"`,
`"premature"`, `"one implementation"`) and special-cases the boundary-preparation signal
codes in five places. The deterministic evaluations therefore validate the fake's knowledge
of the fixtures, not the pipeline's contracts.

### 1.5 Conversation-layer brittleness

- Intent keywords (`between`, `compare`, `polic`, …) override the LLM classifier and raise
  hard errors for reasonable phrasings.
- `_validate_supported_facts` regex-scrapes answer prose for bare numbers, relationship
  words, and quoted strings and fails the turn when a token is absent from serialized
  support JSON — a false-positive machine (e.g. a model writing a derived count fails
  validation even when every cited artifact is correct).

### 1.6 Transport blind spots

No prompt-size check against `num_ctx` (Ollama silently truncates from the front), no
transient-failure retry, one timeout for every stage.

### 1.7 Structural hygiene

- `workflows/consultation.py` is 2,166 lines; roughly a third of `advise()` is progress
  plumbing.
- `adapters/repository/ast_analyzer.py` is 2,079 lines, ~800 of which implement the two
  boundary-preparation signals; knowledge of those two signal codes is additionally
  scattered across the workflow's hardcoded overview ordering
  (`consultation.py:2018`), the deterministic provider, docs, and tests.
- `ConversationConfig` presents mandated V1.2 ceilings as configuration: most fields allow
  exactly one value (`summarize_after_messages: ge=12, le=12`) or a range capped at the
  mandated ceiling. Constants are dressed as knobs.
- `bootstrap.Runtime` exposes concrete adapter types (`SQLiteCaseRepository`, …) as public
  fields; only the AST boundary test keeps presentation honest.
- `presentation/web/app.py` is a single 716-line module for all routes.
- Stage names are stringly-typed across three locations.
- The built React bundle is committed under `presentation/web/static/` with no staleness
  check against `frontend/`.

## 2. Decisions

Delegated to the implementing agent; confirmed where noted.

1. **Composition over reproduction (confirmed by owner).** Synthesis returns a
   `ProposedRecommendation` wire DTO containing only what the model uniquely contributes.
   The application composes the persisted `RecommendationReport` from canonical upstream
   artifacts plus that proposal. Provenance is recorded in `execution_metadata`.
2. **Wire contracts and storage contracts are separate.** Model-facing DTOs live in
   `domain/proposals.py` and validate strictly. Domain model validators never contain
   migration heuristics.
3. **One validation authority.** All domain-aware validation and repair lives in the
   application layer. Adapters do transport + schema constraint + one generic JSON-repair
   round only. `consume_repair_actions` is removed from the port.
4. **Explicit-reference resolution stays deterministic and authoritative; intent keywords
   become advisory.** Master plan §16 finding resolution (ID, exact title, ordinal,
   unambiguous recent reference) is unchanged.
5. **Ambiguity produces a clarification answer, not an exception.**
6. **No silent truncation, ever.** The adapter fails explicitly when the serialized prompt
   plus output budget cannot fit `num_ctx`; prompt sizes are recorded per stage.
7. **Transport retries are bounded and transport-only.**
8. **A golden-replay test tier is added before refactoring starts.**
9. **Pre-release legacy compatibility is deleted, not ported.** ArchCompass 0.1.0 has never
   been released; the v1/v2 schemas existed only inside this repository's history. All
   legacy upgrade validators, the `legacy` statement flag, compat aliases/properties, the
   `advise(atlas=)` shim, and the dead modules in §1.3 are removed. Reading a stored pre-v3
   row fails loudly with a clear "re-run this consultation" message; no SQL migration
   deletes any data. *Fallback if the owner holds stored runs worth keeping: a one-time
   export command before this lands — decide when WS1 starts.* The deprecated
   `report_follow_ups` table stays per the V1.2 milestone.
10. **The deterministic provider becomes a scripted fixture player.** Per-eval-case response
    fixtures live next to the eval cases; the provider replays them. It contains no
    keyword heuristics and no knowledge of signal codes. Pipeline contracts are tested by
    the validators and the replay tier, not by a simulated reasoner.
11. **Mandated ceilings become constants.** V1.2 budget ceilings move to domain constants
    with names matching the documentation. `ConversationConfig` retains only genuinely
    tunable values. Same review applied to the other config sections.
12. **Prose fact-checking keeps only high-precision token classes.** Artifact IDs, source
    locations, and paths remain hard-fail checks (near-zero false positives). Bare numbers,
    relationship words, metric-name mentions, and quoted-substring checks become audit
    warnings recorded on the message, not turn failures. The renderer increasingly injects
    exact figures from cited evidence rather than trusting model restatement (same
    composition principle as decision 1).
13. **A report-conversation panel joins the web workspace (confirmed by owner).** Master
    plan §18 currently lists a React conversation frontend as a non-goal; the owner has
    decided to lift that. WS8 begins by amending master plan §18 and `.agents/AGENTS.md`
    and recording `docs/adr/0003-conversation-panel.md`, then builds the panel against the
    existing `/api/conversations` contracts. It is sequenced after WS4 so the UI is built
    on clarification-answer behavior, never on today's exception-throwing behavior.

Deliberately kept as-is:

- Query-plan and packet budget enforcement in the workflow (allowlist/budget enforcement
  with audit records, not model-output repair).
- Post-hoc validation for `plan_atlas_queries` node references (conditional per-cluster
  enum schemas cost more than drop-and-audit).
- The boundary-preparation signals themselves: documented in `docs/atlas-metrics.md` and
  `docs/repository-atlas.md`, tested in `test_atlas_alignment.py`. They are contained and
  de-scattered (WS6), not removed.
- The committed React bundle (local-first distribution); WS6 adds a staleness check and
  regeneration instructions instead of moving the build.

Target end state: **four repair mechanisms, each with a single owner and a single pass** —
adapter schema repair, workflow plan/budget enforcement, application evidence repair,
application conversation-answer repair.

## 3. Workstreams

Order is dependency order. Each workstream lands as one or more commits with the full test
suite green.

### WS0 — Golden replay safety net

*Goal: pin current intended semantics before anything moves.*

- New `tests/replay/` tier: fixtures of persisted stage outputs (valid and deliberately
  malformed) replayed through `validate_report_evidence`, `canonicalize_report_findings`,
  `validate_conversation_answer`, and (once it exists) the report composer.
- Malformed fixtures per stage: missing `schema_version`, `legacy: true` statements,
  misclassified section claims, duplicate claim IDs, unknown node/policy references,
  missing cluster coverage, scenario alternative-key drift, unknown force handles.
- These fixtures double as the seed corpus for the WS7 fixture player.
- Acceptance: replay tests document today's behavior for the two evidence-discipline holes
  (§1.2) and are updated to the fixed behavior in WS1.

### WS1 — Contract honesty: legacy purge, wire/storage split, constants

*Goal: fresh model output can never enter legacy paths; the schema surface tells the truth.*

- Delete everything in §1.3: legacy validators, `legacy` flag and `legacy_value`,
  `_legacy_statement` / `_legacy_findings` / `_upgrade_scenario_mappings`, metric-name
  aliases and compat properties, `cluster_legacy` defaults, `CaseExtraction`,
  `ports/services.py`, `prompt_identities`, `DEFAULT_CONFIG_TEXT`, the `advise(atlas=)`
  parameter. Remove the `legacy` branches from `application/evidence.py` and
  `application/reporting.py`.
- `RecommendationReport`, `ADRRecord`, `ConsultationRun`, `FocusedAnalysisPacket`,
  `ConcernAnalysis` validate the current schema strictly; `schema_version` is required
  where it exists. Repository read paths translate a strict-validation failure on a stored
  row into a clear "pre-V1.2 row; re-run this consultation" error (decision 9).
- Move mandated V1.2 ceilings from `ConversationConfig` to domain constants (decision 11);
  config keeps genuinely tunable knobs only.
- Acceptance: WS0 fixtures for §1.2 now fail validation loudly; no source file matches
  `legacy|compat` outside persistence read-path errors and the policy corpus; test suite
  green.

### WS2 — Consolidate validation authority *(done)*

*Goal: one implementation of each domain rule; the adapter contains no policy it owns
alone.*

Delivered:

- **One containment rule.** "Is this cited span inside its surfaced node" existed in
  *six* places, not the three the review found: `application/evidence.py` twice
  (`_claim_errors` and `_reference_invalid`), `workflows/consultation.py` twice
  (the concern-analysis repair pass and its validation pass), `adapters/models/ollama.py`
  once, and `application/conversation_validation.py` twice. All now call
  `domain/evidence_rules.py::location_within`. The two extra copies in conversation
  validation were found by the guard test, not by reading.
- **Guard tests.** `adapters/models` may not import `application` or `workflows`
  (the invariant already held; it is now enforced). A second test fails if hand-rolled
  span containment reappears anywhere outside the domain rule.
- **`ReasoningTask` StrEnum** replaces stringly-typed stage names across the prompt
  registry, both providers, the workflow, and the conversation service. A consistency
  test asserts the enum and the Ollama registry describe the same stage set — which
  surfaced that `LINK_STATEMENT_SUPPORT` executed without being registered, so its
  identity could never be resolved or recorded. It is now registered.
- **`Runtime` typed by ports** rather than concrete SQLite/AST/vector adapters, with
  `database` documented as the deliberate exception (the composition root's own
  infrastructure handle, already fenced off from presentation by a structural test).

**Deferred to WS3, with reason.** The plan listed `_normalize_output`,
`_link_report_support`, and `consume_repair_actions` for removal here. They cannot move
before the wire DTO exists:

- `_normalize_output` runs *before* Pydantic validation, because misclassified section
  claims and duplicate claim IDs raise in `validate_report_contract`. Relocating it to
  the application would mean validating first — which is exactly what fails. The
  composer removes the need entirely by placing claims into sections by classification
  and assigning claim IDs itself.
- `_link_report_support` issues its own model call. Moving it to the application in WS2
  would mean adding a port method in WS2 and deleting it in WS3, since the proposal DTO
  carries claim-key references in band.
- `consume_repair_actions` still carries the audit trail for both of the above.

### WS3 — Composed synthesis (the centerpiece) *(done)*

*Goal: the model proposes; the application composes. Repair mechanisms #2, #3, #6
disappear by construction.*

New wire DTO in `domain/proposals.py` — `ProposedRecommendation`:

- disposition, decision-summary statement, problem/outcome text, confidence, ADR content;
- proposed claims with **model-local keys** (`c1`, `c2`, …), classification, text, and
  evidence references using **request-local handles** for everything known a priori
  (atlas node IDs, policy IDs, cluster handles `C1..Cn`, force handles `F1..Fn`,
  alternative handles `A1..An`) — enum-constrained in the JSON schema;
- statements (decision summary, recommended architecture, responsibility allocation,
  conceptual interfaces, trade-offs, implementation sequence, reversal conditions, revisit
  triggers, change amplification, ADR decision/consequences) each referencing supporting
  model-local claim keys;
- proposed findings with cluster handles and claim/node/policy handle references;
- **no** echo of forces, alternatives, scenarios, or policy evidence; **no** `legacy` or
  `schema_version` fields on the wire.

New composer in `application/synthesis.py`:

1. Validate the proposal: intra-response claim-key references resolve; cluster coverage
   (≥1 finding per cluster); evidence references valid against the packets (single
   authority from WS2).
2. On errors: one constrained repair via a new port method
   `repair_recommendation_proposal(proposal, errors, allowed_*)` (mirrors
   `repair_conversation_answer`), then revalidate.
3. Compose the `RecommendationReport`: system-assigned claim IDs (deterministic content
   hash — duplicate-ID handling disappears by construction), claims placed into sections
   **by classification** (misclassification shuffling disappears by construction),
   canonical forces/alternatives/scenarios/policy evidence injected from workflow state
   (canonical restore disappears by construction), statement supports mapped from claim
   keys (the statement-support linking call disappears).
4. The existing pipeline continues unchanged: `canonicalize_report_findings` →
   `validate_report_evidence` → deterministic evidence repair (the single evidence repair)
   → final validation → commit or fail.

Port and prompt changes:

- `synthesize_recommendation` → `propose_recommendation(...) -> ProposedRecommendation`;
  add `repair_recommendation_proposal`.
- `SYNTHESIZE_RECOMMENDATION` contract rewritten for the proposal schema; version bumped.
- Cheap hardening, no DTO change: `analyze_concern_cluster` gets a `schema_override` with
  enum-constrained node and policy IDs from its packet, replacing prose-only allowlists.

Persistence: the composed `RecommendationReport` keeps schema v3 — the persisted shape does
not change. `execution_metadata` gains `synthesis_proposal_hash` and `composition_actions`.

Acceptance: replay and evaluation tests green; a replay fixture proves a proposal with
misclassified/duplicate/unknown references composes or fails deterministically;
`_link_report_support`, `_restore_synthesis_artifacts`, and `_normalize_output` are gone.

### WS4a — Precise repository-fact verification *(done)*

*Goal: a correctly cited answer is never rejected for how its prose reads.*

Two strict-xfail replay tests from WS0 pinned false positives in the prose fact
checker. Both now pass. Investigation found three distinct causes, fixed separately
rather than by blanket demotion:

- **A missing guard, not a heuristic.** Relationship words were checked even when no
  relationship evidence was supplied, so with only a metric cited every ordinary use of
  "imports", "calls" or "contains" read as an invented edge. The structurally identical
  signal-code check three lines below already guarded on its supplied set. It now does
  too, and two new tests pin both directions: once an edge *is* cited, naming a
  different edge type still fails the turn.
- **A too-narrow supplied set.** A path counted as supplied only when its evidence also
  carried `start_line`/`end_line`, so citing a node summary without a span made its own
  path look invented. Bare `path` fields now count.
- **A genuine over-reach.** A bare number is a repository fact only when offered as a
  metric's value. It is now a hard error when the text also names a supplied metric —
  so a wrong `dependency.fan_in` still fails — and an audit warning otherwise. Quoted
  fragments became warnings for the same reason.

`validate_conversation_answer` returns `AnswerValidation(errors, warnings)`; the service
records warnings on the message's retrieval record, alongside the truncation and
unavailability audit it already carries.

**Correction to decision 12.** The decision assumed artifact IDs, source locations and
paths were all high-precision. Investigation reproduced false positives in two of the
three: `node-level` and `test-coverage` scrape as artifact IDs, and the path case above.
The path derivation is fixed. Artifact IDs stay a hard failure deliberately: no rule
distinguishes `node-level` (prose) from `node-invented` (fabrication) by shape, and
admitting a fabricated repository identifier would breach invariants 13 and 14. The
false-positive shape is documented rather than silently accepted.

### WS4b — Clarification answers *(deferred; must follow WS7)*

The advisory-intent and clarification-answer half of WS4 is **not** implemented, and the
sequencing in decision 4/5 was wrong. Investigation surfaced a hard dependency and three
design hazards that were not visible when the plan was written:

1. **`DeterministicReasoningProvider` duplicates five of the resolution rules and raises
   first.** `classify_report_question` runs before `_resolve_and_enrich_plan`, and the
   fake — which every integration and evaluation test uses — raises its own
   `ConversationValidationError` at `deterministic.py:967` and `:980`. Changing
   `conversations.py` alone would leave the clarification path unobservable in every
   test tier, and writing clarification logic into a fake that WS7 replaces wholesale is
   wasted work. **WS4b must follow WS7.**
2. **A `kind: clarification` field on `ConversationAnswer` would be the `legacy` escape
   hatch again.** That model is simultaneously the model-facing wire schema and the
   persisted shape, so a kind that relaxes `AnswerStatement.require_support` is
   structurally what ADR 0002 removed. The clarification must therefore be constructed
   by the application and never offered to the model.
3. **A clarification that cites nothing is not constructible**, and should not become
   so. The minimum valid form cites the candidate finding digests, which is honest and
   passes validation unchanged. Whatever it puts in `relevant_finding_ids` becomes the
   next turn's contextual anchor — for a two-candidate clarification that is correct
   behaviour, not a bug, but it must be deliberate.
4. **Persisting one is non-trivial**: the assistant message needs a full
   `ConversationRetrievalRecord` whose `supplied_finding_ids` equals the entire ordered
   pinned finding list and whose `summary_revision` is exactly current. A clarification
   also adds two messages where a failed turn added one, shifting rolling-summary
   pacing.

Eleven raise sites are in scope (`conversations.py` 534, 542, 546, 716, 727, 739, 747,
770, 779, 788, 797); six others are genuine contract violations that must keep raising
(118, 154, 156, 164, 356, 1019).

### WS5 — Transport hardening *(done)*

*Goal: the most likely real-world failures are explicit, attributable, and cheap to
survive.*

- **Prompt-size guard** in `_chat`, covering the schema-repair round as well as the
  first call. Raises `PromptBudgetExceededError` naming the stage and both measured
  sizes rather than letting Ollama truncate from the front and lose the system prompt.
- **Bounded retry** (3 attempts, exponential backoff) via one `_post_with_retry` helper
  shared by the reasoning and embedding providers. The transient set is positive-listed
  — timeouts, network errors, remote protocol errors, proxy errors, and 408/429/5xx —
  so `LocalProtocolError` and `UnsupportedProtocol`, which are configuration faults,
  are never retried. A structured-output failure is not a transport failure: a stage
  still makes exactly two calls however malformed the responses are, which a test pins.
- **Two timeout classes** with `timeout_seconds` as fallback, so a workspace written
  before they existed behaves identically. `_complete` now takes a `ReasoningTask` and
  resolves its contract from the registry, which is what both the guard message and the
  timeout class need; twelve contract imports collapse to one.

**Corrections applied after adversarial review.** Three of the four reviewers returned
`needs_revision` on the first design, and the criticism was right:

- The design excluded the response schema from the guarded estimate, citing a 400
  "failed to parse grammar" response as server-side evidence. That response is
  fabricated by a test's own monkeypatched stub; no Ollama server is involved. The
  schema is now **counted**, which is the fail-safe direction: over-counting refuses a
  borderline request explicitly, under-counting reproduces the silent truncation the
  guard exists to remove.
- `PromptBudgetExceededError` derives from `ArchCompassError`, not `ProviderError`. The
  stated rationale for `ProviderError` (surviving `_sanitize_error`) was a non-sequitur —
  the `else` branch preserves any non-`ModelOutputValidationError` message — and
  `ProviderError` maps to 503 `retryable=True`, which misdescribes a deterministic
  failure.
- A proposed `ports/prompt_metering.py` using process-global context state was dropped.
  It was not a port, and `ThreadPoolExecutor.submit` does not propagate context, so a
  scope opened on the wrong thread would have recorded nothing with a green suite.

**Deferred: per-stage prompt sizes in `execution_metadata`.** Decision 6 asks for these
on the success path. Every mechanism considered either smuggled application state into
the adapter or added a collaborator with no reader, which master-plan §18 forbids. The
guard's exception already carries the sizes on the only path where they change a
decision. Recording them on success is deferred until something reads them.

### WS6 — Structural decomposition and containment (mechanical, behavior-preserving)

*Goal: no module carries responsibilities it doesn't own; large files become navigable.*

- Extract a `StageRunner` wrapping progress events, stage timing, prompt-identity
  recording, and the current-stage marker; `advise()` shrinks to the pipeline sequence.
- Split `workflows/consultation.py` into orchestration, evidence accumulation, plan
  enforcement, packet building, and case-revision assembly modules; target no file above
  ~600 lines.
- Split `ast_analyzer.py`: the two boundary-preparation signal implementations move to
  `adapters/repository/boundary_signals.py`; the analyzer core keeps parsing, graph
  construction, and metrics.
- Contain signal knowledge: signal ordering/priority metadata moves next to the signal
  definitions (a small registry in the repository adapter); the workflow's hardcoded
  priority map at `consultation.py:2018` reads from it. (The deterministic provider's
  special-casing disappears in WS7.)
- Split `presentation/web/app.py` routes by resource (cases, runs, jobs, atlas, policies,
  conversations); shared error mapping stays in one place.
- Bundle staleness check: a script target that rebuilds `frontend/` and fails when the
  committed `static/` bundle differs; regeneration instructions in
  `docs/web-workspace.md`.
- Documentation pass: `docs/architecture.md` (adapter responsibilities now true as
  written), `docs/report-contract.md` (composition provenance),
  `docs/advisory-workflow.md`, `docs/report-conversations.md`, `.agents/AGENTS.md`.
- New `docs/adr/0001-composed-synthesis.md` and `docs/adr/0002-legacy-purge.md` per master
  plan §22.

### WS7 — Evaluation honesty

*Goal: evaluations exercise the pipeline, not a keyword simulator.*

- Replace `DeterministicReasoningProvider`'s heuristic reasoning with a scripted fixture
  player: per-eval-case response files (YAML/JSON, stored under `eval/cases/<case>/responses/`)
  keyed by `ReasoningTask`; the provider validates that requested task/inputs match the
  fixture's recorded expectations and replays the response.
- Delete all token- and signal-code-keyed behavior (`"qwen"`, `"provider"`, `"voice"`,
  `"premature"`, `_BOUNDARY_PREPARATION_SIGNAL_CODES`) from the provider.
- Evaluation assertions move from "the fake produced the expected recommendation" to "the
  pipeline validated, bounded, composed, and persisted the scripted responses correctly" —
  plus the existing evidence-integrity assertions, which stay.
- Where an eval case needs live-model quality signal, it uses the existing `ollama` /
  `architectural_quality` markers; the deterministic tier makes no quality claims.
- Runs after WS3 so fixtures are written once against the final port signatures.
- Acceptance: `deterministic.py` shrinks to a fixture player (~300 lines); eval matrix
  green; no eval-case vocabulary appears in `src/`.

### WS8 — Report-conversation panel in the web workspace

*Goal: converse about a run's findings directly from the report overview.*

Scope amendment first (decision 13): amend master plan §18 (remove the conversation-UI
non-goal), update `.agents/AGENTS.md` ("no conversation React UI" no longer applies), and
record `docs/adr/0003-conversation-panel.md` (previous direction, new direction,
justification, consequences) before any UI code.

Then, against the existing contracts only:

- A conversation panel on the run detail page: create a conversation for the viewed run,
  list existing conversations, show history, ask questions, and render clarification
  answers distinctly from evidence-grounded answers.
- Consume the existing endpoints (`/api/conversations` create/list/show/history/messages/
  export) via the OpenAPI-generated types (`scripts/generate_openapi_types.py`); no new
  backend routes and no changes to conversation semantics — the panel is a pure client of
  the WS4-hardened service.
- Render structured answers from their typed statements (direct answer, supporting points,
  uncertainty) with finding/claim/policy references visible; markdown export via the
  existing export endpoint.
- Surface turn failures as recorded failed attempts (they already persist as error
  records), never as silent drops.
- Rebuild and commit the static bundle through the WS6 staleness check.
- Acceptance: panel works against a live local workspace end to end; `docs/web-workspace.md`
  documents the panel; master plan §18 and AGENTS.md no longer contradict the shipped UI.

## 4. Sequencing

Progress: WS0, WS1, WS2, WS3, WS4a and WS5 are complete. WS6, WS7, WS4b and WS8 remain,
in that order — WS4b now depends on WS7.

```text
WS0 (replay tier)
  → WS1 (legacy purge + contract honesty)   [fixes both evidence-discipline holes]
  → WS2 (adapter slimming)                  [prerequisite for WS3]
  → WS3 (composed synthesis)                [largest; the confirmed decision]
      → WS7 (evaluation honesty)            [fixtures written against final ports]
WS4a (fact precision)                       [done; independent]
WS7 (evaluation honesty)
  → WS4b (clarification answers)            [needs the fixture player, not the fake]
     → WS8 (conversation panel)             [scope amendment + UI]
WS5 (transport)                             [independent; parallel after WS0]
  → WS6 (decomposition + docs + ADRs)       [after WS0–WS5; WS8 may follow or overlap]
```

Approximate sizes: WS0 M, WS1 M, WS2 M, WS3 L, WS4 M, WS5 S, WS6 M, WS7 M, WS8 M.

## 5. Invariant Compliance

Master plan invariants directly exercised: #8/#9 (bounded contexts — strengthened by the
prompt-size guard), #13 (claim classifications — correct by construction; the `legacy`
escape hatch closes), #14/#15 (validated references, failed validation cannot mutate the
case — unchanged), #17 (no provider tech in core — strengthened by WS2), #19 (new
abstractions limited to the wire DTOs, the composer, the StageRunner, and the fixture
player, each with a concrete responsibility). Invariant #21 (old consultations retain their
exact versions) is interpreted as data retention: decision 9 deletes schema-tolerance code,
not rows, and pre-release rows that no longer parse fail with an explicit re-run message
rather than being silently reinterpreted.
