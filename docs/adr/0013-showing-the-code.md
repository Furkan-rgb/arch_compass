# ADR 0013 — Showing the code, and demonstrating a recommendation

**Status:** Accepted
**Date:** 2026-07-29
**Supersedes:** none
**Related:** master plan §8A, §12.0, §5.5, ADR 0002, ADR 0011,
`docs/plans/finding-source-excerpts.md`

## Previous direction

A finding carried the coordinates of its evidence and nothing else reached the reader. Each
`FindingParticipant` records `path`, `start_line` and `end_line`, chosen by a deterministic
detector at the moment the verdict was reached — 387 participants across every stored review
in the development workspace, none of them missing one. The finding card printed
`path:line` as a label; `_boundaries_for_reading` and the answering stage presented
qualified names and dropped `location` entirely.

## Problem

One live conversation, three consecutive refusals.

> **Can you show the actual problematic code in question?**
> The review does not provide the actual code snippets you are looking for. […] the record
> only contains the names of these modules and does not include the specific lines of code.

> **Can you show an example fix snippet then?**
> The review does not contain any example fix snippets […] it does not include the actual
> code-level implementations or diffs required to perform those changes.
> *— Not grounded on any reviewed boundary*

> **But I mean can you show one?**
> The review does not contain any code snippets or implementation examples.

Two distinct defects, and only the first is about missing data.

**The evidence was not delivered.** The first answer is accurate about what reached the
stage and false about what the review holds. Nothing needed to be found — the spans were
recorded, immutable, and chosen when the verdict was reached.

**The contract forbade the answer.** The second and third are the stage obeying
ANSWER_REVIEW_QUESTION v4: *"where the record does not settle what was asked, say what is
missing from it rather than closing the gap with a general principle about abstractions."*
That rule is correct for a claim about this repository — a review of six boundaries cannot
speak about a seventh — and was being applied to *"show me how to carry out the
consolidation you recommended"*, which is not a claim about the repository at all. It is
craft, about a recommendation the review had already made and already grounded. With no
category for it, the request fell into *not in the record, therefore decline*.

The refusal also cited nothing, while declining to illustrate BR-007's own
`recommended_response`.

## New direction

Both, because each is worthless alone: without the contract change, excerpts buy
better-informed refusals; without excerpts, permission to write an example buys invented
code.

- **`BoundaryExcerpt` and `ReviewSourceService`.** The recorded span resolved to text, read
  from the repository the review pinned, at request time. Served by
  `GET /api/reviews/{id}/source?reference=BR-nnn&context_lines=N`.
- **The finding card shows it inline**, following what `policy_bearings` already does there
  — *"the substantiation is the reason to believe the verdict"*. Affordable because it shows
  the recorded span and nothing more: the detector picks declaration spans, so a duplicated
  constant is one line per site. Surrounding lines are the unfold.
- **Both conversation stages receive it**, attached to the boundary it belongs to, because
  "which lines are which finding's" is the question being asked. A review-wide conversation
  gets every boundary; a question discussion gets only the cited ones, matching the scope
  that makes it safe to run while verdicts are withheld (§6C.7).
- **ANSWER_REVIEW_QUESTION v5** narrows the refusal rule to *facts about this repository*
  and names the missing category: demonstrating a recommendation is allowed, rests on the
  boundary that recommended it, is labelled an illustration the review never ran, and is
  built from the `source` lines rather than from memory.
- **v6 separates quoting from illustrating**, which v5 had run together under "build it from
  `source` and not from memory". That names where the material comes from and says nothing
  about whether it may be altered — and the first live run answered with the right files,
  the right lines and the right drift while retyping one identifier as `BUILT_IN_EPOCHES`
  and inventing a docstring ending "for the Qwen account" that was really "for a reader",
  fabricating an instance of the very leakage it was asked to show. Reproducing is now
  character-for-character, illustrating may depart only in arrangement, and an altered quote
  is called what it is: a false report about the repository, worse than the refusal it
  replaced, because nobody can grep for a symbol that was never there.

### Not a retrieval tool

The obvious reading — the repository does not fit in the context, so the model needs a tool
to fetch source — is refused. §12.0 is that the application decides what to look at and the
model decides what it means, and `tests/unit/test_boundaries.py` asserts it for this stage
so that *"a model adapter cannot become the thing that chooses its own evidence"*. Selection
was already performed by the detector. This is delivery.

### Pinned on the review, read once when it completes

**Amended.** This originally read from disk on every request and stored nothing, on two
grounds: that storing would make every existing review unreadable under ADR 0002, and that it
invites a worse question — whether the *judge* saw those lines.

The first ground was wrong about the mechanism. ADR 0002 refuses a shim for a *narrowed*
schema; an optional field with a default **widens**, and a review stored without it parses
unchanged and falls through to a live read. `elicited_from` was added exactly this way.

The second ground is real and survives, as a naming problem rather than a storage one. These
are the lines a deterministic detector measured, not the judge's input — judgement is
structural, over the atlas. The field says so where it is defined. Note also that the excerpts
already *are* model input at the answering stage, so storing them changes what is durable, not
who sees them.

What settled it was measuring the live read against a repository being worked on. Freshness is
a single repository-wide fingerprint, so appending one comment to a file no finding cites took
a six-boundary review from sixteen excerpts to none. Three consequences, in the order they
matter:

- A concluded review asked "show me the code" a week later answers with the refusal this ADR
  exists to eliminate — not because the record lacks the lines, but because someone edited
  something else. The fix undid itself on first contact with normal work.
- `BoundaryReview` is documented as pinned to the exact inputs that produced it. Case revision,
  atlas version, model identity and prompt identity are all pinned; the code was the one input
  that quietly expired.
- It costs about 4,000 characters against a 46,000-character stored review.

So the report carries `excerpts`, read once at completion when freshness has just been checked
and nothing has been re-indexed. `context_lines` is the exception and still reads live, because
surrounding code was never recorded: unfolding is browsing rather than evidence, so a
repository that has moved on keeps the pinned span instead of losing it.

## Consequences

- A review keeps answering with its evidence for as long as it is kept, whatever happens to
  the repository afterwards. The freshness caption still exists and now applies only where it
  is the honest answer: a review stored before excerpts were pinned, which reads live and
  carries *"this repository has changed since the review ran"* in place of its text.
- Absence is a stated outcome in three shapes and none is an error: a stale or missing
  repository, a node with no span, and a boundary that was never written — which is what a
  greenfield candidate is (§4.1) and the reason `location` is optional at all.
- The reasoning port gains `excerpts` on four methods. Third signature change to these this
  cycle; if a fourth is wanted, bundle `(case, excerpts)` into a `ReviewEvidence` value
  rather than adding another positional parameter. *(A fourth was wanted, and `ReviewEvidence`
  is that value.)*
- Budget: five to eight boundaries at two to four spans each, a handful of lines per span —
  order 10–15k characters against an input budget near 490k, and bounded by the detector
  rather than by anything a model asks for.
- An illustrated fix is never stored. It is composed per question, in the answer, and is not
  a field on a finding: the recommendation is the review's, and an illustration of it is a
  conversational aid that must not harden into evidence.
- **A quote in an answer is retyped prose and cannot be trusted the way the finding card
  can.** v6 is measurably better and is not a guarantee: across live runs the fabricated
  identifier and the fabricated docstring both stopped, and a later run still returned
  `"chelsine"` for `"chelsie"` inside a string literal. A contract cannot make token-by-token
  transcription reliable, so the finding card — which renders `source` straight from disk and
  never passes through the model — stays the authority, and the honest reading of a quoted
  line in a conversation is that it is the model's report of the code, not the code. Closing
  this properly means the answer citing a span the interface expands rather than retyping it,
  which is a change to how an answer is rendered and belongs in its own decision.
- The span is the declaration, which is the right evidence for a duplicated constant and the
  wrong evidence for a leaked name: BR-008 is about `qwen` appearing in five modules, and
  what `source` carries for it is each module's docstring, not the referencing lines. Asked
  to show that leakage, the stage correctly said the lines were not in front of it and
  described the change in prose — the contract working, on evidence that does not reach the
  question. What a `name_leakage` boundary should record is a separate matter from delivery.
