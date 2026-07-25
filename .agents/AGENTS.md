# Agent Instructions

Before making substantial changes, read:

1. `docs/master-plan.md`
2. The relevant subsystem documents under `docs/`
3. Existing tests and evaluation cases

`docs/master-plan.md` is the authoritative product and architecture direction. Implement only the requested milestone; do not automatically build later roadmap phases.

V1.2 is the active milestone. Preserve these report-conversation boundaries:

- Conversations may be created only for a validated successful `ConsultationRun`.
- Always use the run's exact case revision, Atlas version, policy-index version, and report.
- Canonical finding node IDs, locations, metric values, signals, and policy IDs are projected by
  the application from the finding's own focused packet. Provider-authored artifact values or
  cross-cluster evidence are not trusted; revalidate cluster coverage after repair and assign
  ordered `FIND-001…n` IDs only after final canonicalization.
- Supply all one to twelve finding digests and the exact pinned case title, problem, desired
  outcome, actors/workflows, requirements, quality attributes, technical/organisational/derived
  constraints, confirmed facts, expected changes, non-goals, and assumptions. Retrieve detailed
  finding evidence only for the current question.
- Never pass a full Atlas, repository root/tree, policy corpus, or unlimited history to reasoning.
- Apply the cumulative per-turn ceilings: eight actions, twelve findings, twenty-four unique
  Atlas/path nodes, eight policies, neighbourhood depth two, 120 lines per excerpt, 180 excerpt
  lines total, and 24,000 retrieved characters. Scope every exact retrieved artifact independently
  as original-run or additional-conversation evidence.
- Every factual answer statement must identify its supporting answer claims, findings, or report
  claims. Rendering is derived from the validated structured answer.
- Resolve finding references by ID, exact title, numeric/word ordinal, and unambiguous recent
  reference. Preserve multiple explicit titles for comparisons and report ambiguity instead of
  guessing.
- Keep deterministic behavior for summaries, details, all-finding priority, comparisons,
  evidence/source traces, policy applicability/exceptions, alternatives, scenarios, assumptions,
  implementation order, strengthening/weakening counterfactuals, and unsupported questions.
- Use the shared canonical JSON serializer for every Ollama prompt input and context hash. Bump
  affected prompt versions and record only identities that actually executed.
- Conversation messages are append-only; use compare-and-swap revisions for ordering.
- Durable message retrieval records contain bounded references and audit metadata, not copies of
  report findings, Atlas query payloads, or policy documents.
- Counterfactual answers are labelled hypotheticals and never revise the case or recommendation.
- One constrained answer repair is permitted; invalid repaired output is recorded as a failed
  attempt, not appended as an assistant answer.
- Summaries cover exactly the first twelve messages and fixed batches of eight thereafter, only
  after an assistant answer is committed. Invalid summaries do not advance coverage; a summary
  failure is recorded and must not turn a valid persisted answer into a failed request.
- Keep the deprecated `report_follow_ups` table and its data during V1.2 migration; its API and UI
  remain removed and its rows are not converted into conversations.
- Synthesis returns a `ProposedRecommendation`, never a report. Do not add fields to it for
  anything ArchCompass owns: design forces, alternatives, scenarios, policy evidence, claim or
  finding identity, report section placement, or finding Atlas/metric/signal/policy evidence.
  `application/synthesis.py` composes the persisted report. See
  `docs/adr/0001-composed-synthesis.md`.
- Model adapters do transport, schema constraint, and one generic JSON repair. They hold no
  domain rule and may not import the application or workflow packages.
- Model transport refuses an oversize request rather than letting it be truncated, and retries
  only positive-listed transient failures. Never retry a structured-output failure: the one
  schema-repair round is the only second attempt at content.
- Conversation adapters and services are composed only in `bootstrap.py`.
- There is no conversation React UI in V1.2.
- Domain models validate the current schema only. Do not add upgrade validators, defaulted
  `schema_version` fields, validation aliases for superseded names, or in-band flags that exempt
  a value from validation; a stored row that no longer parses is reported through
  `UnreadableStoredRecordError` and the consultation is re-run. See `docs/adr/0002-legacy-purge.md`.
- Mandated V1.2 ceilings live in `archcompass.domain.budgets`. Configuration may lower a ceiling,
  never raise one.
