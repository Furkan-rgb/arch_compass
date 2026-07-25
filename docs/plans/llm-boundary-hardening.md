# Implementation Plan: LLM Boundary Hardening

**Status:** Accepted plan, implementation pending
**Scope:** Master plan Phase 1 ("Strengthen prompt contracts", "Complete per-cluster retrieval
and analysis"). No new product capabilities, no roadmap phases pulled forward.
**Drives:** Removal of model-output brittleness identified in the July 2026 architecture review.

## 1. Problem Statement

The reasoning boundary currently asks the model to produce far more than it uniquely
contributes, then compensates with eight distinct repair/normalization mechanisms spread
across three layers:

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

Additional defects:

- **Latent bug:** `RecommendationReport.upgrade_schema_v1` treats any payload without
  `schema_version` as legacy v1. The JSON schema sent to Ollama does not require
  `schema_version` (the field has a default), so fresh model output can silently fall into
  keyword-based disposition inference and `_legacy_findings` fabrication.
- **Duplicated knowledge:** atlas-reference validity is implemented three times
  (`ollama.py::_claim_can_survive_evidence_repair`, workflow
  `_drop_unsupported_concern_evidence`, `evidence.py::_reference_invalid`).
- **Doc/code conflict:** `docs/architecture.md` states model adapters "do not choose evidence,
  history, citation, or truncation rules"; the Ollama adapter currently does.
- **Product brittleness:** conversation intent keywords (`between`, `compare`, `polic`, …)
  override the LLM classifier and raise hard errors for reasonable phrasings.
- **Transport blind spots:** no prompt-size check against `num_ctx` (Ollama silently truncates
  from the front), no transient-failure retry, one timeout for all stages.

## 2. Decisions

These decisions govern the workstreams below. They were delegated to the implementing agent
and confirmed where noted.

1. **Composition over reproduction (confirmed by owner).** Synthesis returns a
   `ProposedRecommendation` wire DTO containing only what the model uniquely contributes.
   The application composes the persisted `RecommendationReport` from canonical upstream
   artifacts plus that proposal. The persisted report is system-composed; provenance is
   recorded in `execution_metadata` (proposal content hash + composition actions).
2. **Wire contracts and storage contracts are separate.** Model-facing DTOs live in
   `domain/proposals.py` and validate strictly against the current schema. Legacy-upgrade
   logic moves to the persistence read path. Domain model validators never contain migration
   heuristics.
3. **One validation authority.** All domain-aware validation and repair lives in the
   application layer. Adapters do transport + schema constraint + one generic JSON-repair
   round only. The `consume_repair_actions` port method is removed; repairs are recorded
   where they happen.
4. **Explicit-reference resolution stays deterministic and authoritative; intent keywords
   become advisory.** Finding resolution by ID, exact title, numeric/word ordinal, and
   unambiguous recent reference (master plan §16) is unchanged. Keyword intent detection may
   add retrieval actions but never vetoes the LLM plan and never raises.
5. **Ambiguity produces a clarification answer, not an exception.** An ambiguous reference
   or under-specified comparison yields a structured clarification response persisted as a
   normal assistant message. This still "reports ambiguity instead of guessing".
6. **No silent truncation, ever.** The adapter fails explicitly when the serialized prompt
   plus output budget cannot fit `num_ctx`. Prompt sizes are recorded per stage.
7. **Transport retries are bounded and transport-only.** Connect errors, timeouts, and 5xx
   responses retry with backoff; validation failures never retry beyond the single sanctioned
   repair pass.
8. **A golden-replay test tier is added before refactoring starts.** Recorded stage outputs
   (valid and deliberately malformed) replay through validators and composers without a
   model.

Deliberately kept as-is:

- Query-plan enforcement (#4 above) and packet budget enforcement: these are allowlist/budget
  enforcement with audit records, not model-output repair. They stay in the workflow.
- Post-hoc validation for `plan_atlas_queries` node references (instead of per-cluster schema
  enums): conditional per-cluster enum schemas are more complex than the drop-and-audit
  enforcement they would replace.
- The committed React bundle under `presentation/web/static/` (out of scope; separate
  decision).

Target end state: **four mechanisms, each with a single owner and a single pass** —
adapter schema repair, workflow plan/budget enforcement, application evidence repair,
application conversation-answer repair.

## 3. Workstreams

Order is dependency order. Each workstream lands as one or more commits with the full test
suite green.

### WS0 — Golden replay safety net

*Goal: pin current intended semantics before anything moves.*

- New `tests/replay/` tier: fixtures of persisted stage outputs (from the deterministic
  provider and hand-written malformed variants) replayed through
  `validate_report_evidence`, `canonicalize_report_findings`,
  `validate_conversation_answer`, and (once it exists) the report composer.
- Malformed fixtures to cover, per stage: missing `schema_version`, misclassified section
  claims, duplicate claim IDs, unknown node/policy references, missing cluster coverage,
  scenario alternative-key drift, unknown force handles.
- Acceptance: replay tests fail today on the missing-`schema_version` fixture (documenting
  the latent bug) and are updated to the fixed behavior in WS1.

### WS1 — Separate wire and storage contracts (fixes the latent bug)

*Goal: fresh model output can never enter legacy-migration heuristics.*

- Move `upgrade_schema_v1`, `_legacy_statement`, `_legacy_findings`,
  `_upgrade_scenario_mappings` (and the `ADRRecord` legacy validator) out of
  `domain/consultation.py` into a persistence-side migration module under
  `adapters/persistence/migrations/`. The run repository applies migrations when reading
  stored rows before constructing domain models.
- `RecommendationReport` and `ADRRecord` validate the current schema strictly. A payload
  without `schema_version` is invalid, loudly.
- Audit `domain/conversation.py` for the same pattern; move any found upgrade validators the
  same way.
- Acceptance: replay fixture from WS0 now fails validation instead of silently mutating;
  stored legacy rows still load through the repository path (covered by existing persistence
  tests plus one new legacy-row fixture).

### WS2 — Slim the adapter; consolidate validation authority

*Goal: the Ollama adapter contains no domain rules; evidence validity has one implementation.*

- Delete from `adapters/models/ollama.py`: `_normalize_output` (claim moves, duplicate-ID
  reassignment, canonical restore), `_claim_can_survive_evidence_repair`,
  `_link_report_support`, `_statement_slots`, `_apply_statement_support`,
  `_support_plan_schema`, `_support_plan_errors`, `normalization_context`. (Most of this
  becomes unnecessary by construction in WS3; anything still needed interim moves to
  `application/evidence.py`.)
- The adapter keeps: canonical JSON serialization, schema constraint (including
  caller-supplied `schema_override` enums), one generic repair round driven by schema
  validation plus an optional caller-supplied `candidate_validator`, HTTP error mapping.
- Single implementation of atlas-reference validity in `application/evidence.py`, used by the
  workflow's concern-analysis validation and by evidence repair. The other two copies are
  deleted.
- Remove `consume_repair_actions` from `FocusedReasoningProvider`; the workflow and
  application record repair/composition actions themselves.
- Replace stringly-typed stage names with a `ReasoningTask` StrEnum in `ports/reasoning.py`;
  `prompt_identity(task: ReasoningTask)`; `OLLAMA_STAGE_PROMPTS` keyed by it.
- New boundary test: `adapters/models` must not import `application.*`.
- Acceptance: existing unit tests for normalization move to `application/evidence` tests;
  boundary tests green; adapter file materially smaller.

### WS3 — Composed synthesis (the centerpiece)

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
- **no** echo of forces, alternatives, scenarios, or policy evidence.

New composer in `application/synthesis.py`:

1. Validate the proposal: intra-response claim-key references resolve; cluster coverage
   (≥1 finding per cluster); evidence references valid against the packets (single authority
   from WS2).
2. On errors: one constrained repair via a new port method
   `repair_recommendation_proposal(proposal, errors, allowed_*)` (mirrors
   `repair_conversation_answer`), then revalidate.
3. Compose the `RecommendationReport`: system-assigned claim IDs (deterministic content
   hash — duplicate-ID handling disappears by construction), claims placed into sections **by
   classification** (misclassification shuffling disappears by construction), canonical
   forces/alternatives/scenarios/policy evidence injected from workflow state (canonical
   restore disappears by construction), statement supports mapped from claim keys
   (statement-support linking call disappears).
4. Existing pipeline continues unchanged: `canonicalize_report_findings` →
   `validate_report_evidence` → deterministic evidence repair (kept as the single evidence
   repair) → final validation → commit or fail.

Port and prompt changes:

- `synthesize_recommendation` → `propose_recommendation(...) -> ProposedRecommendation`;
  add `repair_recommendation_proposal`.
- `SYNTHESIZE_RECOMMENDATION` contract rewritten for the proposal schema; version bumped.
- `DeterministicReasoningProvider` emits proposals; its report-assembly logic moves into
  shared use of the real composer, shrinking the fake and eliminating fake/live divergence
  on this path.
- Also in this WS (cheap hardening, no DTO change): `analyze_concern_cluster` gets a
  `schema_override` with enum-constrained node and policy IDs from its packet, replacing
  prose-only allowlists.

Persistence: the composed `RecommendationReport` keeps schema v3 — the persisted shape does
not change. `execution_metadata` gains `synthesis_proposal_hash` and `composition_actions`.

Acceptance: all replay and evaluation tests green; a new replay fixture proves a proposal
with misclassified/duplicate/unknown references composes or fails deterministically;
`_link_report_support`, `_restore_synthesis_artifacts`, and adapter `_normalize_output` are
gone.

### WS4 — Conversation intent demotion and clarification answers

*Goal: no user turn hard-fails because of phrasing.*

- `_resolve_finding_references` (IDs, exact titles, ordinals, contextual this/that/former/
  latter): unchanged, authoritative, deterministic (master plan §16).
- `_is_comparison` and the phrase→question-type tables become advisory: they may add
  question types and retrieval actions; they never remove LLM-planned actions and never
  raise.
- Ambiguity outcomes (`comparison with <2 resolvable findings`, `ambiguous title`,
  `contextual reference without unique antecedent`, `ordinal out of range`) return a typed
  clarification answer — a `ConversationAnswer` variant with kind `clarification`, no
  evidence claims, listing what was ambiguous and the resolvable candidates. It is rendered,
  validated (trivially), and persisted as a normal assistant message; it is not an error
  record.
- `docs/report-conversations.md` and `.agents/AGENTS.md` updated: "report ambiguity instead
  of guessing" is satisfied by the clarification answer; deterministic behavior applies to
  explicit reference forms.
- Acceptance: existing conversation matrix tests updated; new tests assert that "what's the
  relation between module X and its tests?" and similar phrasings produce answers or
  clarifications, never exceptions; explicit-reference determinism tests unchanged and green.

### WS5 — Transport hardening

*Goal: the most likely real-world failures are explicit, attributable, and cheap to survive.*

- Prompt-size guard in the Ollama adapter: estimate serialized prompt tokens
  (configurable chars-per-token ratio, default 4), fail with a `ProviderError` naming the
  stage and sizes when `estimated_prompt_tokens + max_output_tokens > context_window_tokens`.
  Record per-stage serialized prompt characters in `execution_metadata`.
- Bounded retry (default 3 attempts, exponential backoff) on connect errors, timeouts, and
  5xx only. Validation failures never trigger transport retry.
- Two timeout classes in `ReasoningModelConfig` (`fast_timeout_seconds`,
  `deep_timeout_seconds`) with a per-task mapping (classification/summarize/repair = fast;
  discovery/analysis/synthesis/alternatives/scenarios = deep). `resources/models.yaml`
  updated with commented defaults; existing single `timeout_seconds` remains as fallback for
  backward compatibility.
- Acceptance: unit tests with mocked transport for oversize-prompt failure, retry-then-
  succeed, retry-exhaustion, and no-retry-on-validation-failure.

### WS6 — Workflow decomposition (mechanical, behavior-preserving)

*Goal: `workflows/consultation.py` (2,166 lines) becomes a readable pipeline.*

- Extract a `StageRunner` that wraps started/artifact/completed progress events, stage
  timing, prompt-identity recording, and the current-stage marker; `advise()` shrinks to the
  pipeline sequence.
- Split into modules under `workflows/`: orchestration (`consultation.py`), evidence
  accumulation (`evidence_accumulation.py`: `_accumulate_query_result`, budgets, selection
  reasons), plan enforcement (`plan_enforcement.py`), packet building, and case-revision
  assembly. Target: no file above ~600 lines.
- No behavior change; the WS0 replay tier and existing integration tests are the guard.
- Documentation pass: `docs/architecture.md` (adapter responsibilities now true as written),
  `docs/report-contract.md` (composition provenance), `docs/advisory-workflow.md`,
  `docs/report-conversations.md`, `.agents/AGENTS.md`.
- New `docs/adr/0001-composed-synthesis.md` recording decision 1 (previous direction, new
  direction, justification, consequences) per master plan §22.

## 4. Sequencing

```text
WS0 (replay tier)
  → WS1 (wire/storage split)      [small, fixes latent bug]
  → WS2 (adapter slimming)        [prerequisite for WS3]
  → WS3 (composed synthesis)      [largest; the confirmed decision]
WS4 (conversation)                [independent of WS2/WS3; may run in parallel after WS0]
WS5 (transport)                   [independent; may run in parallel after WS0]
  → WS6 (decomposition + docs)    [last; needs the dust settled]
```

Approximate sizes: WS0 M, WS1 S, WS2 M, WS3 L, WS4 M, WS5 S, WS6 M.

## 5. Invariant Compliance

Master plan invariants directly exercised: #8/#9 (bounded contexts — strengthened by the
prompt-size guard), #13 (claim classifications — now correct by construction), #14/#15
(validated references, failed validation cannot mutate the case — unchanged), #17 (no
provider tech in core — strengthened by WS2), #19 (the only new abstractions are the wire
DTOs, the composer, and the StageRunner, each with a concrete responsibility). Invariant #21
(old consultations keep their exact versions) is preserved by WS1's read-path migrations.
