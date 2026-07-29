# ADR 0011 — Questions worth answering, and answers that survive being recorded

**Status:** Accepted
**Date:** 2026-07-29
**Supersedes:** none
**Amends:** ADR 0010 (adds §6C.7 alongside its two-pass flow)
**Related:** master plan §6C.2, §6C.4, §6C.5, §6C.7, §12.0, invariant 25

## Previous direction

ADR 0010 made a first pass stop and ask. What it asked, and what became of the answer, was
left as §6C.2 had specified it: an `OpenQuestion` carried `unknown`, `why_it_matters` and
`question`; the workspace wrote the reader's reply verbatim into one of five case fields;
and a review still waiting on answers refused every conversation about itself.

## Problem

A live run against `gemma4:26b` produced five questions, and reading them beside the case
they produced showed three separate defects.

**The description restated the question.** The contract asked for the unknown "as the
circumstance the case does not state rather than as a question" — a grammatical instruction,
which got a grammatical answer. Every one of the five was its own question with the
interrogative filed off:

> **Q-5.** do modules like `narration/planning.py` and `preflight/voices.py` rely on the
> specific identity of 'qwen', or is this leakage unintentional?
> *whether modules like `narration/planning.py` and `preflight/voices.py` rely on the
> specific identity of 'qwen' to function.*

`why_it_matters` fared no better: all five came back as "If confirmed, X should stay; if
denied, it should be removed", which is true of every question this stage can ever ask and
therefore worth nothing to someone choosing which to spend an afternoon on. Meanwhile the
input already held what a useful description needs — the abstraction named, the detector's
measurements and limits, and the judging stage's own `if_confirmed`/`if_denied` — and the
contract never asked for any of it.

**The recorded answer lost its subject.** Answers were appended verbatim, so the case
accumulated entries like:

```
assumptions:
  - text: They shouldnt rely on it
```

Nothing downstream ever sees the question again. The second pass judges against the case
snapshot alone, so "it" refers to nothing; and the case is the durable artifact, read by
every later review and by whoever opens the case editor.

**A reader who did not understand a question had nowhere to go.** The conversation service
refused `awaiting_answers` outright. The reasoning was that its verdicts are the ones being
withheld — sound for a conversation about the review, and the wrong answer for someone stuck
on the question itself, who is being told to answer it before they may ask what it means.

## New direction

Master plan §6C.7. Three changes, none of which weakens invariant 25.

- **`what_the_review_saw` is added to `OpenQuestion`**, required, and leads the shape because
  it is the only field written from evidence rather than from the question. `unknown` is
  re-specified as a one-line *subject* rather than a description, and stops being rendered as
  prose. `why_it_matters` is pointed at the hinges' two branches. ELICIT_QUESTIONS goes to
  v2.
- **The recorded case line is composed from `unknown` and the answer**, deterministically, in
  the workspace, and is editable in the preview before it saves. No model is asked to
  rephrase anything: text a model wrote into a case unseen is what invariant 25 exists to
  prevent, and a rephrasing call would be exactly that with a nicer result.
- **A conversation may be pinned to `(review, Q-n)`** and is the only kind a waiting review
  will open. It is shown that question, the boundaries it cites and no others, the case, and
  the method background. It may offer `suggested_answer`; that field exists only in
  DISCUSS_OPEN_QUESTION's reply schema, so the review-wide stage cannot produce one. A
  suggestion fills the answer box on the reader's click and then walks the same preview as
  anything typed by hand.

Separately, the questions are now walked one at a time with every step revisitable, and
submitted as one revision at the end. Presentation only; the batching rule is unchanged.

### Rejected: send the question to the judging stage

The direct repair for the lost subject is to pass the Q&A pairs into
`judge_finding_candidate` alongside the case. Refused on three grounds, the last decisive:

1. It repairs one hop. The orphan line stays in the case for every later reader.
2. It is more code — a wider port signature, a bump to the hottest contract in the system,
   and new prose about precedence when the case and the Q&A disagree.
3. It breaks the pin. A review's inputs are its case revision, atlas version and policy set.
   A judge that also read the eliciting review's record would let two reviews of the same
   revision reach different verdicts, and no verdict would be reproducible from what it says
   it ran against.

## Consequences

- `OpenQuestion` gains a required field, so a stored review written before this raises
  `UnreadableStoredRecordError` and is re-run. That is ADR 0002's rule, not an exception to
  it: a defaulted field would not be required in the model-facing schema, which is the
  failure mode that ADR exists to prevent.
- `StreamingAnswerReasoner` gains `stream_open_question_discussion`. The protocol is
  `runtime_checkable` and compares method names, so a partial double that omits it silently
  stops being a streaming reasoner — the existing doubles state their conformance where they
  are defined, and the one in `test_review_conversations.py` now carries the method for that
  reason.
- A review-wide conversation about a waiting review is still refused, and its message now
  names the alternative rather than only the prohibition.
- `ReviewAnswer.suggested_answer` is carried on every answer and is empty on all but one
  path. That is deliberate: which stage can fill it is enforced by the reply grammar rather
  than by a second type, the same technique that stops `summarise_review` reopening the
  elicitation loop.
