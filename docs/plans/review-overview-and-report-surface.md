# Implementation Plan: The review overview and the report surface

**Status:** Proposed plan, implementation pending
**Decides:** ADR 0007 (the review overview; the case as intent only)
**Scope:** One new reasoning stage, the review page it feeds, a structured case form, the
atlas entered from a finding, and a CLI batch evaluation. Brownfield only. No job queue, no
greenfield rail, no second detector.
**Drives:** Making what the engine already produces legible, which is the gap between a
correct answer and a usable one.

## 1. What exists today

Honest inventory, because the plan below is mostly *surfacing* rather than building.

| Stage | State |
| --- | --- |
| `ArchitectureCase` as intent | **Built.** ~20 fields, including the three that decide verdicts: `expected_future_changes`, `non_goals`, `confirmed_facts`. Authored in the browser as YAML, immutable revisions, revise-and-review-again. |
| Repository → `RepositoryAtlas` | **Built.** Versioned, freshness-checked, never imports or executes the analysed project. |
| Detect candidates | **Built, narrow.** Deterministic complete sweep, one detector: an abstraction with exactly one implementation (§8A.2). The second detector is §8A.3, Phase 3. |
| Per candidate: candidate + case + **whole** policy corpus → one model call | **Built.** Returns `material`, `rationale`, `policy_bearings` (which policy, and how it bears), `recommended_response` when material. Policies are presented by position and never by ID. |
| Compose the review | **Built.** `BR-001…n` assigned by the application in detection order; JSON and Markdown persisted; immutable; pins case revision, atlas version and the policy set. |
| **Overview across findings** | **Missing.** This plan's only new engine work. |
| Review page | **Built, thin.** Boundaries grouped material/cleared, each with rationale, bearings with the denominator named, detection limits, plus the score bar and provenance. No overview, no atlas, one conversation thread. |
| Conversations | **Built and durable.** Append-only, stored, many per review, `GET /api/review-conversations?review_id=…` returns all. The workspace renders `[0]` and offers no way to start or switch a thread. |
| Progress | **Built.** Streamed NDJSON, `judging boundary k of n`, failures in-stream. |
| Scoring | **Built.** `boundary-review` ships answers; `make demo` / `demo-local` grade one example. |

Worth knowing before step 1: **the full flow is already walkable today** — one click on a
bundled example fills both rails, Run streams the judgement, and the review page opens. What
that walk is missing is the overview and a page that leads with it.

## 2. The target flow

```text
ArchitectureCase (intent: requirements, constraints, expected changes,
│                 non-goals, confirmed facts — authored by a person)
│        +
│   Repository ──parse AST──▶ RepositoryAtlas (versioned, deterministic)
│                                   │
└───────────────┬───────────────────┘
                ▼
        Detect FindingCandidates            deterministic · complete · no ranking
                │
                ├─ per candidate ──▶ candidate + case + WHOLE policy corpus
                │                      │  one model call
                │                      ▼
                │                    Verdict: material? · rationale ·
                │                    policy bearings (by position) · response
                ▼
        Compose ReviewedBoundary list       BR-001…n assigned by position
                │
                ├─ once ──────────▶ every boundary + the case
                │                      │  one model call
                │                      ▼
                │                    Overview: situation · themes · sequence · limits
                │                    (cites boundaries by position; no verdict field)
                ▼
        BoundaryReview  ── immutable, pins case revision + atlas version + policy set
                │
                ▼
        THE REPORT PAGE
        overview first · every boundary with its verdict, argument and policy
        substantiation · atlas neighbourhood per finding · score bar when the
        example ships answers · conversation threads, durable and plural
```

Two rules the new stage does not get to break: the application decides what to look at, the
model decides what it means, and nothing the model writes is used as a key (§12.0); and the
response schema is ordered reasoning → conclusion, so the situation and themes are filled
before the sequence that follows from them.

## 3. Contracts

### 3.1 Domain — `domain/review.py`

```python
class OverviewStatement(DomainModel):
    """One claim about the repository, and the boundaries it rests on."""
    text: str = Field(min_length=1)
    #: BR-nnn, attached by the application from returned positions. Never parsed from text.
    supporting_references: list[str] = Field(min_length=1)


class ReviewOverview(DomainModel):
    """What the whole set of verdicts amounts to. Carries no verdict of its own."""
    situation: str = Field(min_length=1)          # what this repository is being asked to do
    themes: list[OverviewStatement]               # patterns across boundaries
    recommended_sequence: list[OverviewStatement] # what to do, in order
    limits: str = Field(min_length=1)             # what this review could not see


class BoundaryReviewReport(DomainModel):
    schema_version: Literal[2] = 2                # was 1; overview is required
    ...
    overview: ReviewOverview
```

`themes` and `recommended_sequence` may be empty lists — a review of two cleared boundaries
has no theme — but no statement inside them may cite nothing.

### 3.2 Port — `ports/reasoning.py`

```python
class ReasoningTask(StrEnum):
    JUDGE_FINDING_CANDIDATE = "judge_finding_candidate"
    SUMMARISE_REVIEW = "summarise_review"         # new
    ANSWER_REVIEW_QUESTION = "answer_review_question"


def summarise_review(
    self,
    case: ArchitectureCase,
    boundaries: list[ReviewedBoundary],
) -> ReviewOverview: ...
```

The boundaries are passed already composed, so `BR-nnn` exists and the adapter can zip a
returned position back to `boundary.reference` — the same move `judge_finding_candidate`
makes for policy bearings.

### 3.3 Adapter — `adapters/models/structured.py`, `prompt_contracts.py`

Presents each boundary positionally and **without its reference**: an identifier in the input
is an identifier the model can quote back. Returns `ProposedReviewOverview`, whose statements
carry `supporting_boundaries: list[int]` (1-based). The adapter validates that every position
is in range and non-empty, zips to references, and returns the domain model. New prompt
contract at version 1.

### 3.4 Application — `application/reviews.py`

After the judgement loop and `reviewed_boundaries(...)`, call `summarise_review`, then compose
the report with the overview. New optional callback `on_summarising` so the stream can say so.
Failure propagates: nothing is persisted.

### 3.5 Web — `presentation/web/app.py`

- `ReviewSummarising` progress line (`event: "summarising"`) added to the `ReviewProgress`
  union, so `judging 6 of 6` is followed by something other than silence.
- No new routes. `make api-types` after the schema change.

### 3.6 Rendering — `application/review_rendering.py`

The Markdown report leads with the overview, each statement followed by the references it
rests on, so the exported artifact and the page say the same thing.

## 4. What the report page looks like

```text
┌────────────────────────────────────────────────────────────────────┐
│ BOUNDARY REVIEW                                                    │
│ Task scheduler boundary review                                     │
│ 6 boundaries examined · 27 policies presented to each · 4 material │
│ case rev 1 · atlas 423a…d06c2 · gemini-3.6-flash · 26 Jul 14:09    │
│ [Revise case & review again]   ← earlier · 2 of 3 · newer →         │
├────────────────────────────────────────────────────────────────────┤
│ WHAT THIS AMOUNTS TO                              ← the overview   │
│ Situation: one operator, one server, a label format fixed by a     │
│ downstream parser…                                                 │
│                                                                    │
│ Themes                                                             │
│  · Four boundaries absorb variation this case rules out   BR-001,  │
│    as a non-goal.                                         BR-003…  │
│  · Two earn their place for a change that is scheduled.   BR-005   │
│                                                                    │
│ Do this, in order                                                  │
│  1. Remove the formatter port; its only variation is        BR-001 │
│     contractually excluded.                                        │
│  2. …                                                              │
│                                                                    │
│ Limits: one detector ran — abstractions with exactly one           │
│ implementation. Duplication without ownership is not examined.     │
├────────────────────────────────────────────────────────────────────┤
│ 3/6 correct against the answers boundary-review ships  ← score bar │
├────────────────────────────────────────────────────────────────────┤
│ JUDGED MATERIAL (4)                                                │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ BR-001  ports.TaskFormatter                        MATERIAL    │ │
│ │ Implemented only by adapters.DefaultTaskFormatter · adapters.py│ │
│ │ Because: …the label format cannot vary…                        │ │
│ │ Do this: remove the port and call the formatter directly.      │ │
│ │ Policies that bear (2 of 27):                                  │ │
│ │   · Delay premature abstraction — the variation it would…      │ │
│ │   · Keep interfaces simple — …                                 │ │
│ │ Not seen by this method: tests are excluded from…              │ │
│ │ [Show BR-001 in the atlas ▾]        ← neighbourhood, in place   │ │
│ └────────────────────────────────────────────────────────────────┘ │
│ EARNING THEIR PLACE (2)                                            │
│ … same block, verdict rail reads cleared …                          │
├────────────────────────────────────────────────────────────────────┤
│ QUESTIONS   [thread: "why the clock?" ▾] [+ new thread]            │
│ … append-only history, each answer naming the boundaries it rests  │
│ on, or labelled as resting on none …                               │
└────────────────────────────────────────────────────────────────────┘
```

The verdict word is the loudest thing in each block, the policy substantiation sits under the
argument it supports with its denominator named, and the atlas opens inside the finding that
raised the question rather than as a page of its own.

## 5. The plan

Each step leaves the tool working and is committed on its own.

### Step 1 — The overview stage (engine)

Domain model, port, prompt contract, adapter stage, application composition, Markdown
rendering, schema bump, `make api-types`, `summarising` progress line. Deterministic-provider
tests for composition and for the citation validators; one live run on the local model.
Master plan revision (§5.1, §5.5, §6A, §16, §17, invariants) lands here, with ADR 0007 moving
to Accepted.

*Acceptance:* `make check` green; every review carries an overview whose citations all
resolve to boundaries of that review; a review whose synthesis fails persists nothing;
`make demo-local` prints the overview above the per-boundary table.

### Step 2 — The report page

Overview section first. Findings rewritten so the verdict, the argument, the policy
substantiation and the recommended response are unmistakable. Conversation threads: list,
switch, start a new one with a title.

*Acceptance:* browser flow extended — run a review, read the overview and its citations,
open a second thread and ask in it; `make test-browser` green.

### Step 3 — The case as a prefilled form

A structured form over the fields that decide verdicts, each labelled with the question it
answers and the reason it matters, prefilled from the selected case; the YAML editor stays as
the escape hatch; revise-and-review-again reuses the same form. On a workspace with exactly
one case, it is selected on arrival so the flow is one click from a run.

*Acceptance:* browser flow — pick a case, see its fields prefilled, change an expected future
change, run, land on a review whose overview reflects the change.

### Step 4 — The atlas from a finding

"Show BR-003 in the atlas": the existing explorer, scoped to that boundary's participants and
their neighbourhood, opened inside the finding. Completes `workspace-design` §4's
repossession.

*Acceptance:* browser flow — expand a finding's neighbourhood without leaving the page.

### Step 5 — Batch evaluation, CLI and local

`scripts/run_boundary_review.py --all` over the brownfield examples on `config/models.yaml`,
one review each, scored where answers exist, one table at the end, non-zero exit if any
scored example regresses. A `make eval-local` target.

*Acceptance:* runs to completion locally and prints per-example scores; unscored examples are
reported as unscored rather than counted.

### Step 6 — Remove the write-back fields

`current_recommendation`, `confidence`, `advisor_design_forces` from the case and its
summary/update contracts; `origin_run_id` and the `"consultation"` event type from
`CaseRevision`, with the SQL migration. Released by ADR 0007's decision that the case is
intent only.

*Acceptance:* `make check` green; no era name left in the domain.

### Later, deliberately not now

The second detector (§8A.3) — the overview gets more to synthesise once it exists, but
building it first would mean redesigning the page around it twice. Greenfield candidates
(§4.1). Policy retrieval and the embedding index remain unused on the review path and are a
separate decision.

## 6. Trade-offs accepted, and what could still change our minds

- **An overview can launder weak verdicts.** Prose reads more confident than six independent
  judgements do. Mitigations: it cites every claim, it cannot state a verdict, and the score
  bar stays directly beneath it where an example ships answers. If a live run shows the
  overview asserting more than the verdicts support, the answer is to tighten the prompt's
  field order and the citation validator, not to soften the page.
- **One more model call per review** (~a seventh more for six boundaries), and one more thing
  that can fail late in a long run.
- **Stored reviews stop opening** when the schema bumps. Accepted for a single-user local
  tool where re-running is one click; it would not be accepted once anyone's history matters.
- **Thin reviews get thin overviews.** With one detector and two cleared boundaries there may
  be no theme worth stating. Empty `themes` is valid and the page must read well with it —
  "nothing across these boundaries needed saying" is a result.
