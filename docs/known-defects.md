# Known defects

Faults that are understood but not yet fixed, written down so the next person does not have
to find them again. Each one names the evidence it rests on and carries a status:

- **OPEN** — reproduced, still present in the code on this branch.
- **PARTLY FIXED** — the sharp edge is gone, something named below is not.

A fault that is fully fixed leaves this file, and so does one that turns out not to exist.
Everything here was re-verified against the code on 2026-08-24, claim by claim. Two entries left on 2026-08-25 when the Google Batch subsystem was deleted: the positional response join went with it, and the concurrency knob it was the only reader of went with that.

An entry may also be **wrong about its own size**, which is what happened to the phone entry
below on 2026-08-27: the fault was real and the number describing it had been taken from a
screen the product cannot produce. That is not grounds to delete an entry — the layout it
describes still exists — but the measurement and the population it was taken over now have to
be written down beside it, because a repair was very nearly made on the strength of the wrong
one.

## OPEN — the one-review-one-sequence rule has no schema behind it

Migration `003_one_revision_per_review.sql` rebuilt `core_review_snapshots` without the old
`UNIQUE(repository_id, branch_id, sequence)` and put nothing in its place. The table's only
constraint is `review_id PRIMARY KEY`, and `SQLiteCoreReviewRepository.record` defeats even
that with `ON CONFLICT(review_id) DO NOTHING` followed by a read of whatever row is there.

Review ids are `stable_id` over branch, **atlas**, case, revision, round and status. The
atlas component is `AtlasVersion.version_id`, a fresh `new_id("atlas")` uuid minted by every
analysis and never derived from content — so two reviews of an unchanged repository do *not*
compose the same id, and the collision this entry was first written about is not reachable by
that route. What remains is that nothing in the schema says it could not happen: if two
reviews ever do compose one id, `ON CONFLICT(review_id) DO NOTHING` followed by a read of
whatever row is there means the second silently receives the first one's findings, and
`executions.bind` then writes a `current_review_id` another row already holds. That surfaces
as a `PersistenceError` wrapping `UNIQUE constraint failed: review_executions.current_review_id`,
not as an uncaught `IntegrityError` — the database layer wraps every `sqlite3.Error` — but it
is still unguarded and still lands mid-review.

Nothing anywhere checks that a review's `case.revision` exists in `core_case_snapshots`.

## OPEN — `next_revision()` reserves nothing

Minutes pass between `reviser.open` and `seal_case`. Two reviews of one case inside that
window both take the same number, and the loser dies with a genuine `CaseRevisionConflictError`
after a full round of judging has already been paid for. Reserve the row at `open`, or make
`seal` retry with a fresh number.

`ArchitectureCaseService.rescope` (`workflow/cases.py`) takes `latest + 1` through
`ArchitectureCase.revise()` — the same unreserved number `open` took — so re-scoping during a
live review makes `seal_case` die the same way, with a wider window.

## PARTLY FIXED — a round that could not be put into words is not distinguishable on screen

`generate_questions_node` catches every exception and returns no questions; so does the
per-finding loop inside `LangChainQuestionGenerator.generate`. Degrading is right — every
candidate has already been judged by then, and letting it propagate throws that away — but
"the review settled everything" and "the review has uncertainty it could not phrase" both
leave with no questions and both seal the case.

Half fixed: the two are now distinguishable **in the log**, at ERROR, naming how many held
findings went unasked. Nothing says so on a surface a reader sees, and a review that quietly
stopped short still reads as a review that finished.

## OPEN — a failed or cancelled execution reads as "already done"

`_resume_command` returns `None` for any execution that is not `awaiting_answers`, and
`resume_background` turns that into `202` with the existing run state. For a `failed` or
`cancelled` execution that is a 202 describing a run that will never do anything: the Answer
button can be pressed for ever, and only a client that reads `status` off the run body can
tell. A submission against a superseded *round* is now refused properly
(`ReviewSupersededError`, 409); a submission against a dead *run* is not.

## OPEN — indexing still happens inside the click, and the repository is parsed twice

`POST /api/repositories/start` calls `repository_service.index(...)` before it answers, so the
longest wait in the product has no stage, no progress and no cancel. `start-page.tsx` labels
the two phases honestly as a stopgap.

It cannot simply move into the graph: `review_executions` has `repository_id`, `branch_id` and
`case_id` all `NOT NULL`, the row is written before the thread starts because the 202 response
describes it immediately, both ids come out of indexing, and the case is chosen from
`version.branch_id`. Moving it means nullable execution columns, a migration, case creation
ahead of `load_context` — whose whole job is to load a case by id — and a run page rendering
with no repository name or sequence for exactly the interval the change exists to make visible.

There is a better version of it next door. **The repository is parsed twice per review today**:
`/start` builds and persists an atlas, and then the graph's `analyze_repository` node parses
the same root under the same scope again and keeps the result only in graph state. Resolve the
lineage from git alone — `resolve_repository_lineage` needs only the root commit and the
canonical root, and `resolve_branch_lineage` needs that lineage plus a branch name, which
`GitCommandLineClient.describe` already reads — and move the *atlas build* into the graph as a new first node. All three
ids stay available at `_begin`, so the execution row, the run listing, the sequence and the run
page are untouched; no migration is needed; parsing becomes the run's first visible,
cancellable stage; and a whole parse is removed rather than relocated.

## OPEN — nothing bounds a review's peak checkpoint size

Checkpoints are released the moment a review reaches an end and the space is handed back, so
the file no longer grows without bound. What is not bounded is the *peak*: LangGraph writes the
whole `ReviewState` at every superstep, and that state carries the atlas, the policy corpus and
every retrieved policy set. One review of a six-file example repository reaches about 86 MB
mid-flight before it is released. A repository of real size scales that by its atlas.

The peak is lower than when this was written and the entry's number predates the change: a
`Send` payload now carries three keys instead of the whole state, which took one round of six
candidates from 21 MB of `__pregel_tasks` to 1.3 MB (`workflow/graph.py:199`). That bounds the
fan-out, not the state each superstep writes, which is what this entry is about.

## PARTLY FIXED — on a phone, a held finding's way out is reached after the whole argument

Below `lg` the Judged band collapses to one column, and the rail comes after the argument in
the DOM — which is deliberate and is what makes the stacked reading order right. The cost is
that the **Answer it** control is reached by scrolling past the model's paragraph.

**The number this entry carried was wrong by a factor of about two and a half, and it was wrong
because it was taken from a screen nobody can be shown.** It said "roughly 1,500px", reasoning
from the longest recorded reasoning: 2,139 characters, 57 line boxes in the 324px column a 390px
viewport gives this block. Put on a held row in the live app that argument really does land the
control 1,688px down. But it belongs to a *material* finding, and a material finding has no
hinge and therefore no control here at all. `FindingOutput.the_verdict_carries_what_it_is_allowed_to`
in `reasoning/adapters/langchain.py` refuses a hinge on any verdict but `held`;
`finding-detail.tsx` draws nothing without one; and questions are generated per hinge rather
than per verdict, so the `waitingOn` gate does not widen the population either. Of the 375
recorded judgements in the workspace, all 69 held ones carry a hinge and not one of the 306
cleared and material ones does.

**Measured over the population that exists.** The held arguments run 156 to 971 characters.
Swept over all 69 at 390x844 in the real app, each with its own recorded hinge and its blocks
cut by the real `sentences()`, **Answer it** lands 275px to 956px below the top of the argument
— median 624px, five of the 69 past the 844px viewport, eight past the 796px the sticky topbar
leaves, none past 1,000px. The worst pairing the population admits at all, the longest held
argument against the longest recorded hinge and a pairing that has never occurred, is 1,025px.
The control itself sits 4px below the question it answers.

**And it regressed, by 27px.** Two changes landed on this band and they pull in opposite
directions. `sentences()` cutting the argument into blocks adds 8px of gap per cut: +84.8px of
argument height on the longest held string, +119.2px on the longest string of any verdict.
Moving the verdict's lede out of the rail and above the grid gives 58px back. Measured on the
longest held argument by reversing each change in the live DOM: 929.5px before, 956.3px today.

On the 2,139-character material argument the same two shapes read 1,626.6px and 1,687.8px. The
1,688 is exact — it is what a one-line hinge under 57 line boxes of argument comes to — but it
is the unreachable case, and the "roughly 1,530px before" it was being compared against does not
reproduce against this markup at all: the shape this pass replaced measures 1,626.6px there.
Whoever writes the next number should say which of the two populations it is over.

**What is not wrong is the direction of the complaint, and what is wrong is which control it
names.** Measured below the *end* of the argument on the same sweep: **Answer it** at 144–303px,
**Judgement context** at 884–1,043px, the decision bar at 1,878–2,037px. The last two are on
every verdict, so the control a phone buries in an open row is the decision, not the way out of
a held one — **Answer it** is the first control a phone reaches. `tests/browser/test_mobile.py`
measures that ordering and the 4px.

**That was not enough to hold the shape this entry describes, and the sentence here claimed it
was.** The three distances are signed, and an ordering is a relative claim: move the rail above
`<ModelProse>` in `finding-detail.tsx`, rebuild the bundle, and the three read **−202.17px**,
**+631.38px** and **+1,625.55px** — still ascending, so the test passed with the way out of a
held finding drawn *above* the argument it is a margin note on, which is this entry's layout
running backwards. Only the first term moves: the other two controls are drawn below the grid
the rail and the argument share, so hoisting the rail inside that grid cannot lift them, and an
ordering over the three can never notice it. Measured on the first held row of the browser
suite's own review at 390x844, where the argument is 79.17px tall; the distance scales with the
judgement, the sign does not. jsdom caught the move as a document-order failure (`finding-detail.test.tsx`, *"puts
the rail after the argument"*), so the mechanism was never unguarded; the test named here as
what holds the shape simply did not check it. It now asserts that **Answer it** is drawn below
the bottom of the argument before it asserts anything about the order, which is the stacking
this entry prices.

Three repairs were considered when the number was thought to be 1,500px, and none is taken now
that it is 624px.

- An `order` class puts the paint order and the tab order in disagreement, which costs exactly
  the readers who can least afford to scroll. `finding-detail.test.tsx` asserts that no element
  in the band carries one.
- Moving the hinge group out of the rail below `lg` buys the argument's own height — a median of
  412px — and costs four things: the reader is asked before being told why; it displaces the
  lede and the opening block that `pack`'s share ceiling exists to guarantee; a held row and a
  cleared row stop being the same shape on a phone; and crossing 1024px unmounts the group, so
  focus on the control is lost mid-resize. It also leaves the decision bar where it is, which is
  the larger number.
- A second control on the phone is a second affordance for one action, which
  `review-workbench.test.tsx` already holds the line against.

What is left open is the scroll itself, and it is priced rather than fixed: a reader on a phone
still passes a median 624px of argument to reach the way out, and the argument is what the row
was opened for. This is not the only way in either — while a review is held the clarification
round is the **first item on the docket** and carries the page's one primary action, which a
phone reader reaches without scrolling at all.

## PARTLY FIXED — `Label` still has twenty-two hand-rolled copies

The drift is fixed — the five different tracking values are gone — but twenty-two
mono-variant copies of the recipe remain in `features/atlas/**`, `components/ui/select.tsx`,
`features/landing/specimen.tsx`, `ui/brand.tsx`, `features/landing/exhibit.tsx` and
`features/review/atlas-surface.tsx`. `ui/design-system.test.ts` carries this as an `it.todo`
so it stays visible — though that test's own comment is staler than this entry: it says
"twenty-one times across fourteen files" and names ten files that now carry none.

## OPEN — dead surface that has not been removed yet

Route-plus-generated-types with no live caller, verified by grep over `frontend/src`,
`tests/`, `docs/` and the CLI. The last streaming endpoint has been removed; these remain,
because unlike that one they are plausible REST surface somebody may have meant to keep:

- `POST /api/cases/import-yaml`, `POST /api/cases`, `GET /api/cases/{case_id}`
- `GET /api/branches`, `GET /api/policies/{policy_id}`
- `GET /api/review-conversations/{id}` (and `reasoning/conversation.py:show` behind it)

The duplicated helpers, the duplicated ignored-directory list and the two protocols sharing
the name `RepositoryAnalyzer` have all been reduced to one definition each, and
`safe_workspace_output_path` has gone — see the symlink entry below for the one check that
left with it.
