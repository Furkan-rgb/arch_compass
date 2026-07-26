# Agent Instructions

Before making substantial changes, read:

1. `docs/master-plan.md`
2. The relevant subsystem documents under `docs/`
3. Existing tests and evaluation cases

`docs/master-plan.md` is the authoritative product and architecture direction. Implement only
the requested milestone; do not automatically build later roadmap phases. Where this file and
the master plan disagree, the master plan governs.

The review-centred workspace (master plan §16) is the active milestone. Preserve these
boundary-review and review-conversation boundaries:

- A `ReviewConversation` may be created only for a `BoundaryReview` that succeeded and carries
  a report. A review that failed has nothing to discuss.
- A conversation uses the exact case revision and atlas version its review pinned. Reading that
  revision when the conversation is created is the check that the grounds can still be shown,
  not decoration.
- Nothing the model writes is ever used as a key (master plan §12.0). `BR-nnn` references,
  policy bearings and answer citations are all resolved by ArchCompass from positions in the set
  it presented: boundaries stay in the order the review stored them, presented policies are
  never reordered between a call and its result, and no stage parses an identifier out of model
  text.
- Whether an answer is grounded is derived from the citations it returned, never asked of the
  model. An answer that rests on no boundary is labelled as such rather than presented as
  something the review supports.
- Never pass a complete atlas or a repository tree to reasoning. The whole policy corpus goes
  with every candidate and the whole review with every conversation turn because both were
  measured to fit — that is a measured budget, not an absent one.
- The prompt budget is derived from the configured context window less reserved output
  (`adapters/models/structured.py`), never a frozen constant. Transport refuses a request that
  does not fit rather than letting a provider truncate it silently.
- Use the shared canonical JSON serializer (`domain.base.canonical_json`) for every structured
  prompt input, so the same evidence produces the same request text.
- Conversation messages are append-only, ordered by a compare-and-swap on message count inside
  the write.
- A turn whose provider call failed is appended as a failed message — never as an assistant
  answer, and never dropped. A question that produced nothing is part of the history a reader
  needs to make sense of what follows.
- One constrained repair round is the only second attempt at content. Never retry a
  structured-output failure; retry only positive-listed transient transport failures.
- Reviews are immutable, and an old review keeps the exact case, atlas and policy versions it
  used. A conversation never revises the case or the review; changed circumstances are a new
  case revision and a new review.
- A review records every boundary examined, cleared ones included. A report listing only
  problems reads the same whether every boundary was cleared or none was inspected.
- The judgement stage returns one verdict per candidate, never a report. Do not add fields to it
  for anything ArchCompass owns: boundary identity or ordering, policy identity, positions, or
  report composition. `application/reviews.py` composes the persisted review and `domain/review.py`
  assigns `BR-nnn` by position. See `docs/adr/0001-composed-synthesis.md`.
- Model adapters do transport, schema constraint, and one generic JSON repair. They hold no
  domain rule and may not import the application package.
- A prompt's identity is its stage name, version and content fingerprint
  (`adapters/models/prompt_contracts.py`). Editing a prompt's text changes its identity, so bump
  the stage version deliberately, and record only the identity that actually executed.
- Adapters and services are composed only in `bootstrap.py`.
- The workspace's question dock is a pure client of the existing `/api/review-conversations`
  routes: no new backend path, no alternate domain flow. See
  `docs/adr/0004-conversation-panel.md`.
- Domain models validate the current schema only. Do not add upgrade validators, defaulted
  `schema_version` fields, validation aliases for superseded names, or in-band flags that exempt
  a value from validation; a stored row that no longer parses is reported through
  `UnreadableStoredRecordError` and the review is re-run. See `docs/adr/0002-legacy-purge.md`.
- A numeric limit has one named home in the domain — `MAX_QUESTION_CHARACTERS` in
  `domain/review_conversation.py` — rather than being restated at call sites. Configuration may
  lower a ceiling, never raise one.
