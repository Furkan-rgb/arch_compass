# Spec — Answer provenance on a case revision

**Status:** Implemented — see ADR 0012
**Fills:** master plan §6C.4 — *"A revision may record which review and question it answers.
That is provenance, not write-back."* Never built.
**Related:** §6C.7, ADR 0007 (removed `origin_run_id`), ADR 0011, invariant 25

## The gap

Everything either side of the answer is already immutable and already kept:

- The **questions** live in the pass-1 review, for ever, and cannot change.
- The **case** is append-only: one full snapshot per revision, with actor and timestamp, and
  every review pins the revision it judged.
- The **discussion** about a question is stored, pinned to `(review_id, question_reference)`.

What is not recorded is the arrow between them. Revision N+1 holds the answer *text* and
nothing that says which question produced it, so four questions are unanswerable today:

- Which questions did I skip?
- What did I answer to Q-3?
- Where did this line in my case come from?
- Did answering Q-2 actually move that verdict?

The last one is the expensive one. The whole justification for two passes is that answers
move verdicts — measured at four of five on `warehouse-sync` — and right now that can only
be observed in aggregate. No individual answer can be attributed to the verdict it moved.

## Shape

One optional block on `CaseRevision`, beside `event_type` and `actor` — not inside
`snapshot`.

```python
class RecordedAnswer(DomainModel):
    """One question this revision answered, and the line that answered it."""

    question_reference: str = Field(pattern=r"^Q-[0-9]+$")
    #: The field the line joined, so it can be found in the snapshot.
    answer_belongs_in: CaseField
    #: What was recorded, verbatim, as it entered this revision.
    recorded_text: str = Field(min_length=1)


class AnsweredQuestions(DomainModel):
    """What prompted this revision: one round of answering one review's questions."""

    review_id: str = Field(min_length=1)
    answers: list[RecordedAnswer] = Field(min_length=1)


class CaseRevision(DomainModel):
    ...
    #: Absent where the revision was authored by hand, present where it came from
    #: answering. Its absence is the thing that tells the two apart.
    answered: AnsweredQuestions | None = None
```

Three deliberate differences from the first sketch in conversation:

1. **No `skipped` flag.** It is derivable — the questions in `review_id`'s report minus the
   ones with an entry here — and the codebase's own rule is that a field the application can
   compute is not asked for or stored (`ReviewAnswer.grounded` is a property for exactly this
   reason). Exposed as `skipped_references(questions)` rather than persisted.
2. **`review_id` lifted out of the entries.** One round of answering produces one revision
   against one review's questions, so repeating it per answer invites a state where it
   differs. Putting it on the block makes that unrepresentable.
3. **`answer_belongs_in` added.** Without it the recorded text can be read but not located,
   and "which entry in my case is this" needs a scan of five lists.

### Why `recorded_text` and not a pointer

The three plain fields (`expected_future_changes`, `technical_constraints`, `non_goals`) are
lists of bare strings with no identity; only `confirmed_facts` and `assumptions` carry a
`CaseStatement.id`. Giving all five statement identity is a much larger change and would
alter what a case *is*.

Storing the text is not a workaround, it is the more honest record: this is provenance about
one immutable revision, so the text at that revision is a fact and cannot rot. A later
revision may reword the line; that does not make this record wrong, it makes it history.

### Why not on the review, and why not in the snapshot

- **Not on the review.** Reviews are immutable advisor output. Writing the user's answers
  into one would mean a review record changes after it was produced, which is the property
  every pin in the system depends on.
- **Not in `snapshot_json`.** The snapshot is the `ArchitectureCase`, and a case must stand
  alone. A `Q-2` inside it would make the case unreadable without the review that produced
  it, and would put an advisor-assigned identifier into a user-authored document.
- **Not `origin_run_id` again.** ADR 0007 removed a field marking revisions *authored by a
  run*. This marks a revision the user authored and says what prompted it — §6C.4 draws
  exactly this distinction. Invariant 25 is untouched: nothing here is written by a model,
  and the answer is still the user's.

## Storage

Migration `019_a_revision_records_what_it_answered.sql`: one nullable column and a unique
index over `$.review_id`.

Rebuilt rather than `ALTER TABLE ... ADD COLUMN`, which was the first attempt and fails. A
migration at or above a retired version number is replayed against a workspace that already
applied it, and a bare `ADD COLUMN` dies there on `duplicate column name` — the rebuild is
idempotent, which is what the replay needs, and is the pattern 013, 014 and 018 use.

Nothing is backfilled. Existing revisions carry NULL, which is truthful — they were authored
by hand as far as anything recorded knows. Snapshots are full rather than incremental, so no
existing history has to be reinterpreted.

## How it is written

Today the browser does two calls: `PATCH /api/cases/{id}` with a client-composed update, then
start the second pass. Provenance written that way is optional by construction — a client
that forgets it produces a revision that silently loses the link.

One route that cannot lose it.

```
POST /api/reviews/{review_id}/answers
  { "answers": [ { "question_reference": "Q-2", "recorded_text": "..." }, ... ] }
  → CaseRevision
```

The server resolves each `Q-n` against that review's own report (refusing one it never
asked, exactly as the conversation service already does), reads `answer_belongs_in` from the
question rather than trusting the client, composes the `CaseUpdate`, applies it, and records
`answered` in the same transaction. The client still sends final text, because the reader
edits the composed line before saving and that edited line is what must be recorded.

`CaseUpdate` is left alone. "Edit my case" and "answer a review's questions" are different
operations with different provenance, and folding the second into the first is what made the
link optional in the first place.

## What it unlocks

- **Attribution.** Pass-1 verdict for BR-005, plus the answer to the question citing BR-005,
  plus the pass-2 verdict — the existing `WhatChanged` panel can stop saying "four verdicts
  moved" and start saying which answer moved which.
- **A skipped list.** "You left two unanswered" is derivable and worth showing.
- **Provenance in the case editor.** A line can say where it came from and link to the
  question, and through `(review_id, question_reference)` to the discussion that produced it
  — a join that already exists and is currently unreachable.
- **Evaluation.** `scripts/run_boundary_review.py` can score which *questions* were worth
  asking, not only whether the verdicts ended up right.

## Decisions taken

1. **The route.** `POST /api/reviews/{id}/answers`, and `PATCH /api/cases/{id}` is hand-edit
   only. Two ways to do the same thing is how the link went missing.
2. **Multiple rounds.** Enforced by a unique index over `answered.review_id`. In practice the
   service's stale-revision check fires first — answering appends onto the revision the review
   pinned — so the index is the backstop for a caller going around the service.
3. **Scope of display.** Attribution in `WhatChanged` landed. Case-editor provenance and the
   skipped list are still to do.

## Still to do

- Provenance in the case editor: a line saying which question it came from, linking to the
  question and through `(review_id, question_reference)` to the discussion that produced it.
- A skipped list on the second pass — "you left three unanswered", derived rather than stored.
- `scripts/run_boundary_review.py` scoring which *questions* were worth asking.

## Not in scope

- Statement identity for the three plain case fields.
- Any change to how questions are asked, composed, or discussed (§6C.7 as shipped).
- Backfilling the existing 80 revisions. There is nothing to backfill from.
