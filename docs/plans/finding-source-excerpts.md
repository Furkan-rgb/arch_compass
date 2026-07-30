# Spec — The code a finding was measured from, and the code that would fix it

**Status:** Implemented — see ADR 0013
**Related:** master plan §8A (finding candidates), §12.0 (the application decides what to
look at), §5.5 (pinning), ADR 0002, `docs/plans/answer-provenance.md`

## The gap

A live conversation was asked to show the code behind a finding and answered:

> The review does not provide the actual code snippets you are looking for. […] the record
> only contains the names of these modules and does not include the specific lines of code.

That is accurate about what reaches the stage and wrong about what exists. **Every
participant of every candidate already carries an exact span.** Across every review stored
in the development workspace — 387 participants — not one lacks a location:

```
frontend.catalogue.BUILT_IN_VOICES   → frontend/catalogue.py:8-8
narration.planning.BUILT_IN_VOICES   → narration/planning.py:10-10
preflight.voices.BUILT_IN_VOICES     → preflight/voices.py:9-9
provider.qwen.BUILT_IN_VOICES        → provider/qwen.py:9-9
```

The detector has already decided which lines are the evidence. What is missing is only the
text at those coordinates: `_boundaries_for_reading` and the answering stage both present
the qualified names and drop `location`, and the finding card on the page prints
`path:start_line` as a label rather than as content.

## The second half of the same complaint

The transcript did not stop at one refusal. Asked next for an example fix, and then asked
again after pushing back, the stage declined both times:

> The review does not contain any example fix snippets for the identified issues. While it
> provides text-based recommendations […] it does not include the actual code-level
> implementations or diffs required to perform those changes.
>
> *— Not grounded on any reviewed boundary*

That is a different defect and excerpts do not fix it. The stage is following its contract
exactly:

> Where the record does not settle what was asked, say what is missing from it rather than
> closing the gap with a general principle about abstractions.

The rule is right for a **claim about this repository**: a review that examined six
boundaries cannot speak about a seventh, and inventing one is the failure that rule exists
to stop. But "show me how to carry out the consolidation you recommended" is not a claim
about this repository. It is craft — how one writes the change the review already argued
for, and already grounded. The contract has no category for it, so it lands in *not in the
record, therefore decline*.

Note also that the refusal cited nothing. An example fix for `BUILT_IN_VOICES` rests on
BR-007, whose own `recommended_response` is to consolidate it; the stage marked every
boundary false while declining to illustrate a recommendation one of them made.

### ANSWER_REVIEW_QUESTION v5

Add the missing category, and keep the rule it was crowding out.

- **A claim about this repository comes from the record.** Unchanged. Do not name a module,
  a call site or a dependency you were not shown, and do not report a fact the review did
  not establish.
- **Demonstrating a recommendation this review made is allowed and is often the useful
  answer.** The reader is being told to consolidate a constant or remove an abstraction;
  showing what that looks like is helping them act on a verdict, not adding a finding.
- **Ground it on the boundary that recommended it.** An illustration of BR-007's
  recommendation rests on BR-007, and marking every boundary false while discussing one of
  them is wrong.
- **Label it for what it is.** An illustration of the recommended change, not something the
  review found, ran or verified. Never present a diff as reviewed evidence.
- **Build it from the excerpt, not from memory.** Where the lines are in the input, the
  example edits those lines. Where they are not, say the shape of the change in prose and do
  not invent identifiers to make an example look concrete.

The two halves compose, which is why they are one spec. Without the contract change,
excerpts buy better-informed refusals. Without excerpts, permission to write an example
buys invented code.

The same over-broad refusal exists in `DISCUSS_OPEN_QUESTION` ("a question about something
outside them is one you cannot answer from evidence"). It matters less there — that stage
exists to help someone decide, not to help them act — and it is left alone until measured.

## Not a retrieval tool

The obvious reading of "we cannot fit the repository in the context" is that the model needs
a tool to fetch source. That would be the wrong shape here, and not only unnecessary.

§12.0 is that the application decides what to look at and the model decides what it means.
`tests/unit/test_boundaries.py` asserts it for this exact stage: its parameters are the
pinned review, the history, the question and the background, so *"a model adapter cannot
become the thing that chooses its own evidence."* A tool the model calls inverts that.

There is nothing to search for. The spans are recorded, immutable, and were chosen by a
deterministic detector at the moment the verdict was reached. Selection is done; this is
delivery.

## What already exists

Almost all of it. Nothing here needs building from nothing:

- `SafeSourceReader.excerpt(root, path, start, end, *, max_lines)` — refuses symlinks,
  refuses paths that escape the repository root, clamps to `max_lines`, and returns text
  already numbered as `   10 | BUILT_IN_VOICES = (...)`.
- `SourceExcerpt(node_id, location, text)` — the domain shape.
- `SourceExcerptQuery(node_id, context_lines=3, max_lines=80)` — bounds, with ranges.
- `AtlasFreshnessService.ensure_fresh(atlas)` — compares the repository's current content
  fingerprint, git commit and parser version against the atlas the review pinned.

They are wired to one atlas query and to nothing else. This spec wires them to findings.

## Where the text comes from

**Superseded while building. Read once when the review completes, and pinned on the report.**
This section planned a live read at request time; ADR 0013 records why that was reversed and
what replaced it. Kept here rather than deleted, because both objections below were sound and
only one of them was fatal.

- *"Storing changes a stored shape, so ADR 0002 makes every existing review unreadable."*
  Wrong about the mechanism. ADR 0002 refuses a shim for a **narrowed** schema; an optional
  field with a default widens, and a review stored without it parses and falls back to a live
  read. `elicited_from` was added the same way.
- *"Did the judge see those lines?"* Still the right question, and the answer is no —
  judgement is structural, over the atlas. That makes it a naming problem, settled where the
  field is defined. The excerpts are already model input at the answering stage regardless.
- What decided it: a live read expires. Freshness is one repository-wide fingerprint, so
  appending a comment to a file no finding cites took a six-boundary review from sixteen
  excerpts to none — at exactly the point someone starts acting on the findings.

The split still stays clean: the verdict rests on structure, and the code is recorded because
a reader will ask for it.

The repository is read at completion, when freshness has just been checked and nothing has
been re-indexed since — so the text is the text that was judged, by construction. Afterwards
the repository may change freely without costing the review its evidence. The stated absence
still exists for the two cases that are genuinely absent: a participant with no recorded span,
and a review stored before excerpts were pinned, which reads live and says so.

`context_lines` is the one thing that still reads at request time, because surrounding code
was never recorded. That read is allowed to fail — unfolding is browsing rather than evidence
— and it falls back to the pinned span rather than losing it.

## Surfaces

### 1. The finding card

Each `BR-nnn` shows the lines it was measured from, inline.

Inline rather than collapsed, matching what `policy_bearings` already does on that card —
*"Open, not collapsed. The substantiation is the reason to believe the verdict, and a reader
should not have to go looking for it."* Code is bulkier than a bearing sentence, so the rule
is: **the recorded span and nothing more.** That is small by construction — the detector
picks declaration spans, so `duplicated_knowledge` is one line per site and
`sole_implementation` is roughly five to ten per participant.

Context is the unfold. A "show surrounding lines" control re-requests the same span with
`context_lines`, so the disclosure is for *more* rather than for the evidence itself.

Each excerpt is labelled with `path:line` and the participant's role, which the candidate
already states ("States BUILT_IN_VOICES at this location.", "Declares the abstraction.").

### 2. The conversation stages

`_boundaries_for_reading` and both answering stages gain the excerpts beside each boundary
they already present. A question like *"show me the code"* or *"why is that a leak"* is then
answerable from the input.

Budget: a review has roughly five to eight boundaries with two to four spans each, at a
handful of lines per span — order 10–15k characters against an input budget near 490k, and
bounded by the detector rather than by anything a model asks for.

The contracts gain one rule: the excerpt is what was read at those lines, so quote it and
never write code that is not in it.

## Absence

Every brownfield participant observed so far has a location, but the surface must handle
absence in three cases, and must state which one it is rather than showing nothing:

1. **Greenfield.** §4.1 has candidates enumerated from the case rather than from an atlas.
   Those boundaries do not exist yet, so there is no file and no line — the honest answer is
   "this boundary is proposed, not written". This is the case that makes absence permanent
   rather than exceptional.
2. **A stale or missing repository.** The atlas fingerprint no longer matches, or the root
   is gone. Say so; do not read.
3. **A node with no span.** `AtlasNode.start_line` is optional and the query service already
   raises `Node … has no source span`. Not observed in practice, and the shape admits it.

None of these is an error to a reader. A finding whose code cannot be shown is still a
finding, and saying why is more useful than an empty panel.

## Shape

```python
class BoundaryExcerpt(DomainModel):
    """One participant's recorded span, and the text at it."""

    reference: str                    # BR-nnn
    qualified_name: str
    role: str                         # the candidate's own words for why this participant
    location: SourceLocation
    text: str | None                  # None where it could not be read
    unavailable: str = ""             # why, in one sentence, when text is None
```

Served by one route, so both surfaces and the CLI read it the same way:

```
GET /api/reviews/{review_id}/source?reference=BR-007&context_lines=0
  → BoundaryExcerpt[]
```

Reference-scoped rather than whole-review by default, so the page requests what it is about
to draw. The review resolves to its pinned case, which resolves to the repository root and
the atlas — nothing about the current workspace state is consulted.

## Decisions taken

1. **Inline for the span, unfold for context**, on the `policy_bearings` precedent.
2. **The excerpts follow whatever the stage may already reason about** — every boundary for
   a review-wide conversation, only the cited ones for a question discussion.
3. **A stale repository captions rather than blocks.** The excerpt carries "this repository
   has changed since the review ran" in place of its text. Showing the lines as reviewed
   would be false; showing nothing lets the stage conclude the review has no source, which
   is the defect being fixed.

## Not in scope

- Storing an example fix anywhere. It is composed per question, in the answer, and is never
  a field on a finding: a recommendation is the review's, and an illustration of it is a
  conversational aid that should not harden into stored evidence.
- Storing source in the review record.
- Showing the judge any source. That would change verdicts and needs its own decision.
- Any retrieval the model drives.
