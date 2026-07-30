# ADR 0012 — A case revision records what it answered

**Status:** Accepted
**Date:** 2026-07-29
**Supersedes:** none
**Related:** master plan §6C.4, §6C.6, §6C.7, invariant 25, ADR 0007 (removed
`origin_run_id`), ADR 0010, ADR 0011, `docs/plans/answer-provenance.md`

## Previous direction

Elicitation kept everything on either side of an answer and nothing in between.

- The questions lived in the pass-1 review, immutable, for ever.
- The case was append-only: one full snapshot per revision, with actor and timestamp, and
  every review pinned the revision it judged.
- The discussion of a question was stored, pinned to `(review_id, question_reference)`.

The answer itself was appended to a case list as text, by the browser, through
`PATCH /api/cases/{id}`. §6C.4 said a revision *may* record which review and question it
answers. Nothing did.

## Problem

`case_revisions` was `(case_id, revision, event_type, actor, created_at, snapshot_json)`, so
four ordinary questions had no answer: which questions did I skip, what did I say to Q-3,
where did this line in my case come from, and did answering Q-2 actually move that verdict.

The last is the expensive one. The entire justification for judging twice is that answers
move verdicts — measured at four of five on `warehouse-sync` — and that could only be
observed in aggregate. `WhatChanged` could report "four verdicts moved" and could not name
the sentence that moved any one of them, which leaves the product's central claim asserted
rather than checkable.

The write path made it worse than an omission. Provenance composed by a client is
provenance a client can forget, and a revision written without it is indistinguishable
afterwards from one somebody typed by hand.

## New direction

Master plan §6C.4, rewritten from *may record* to *records*.

- **`CaseRevision.answered`** — an optional `AnsweredQuestions` carrying `review_id` and one
  `RecordedAnswer` per question answered: `question_reference`, `answer_belongs_in`, and the
  `recorded_text` as it entered this revision. Its **absence** marks a hand-authored
  revision, which is the only thing that tells the two apart.
- **Skipped questions are absent, not flagged.** What was skipped is the review's questions
  minus the ones recorded — `skipped_references()` computes it. A stored flag would be a
  second copy of a fact that can be derived, which is the rule `ReviewAnswer.grounded`
  already follows.
- **`POST /api/reviews/{id}/answers`** is how answering happens. The server resolves each
  `Q-n` against that review's own report, reads the destination field from the question,
  composes the revision and records the provenance in one transaction. The client sends the
  reference and the line the reader saw — never a destination.
- **`PATCH /api/cases/{id}` is hand-edit only.** Two ways to do the same thing is how the
  link went missing.
- **`WhatChanged` names the answer behind each moved verdict**, joining the question's
  `supporting_references` to the revision's recorded answers. Where no answered question
  cited the boundary it says nothing, because a verdict can move on what the case says
  overall and inventing a cause there would be worse than naming none.

### Why on the revision

- **Not on the review.** Reviews are immutable advisor output. Writing the user's answers
  into one would mean a review record changes after it was produced, and every pin in the
  system depends on that not happening.
- **Not in `snapshot_json`.** That column holds the `ArchitectureCase`, and a case must
  stand alone. A `Q-2` inside it would make the document unreadable without the review that
  produced it, and would put an advisor-assigned identifier into a user-authored record.
- **Not `origin_run_id` again.** ADR 0007 removed a field marking revisions *authored by a
  run*. This marks a revision the user authored and says what prompted it — the distinction
  §6C.4 has drawn since elicitation was specified. Invariant 25 is untouched: nothing
  recorded here is model-written.

### Rejected: keep the client composing the update

Adding an optional `answered` block to `CaseUpdate` would have been a smaller change and
would have left the link optional, which is the defect. It also leaves the client choosing
where an answer goes, and a client that could name the destination could route an answer
into a list its question never mentioned — with nothing afterwards able to tell that from a
question that did.

### Rejected: statement identity for the three plain fields

`recorded_text` is a copy of the line rather than a pointer into the snapshot, because only
`confirmed_facts` and `assumptions` carry `CaseStatement.id`; the other three destinations
are lists of bare strings. Giving all five statement identity would change what a case *is*,
for a benefit the copy already provides — and the copy is the more honest record, since this
is provenance about an immutable revision and the text there is a fact that cannot rot.

## Consequences

- Migration 019 rebuilds `case_revisions` with a nullable `answered_json` and a unique index
  over `$.review_id`. Rebuilt rather than `ALTER TABLE ADD COLUMN` for the reason 013, 014
  and 018 rebuild: a migration at or above a retired version number is replayed against a
  workspace that already applied it, where a bare `ADD COLUMN` fails on `duplicate column
  name`. Existing revisions carry NULL, which is truthful.
- One review maps to at most one answering revision, enforced by that index. In practice the
  service's stale-revision check fires first — answering appends onto the revision the review
  pinned, so a second round is refused as the stale write it is. The index is the backstop
  for a caller that goes around the service.
- `OpenQuestions` no longer receives the case at all. It composed the whole `CaseUpdate`
  before — reading the pinned snapshot, appending to the right lists, setting statement
  kinds — and now emits `{question_reference, recorded_text}`.
- **"Revise case & review again" and the earlier/newer sibling links are removed.** Not
  because of this change: they navigated by case revision, and following one back to a first
  pass landed the reader on the in-progress screen, which is not where that review is.
  Moving between the passes of a case is worth having and will be built deliberately rather
  than as two arrows in a header.
