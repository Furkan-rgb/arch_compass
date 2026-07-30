# ADR 0014 — An answered question is stored as a pair

**Status:** Accepted
**Date:** 2026-07-30
**Supersedes:** none
**Related:** master plan §6C.2, §6C.4, §12.0, invariant 25, ADR 0002 (no shims for
narrowing), ADR 0011 (questions worth answering), ADR 0012 (answer provenance)

## Previous direction

A review's question named the case field its answer belonged in — one of the five that decide
a verdict: `expected_future_changes`, `confirmed_facts`, `technical_constraints`, `non_goals`,
`assumptions`. The browser composed one line from the question and the reply, joining the
question's `unknown` to the answer with a dash:

> Whether a second audio sink implementation is required — Not for now no.

That line was shown in the preview, editable there, and submitted as `recorded_text`.
`CaseService.answer` appended it to the named list, setting a statement kind where the list
holds statements. The question–answer pairing survived only as provenance on the revision
event, in `RecordedAnswer`.

## Problem

The composition existed for a real reason. A case entry is read with no question beside it —
by the second pass, which judges against the case snapshot and nothing else, by every later
review, and by whoever opens the case editor. Without a subject in the sentence, "they
shouldn't rely on it" entered `assumptions` from a live run with its "it" referring to
nothing. Composing fixed that, and it was paid for twice.

1. **The reader was shown the same sentence twice.** The questions surface printed the
   question, then a preview box holding a line that opened by restating it. The one screen
   whose job is to show what is about to enter the case spent half its width on a paraphrase
   of the question directly above it.
2. **The re-judging stages never saw the question.** They are given `case.model_dump()`, so
   what reached them was the join and not the exchange. The context that made an answer
   legible was the one thing they could not read, and the check that ends the elicitation loop
   — *has the reader already told me this?* — had to be made against a paraphrase rather than
   against the questions actually asked.

The line was also the only text in the case that nobody wrote. The user typed a reply, the
advisor wrote a subject, and the browser produced a third thing from both — inside a design
whose central rule (invariant 25) is that a case holds what its author wrote.

## New direction

The pair is first-class in the case.

- **`Clarification`** — `question` (the review's, verbatim), `answer` (the user's words), and
  `bears_on` (which of the five deciding fields the answer carries the force of). Both halves
  require content; neither is composed from the other.
- **`ArchitectureCase.clarifications`** holds them, and `CaseUpdate.clarifications` revises
  them. `CaseService.answer` appends a pair per answered question and touches nothing else on
  the case; the five lists are no longer written by answering at all.
- **`bears_on` is not a destination.** Nothing is moved anywhere. It says how a later judgement
  weighs the pair, and the judging and summarising contracts now state the rule in as many
  words: an answer bearing on `technical_constraints` binds the design like a listed
  constraint, one bearing on `non_goals` rules its subject out.
- **`clarifications` joins the fields the judging stage must read before it hinges**
  (`judge-finding-candidate` v11). This is what terminates the loop. A stage that cannot
  recognise an answer it has already been given hinges on the same fact for ever, and the
  reader is handed back a question they replied to.
- **The browser composes nothing.** `composeCaseLine` and the second piece of state that held
  the reader's edits to it are gone; `OpenQuestions` submits `{question_reference,
  recorded_text}` where `recorded_text` is the raw answer. Its preview shows the pair —
  question muted and attributed to the review, answer in a box and still editable — grouped by
  `bears_on` as before.
- **The case form gains a clarifications section**, shown only where a review has asked
  something. The answer is editable, the pair is removable, and the question is prose rather
  than an input: a case that claimed a review asked something it never did would be a
  fabricated record of an exchange.

### `schema_version` stays at 2

This is widening. A field with a default breaks no stored document: every case already in a
workspace validates unchanged with the list empty, so there is nothing to migrate and no
migration is shipped. ADR 0002 governs *narrowing* — a schema that has stopped accepting what
it used to — and its remedy is to produce the record again, which a case cannot be, because
nobody can re-type what someone wrote. The same reasoning is already written on
`problem_statement`, which was relaxed rather than removed for exactly this reason.

### Rejected: keep composing, and also store the pair

Storing both would put the same answer in the case twice, in two wordings, with nothing saying
which one a stage should believe. The composed line is derived from the pair, so it is a cache
of a fact stored beside it — and the first edit to either half makes them disagree.

### Rejected: point `RecordedAnswer` at the pair it wrote

`recorded_text` stays a copy. Provenance is about one immutable revision, and a later revision
may reword an answer or delete the pair outright without making the record of what was answered
wrong. A pointer would go stale in exactly the case the provenance exists for.

### Rejected: let the client send the question

The question half is read from the review's own report, like `bears_on` already was (§12.0). A
client that could supply it could put words in a review's mouth, and nothing afterwards could
tell that from a question the review asked.

## Consequences

- `judge-finding-candidate` goes to v11, `elicit-questions` to v3, `summarise-review` to v7.
  Prompt identity is recorded on every review, so runs before and after this remain
  distinguishable without any of them becoming unreadable.
- `answer_belongs_in` on `OpenQuestion` and `RecordedAnswer` keeps its name and its type, and
  changes meaning from *where the line is filed* to *what the answer weighs*. The elicitation
  request now asks for it in those terms, because a stage told it is filing a sentence picks by
  where the words look tidiest.
- `OpenQuestion.unknown` keeps its place. It is no longer half of a composed line, and it is
  still what the question is about — which is what titles a question's discussion thread and
  what lets a reader recognise the same subject across two passes.
- The deterministic substitute counts a clarification bearing on `expected_future_changes` as
  being told about the future. Reading only the list would have left every offline run hinging
  for ever on questions it had already had answered.
- A case now records the exchange that shaped it, which is worth having on its own: a reader
  opening a case months later can see what they were asked and what they said, rather than a
  list of sentences in a voice that is nobody's.
