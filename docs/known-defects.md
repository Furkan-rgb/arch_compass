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
judgement, the sign does not.

jsdom caught the move as a document-order failure (`finding-detail.test.tsx`, *"puts the rail
after the argument"*), so the mechanism was never unguarded; the test named here as what holds
the shape simply did not check it. It now asserts that **Answer it** is drawn below the bottom
of the argument before it asserts anything about the order, which is the stacking this entry
prices.

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

## OPEN — the block cap's guarantee holds on nine strings of 375, and it says so now

`sentences()` in `ui/prose.tsx` cuts the model's paragraph at its own sentence boundaries, and
`pack` promises that an argument long enough to reach the cap never opens on its tallest block.
That promise is real and it is **conditional**, and for three passes the condition was nowhere:
`pack` runs only when a string holds *more* than `MOST_PARTS` sentences. Nine of the 375 recorded
judgements do. On the other 366 every boundary is cut, the blocks are the model's own sentences,
and no ceiling applies to any of them.

**Applying the ceiling regardless is a no-op, which is why this is written down rather than
fixed.** At `count === mostParts` the packing table has exactly one feasible partition — one
sentence to a block — and the ceiling's own escape (`through > 1`) exempts the single-sentence
first block that partition makes. Forcing `pack` to run on every string and diffing the parts
changes **0 of the 375**. The only rule that could shorten the opening block of a two-sentence
string would cut inside a sentence, and every part `sentences()` returns is a raw slice of what
the model wrote — the one thing this surface may not do is edit a judgement.

**What is left, measured rather than estimated** — and measured under Onest, at the 617.12px
that `58ch` resolved to in that face. IBM Plex Sans brings the same declaration in to 556.80px,
so every line-box count in this section is a lower bound on what the page draws today and the
sweep wants re-running; see the entry at the end of this file. All 375 strings rendered through
the real `ModelProse` in a headless Chromium against the built stylesheet, with both sans weights
and IBM Plex Mono asserted through `document.fonts.check` before anything is read; a Range per character of each block's rendered text, clustered on the vertical centre of
each rect at a 0.6px tolerance, one cluster to a line. That is 3,248 line boxes over 1,166
blocks. Of those:

- **Two strings open on a seven-line block**, both under the cap: a 673-character judgement in
  two sentences that draws 7/2, and a 1,235-character one in six that draws 7/3/3/4/2/1. The
  first is pinned as `UNDER_CAP_WALL` in `ui/prose.test-corpus.ts`.
- **Four of the 1,166 blocks are a single sentence of seven lines or more.** The tallest block in
  the corpus is a **1,132-character sentence at seventeen line boxes**, sitting second in a
  four-sentence string that draws 3/17/3/2 — not an opening block, not over the cap, and out of
  reach of any ceiling on an opening block.
- Over the cap, all nine strings open on **three** lines and none opens on its tallest block,
  which is the guarantee doing its work.

**It is worse in a phone's column, which is where it should be judged.** The same sweep at
`PHONE_COLUMN_PX` draws the 673-character judgement as **17/4** and the four-sentence one as
**7/32/5/4**. A 32-line block is a wall by any reading. What it is not is a *packing* failure:
that block is one sentence of 1,132 characters, and the string holds four sentences, so nothing
`pack` could be asked to do would touch it.

**Why that is still not the defect the cap was built for.** The complaint was a 2,139-character
nineteen-sentence judgement drawn as one block — **28** line boxes at the 617.12px measure and
**54** in the phone's column. Cut, it opens on **3** and **5**. The difference between "the model
wrote one very long sentence" and "the product drew nineteen sentences as one paragraph" is the
whole of what the cut bought: the first is the model's prose and the second was ours. Closing the
remainder would mean cutting inside a sentence, which costs the guarantee that what is on screen
is what the model wrote — and that guarantee is worth more than seventeen lines.

`ui/prose.test.tsx` fails if the 366 stop being cut at every boundary, or if that worst recorded
string stops being one sentence in its opening block — which is the fact that makes the hole
unclosable rather than unclosed.

## PARTLY FIXED — `max-w-[46ch]` is written four times on the finding surface and means four widths

`features/review/finding-detail.tsx` declares `max-w-[46ch]` on four blocks. A `ch` is the
advance of the digit zero in the element's **own** used font, so each one resolves against the
type that block declares:

| block | type | `46ch` resolves to |
| --- | --- | --- |
| `Footnote` | `text-[12px]` | 331.20px |
| the "How it was detected" rationale | `text-[12.5px]` | 345.00px |
| the policy list's empty state | `text-[13px]` | 358.80px |
| the question's answer | `text-[14px]` | 386.40px |

55.20px between the narrowest and the widest — and 61.18px under Onest, whose zero also followed
*weight* and put the same `46ch` at the same 13px on two different widths. IBM Plex Sans ships
four static cuts that advance the zero identically, so size is the whole of what is left. The
defect is smaller and unchanged in kind. This is the same fault `ui/markdown.tsx` was
repaired for in the same pass — one `46ch` on seven renderers that meant five widths — and it
went unseen here because every guard on this surface reads the model's argument and the lede,
which are the two blocks somebody had already suspected.

**The fifth is fixed.** It was `<ul className="grid max-w-[46ch] gap-2">` on the policy list,
and it was the worst of the five rather than one more of them: a `ch` on a block that declares
no font size resolves against whatever it inherited, which here is the root's 16px, so it drew
a width resolved against whatever it inherited, which here is the root's 16px, against a note
inside it set at `text-[14px]`. It also capped the wrong box — the card spends 30px on `px-3.5`
and two hairlines, so the note read 30px narrower than the number written on the list. The cap is
now the grid track — `grid-cols-[repeat(auto-fill,minmax(0,24.3rem))]` — rather than a `max-w` on
the `ul`, so it sits on the card it was always a property of and the fold lays two cards across
the 1,126px it has instead of spending one column and two rows. The derivation did not move: the
note's own `46ch` at the 13px it is now set in, 358.80px, plus the 30px the card costs, which is
`24.3rem` exactly.

**`46ch` is 46 advances of the zero, not 46 characters, and this section said characters until
now.** The two are well apart: 358.80px is `46 x 13 x 0.600`, the zero's advance, and a character
of body text on a full line costs less than a zero does. **The character figures this section
carried are Onest's and have been removed rather than converted** — 60.58 a line at the note's
measure, 65.47 at the width and size it had before, both a `Range`-per-character sweep over all
514 recorded notes. They were real measurements of a face this product no longer downloads, and a
ratio is not a measurement. The re-sweep is the last entry in this file.

**How the figures were produced.** `46 x size x advance`, where the advance is IBM Plex Sans's
zero: 0.600em, read off the `hmtx` table of each of the four shipped cuts. All four agree, so
this set differs by size alone; under Onest's single variable file it did not, which is why the
column above used to have to say which weight each block declared. Nothing above is typed in by
hand — "resolves every `46ch` this surface declares, and none of them from an ancestor" in
`features/review/finding-detail.test.tsx` reads the class lists out of the component's own source
and computes them. It asserts a property rather than a count, so repairing one of these four
passes and introducing a fifth *width* fails.

**Why the remaining four are recorded rather than fixed.** Closing it means deciding which edge
these four blocks should share, and whether the answer is one shared `rem` (which is what
`ui/markdown.tsx` chose) or four deliberate widths said in a unit that does not follow the type.
That is a decision about the surface, not about a number. What the repaired fifth settles is
narrower and is not that decision: a `ch` that cannot be resolved from the class list stating it
is wrong whatever the surface decides, because no reader of that line can tell what it draws.

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

## OPEN — a thinking *level* pinned on Ollama fails before the request is built

The mirror of the fault `openrouter._effort` fixed. `ThinkingMode` is one type over two
provider shapes — a switch and a four-word dial — and each adapter now owes the shape it does
not have. OpenRouter's branch owes the switch, and maps it onto the ends of the dial. Ollama's
branch owes the dial, and does not: `build_chat_model` passes `config.thinking` straight into
`ChatOllama(reasoning=…)`, which reaches `ollama.ChatRequest.think`, typed
`Optional[Union[bool, Literal['low', 'medium', 'high']]]`.

Measured on 2026-08-27 through a mock transport, four levels against `qwen3.8:27b`: `low`,
`medium` and `high` go across as `think='low'`, `think='medium'`, `think='high'`. `minimal`
raises `pydantic.ValidationError: 2 validation errors for ChatRequest` inside the ollama
client, before any request is built. So `--thinking minimal --provider ollama` cannot run at
all, and the other three run only by the coincidence that both vocabularies spell three of
their words the same way.

Not fixed here because the mapping is a product decision with nothing written down to
implement. `minimal` on a switch is either `False` — which reads the floor as off, the
opposite of the approximation OpenRouter makes — or `low`, which asks a model to think when
the setting asked it not to. The OpenRouter mapping had a specification already:
`ReasoningModelConfig.thinking` and `_thinking_mode` both stated it. This one has none.

Bounded rather than dangerous: it is unreachable from the chooser, which offers each provider
only the shape it has (`probe_ollama` reports `(True, False)` or `(None,)`; OpenRouter's
`_judgeable` reports `(None, *THINKING_LEVELS)`), so only a `--thinking` pin reaches it — and
it fails at model construction, loudly, before a token is spent. `test_provider_conformance.py`
covers the three states `ReasoningModelConfig` specifies and deliberately does not pin this
one, because a test of the current behaviour here would be a test that the defect is present.

## OPEN — every corpus sweep in the tree is Onest's, and the product is set in IBM Plex Sans

The face changed in the v2 design pass. A `ch` is the advance of the used font's zero, and that
number moved from Onest's `0.665em` (narrowing to `0.6618em` at weight 600, because it was one
variable file) to IBM Plex Sans's `0.600em` at all four static cuts it ships. Everything that is
*arithmetic* moved with it: `ui/font.test-metrics.ts` holds the advance, read off the `hmtx` of
`plex-sans-{400,500,600,700}.woff2`, and every `ch` figure and `rem` cap in the tree was
recomputed against it — `26.75rem` to `24.15rem` on the Markdown measure, `38.5rem` to `34.8rem`
on the finding lede, `26.75rem` to `24.3rem` on the policy card track.

**What did not move is everything a browser had to measure**, because it needs the built bundle
served over HTTP, a headless Chromium waiting on `document.fonts.check`, and a read-only copy of
`.archcompass/workspace.sqlite3` — none of which a vitest run has. Outstanding, and marked as
Onest's at every site:

| figure | where it lives | what it is |
| --- | --- | --- |
| **541.7px** widest unbreakable qualified name | `ui/prose.test-corpus.ts` | the **floor** the argument's measure is chosen against |
| **75.7** characters on a full line of a judgement | `features/review/finding-detail.tsx`, `ui/prose.tsx` | the return-sweep **ceiling** on the same measure |
| **59** characters on a full line of a footnote | `features/review/finding-detail.tsx` | the pair that argues why a footnote's measure is the shorter |
| **60.58** characters on a full line of a policy note | `features/review/finding-detail.tsx` | removed from `docs/known-defects.md` rather than converted |
| the nine `ch` rectangles | `ui/font.test-metrics.test.ts` | the *rule* — snap down to 1/64px — is Chromium's and carries; the nine readings are not |
| 3,248 line boxes / the packing counts | `ui/prose.tsx`, this file | all read at the 617.12px `58ch` used to resolve to |

**Do the floor first, because it is the one that could already be wrong.** `58ch` cleared the
541.7px floor by 75px under Onest and clears it by 15px under Plex Sans, and the token being
measured is set in the new face too, so both ends of that subtraction have moved.
`features/review/finding-detail.test.tsx` asserts `measurePx >= WIDEST_TOKEN_PX` and it passes —
on one face's measure against the other face's floor. If the floor comes back above 556.80px, the
argument's measure has to widen, and the ceiling above it is what says by how much.

The method for all of them is written out where each lives and in *Measure* in
`docs/design-system.md`; nothing about it is face-specific.

## OPEN — the evidence tier is one row in the scale and about a hundred and twenty sizes in the tree

`docs/design-system.md` gives mono two rows: **12.5px at weight 500** for evidence — provenance,
identities, paths, namespaces, fingerprints — and 15–17px for the review head. `ui/meta.tsx`'s
`Mono` component was moved onto the first of those in the v2 pass, which is the right half of the
change and is not the whole of it.

**44 call sites write `text-[11px]` back onto a `<Mono>`.** Until the default moved, that class
restated it; now it is an override pinning the size the scale moved off, so the evidence tier
renders at two sizes across the product with nothing to announce it — it compiles, the class
exists, and no test can tell an override from a restatement. They are concentrated in
`features/atlas/detail.tsx` (8), `atlas/controls.tsx` (7), `landing/landing-page.tsx` (6),
`start/repository-picker.tsx` (5) and `policies/policies-page.tsx` (4), with ten more spread over
eight files. A further ten `<Mono>` call sites pin 12px, 13px or 10.5px, and roughly 69
hand-rolled `font-mono` spans set eleven different sizes between 10px and 18px.

**It is not a sweep, and that is why it is written down rather than done.** Two different things
are wearing one face:

* **Evidence** — a path, a hash, a run id, a qualified name — belongs at 12.5/500 and the
  override should simply go.
* **A label that happens to be in mono** — an uppercase eyebrow at 11px with `tracking-[0.08em]`,
  of which the block-label sweep left about twenty — is on the *label* row, not the evidence one,
  and 12.5px would break it. `docs/design-system.md`'s rule that mono means the machine quoting
  itself arguably says a word like "Lens" should not be in mono at all, which makes those a
  design question rather than a size.

So each site needs reading, and the answer is sometimes "delete the override", sometimes "this is
a `Label`", and sometimes "this should not be mono". `ui/design-system.test.ts` carries the
matching guard for the label half — *"hunts for the recipe `Label` actually draws"* is live and
keeps the pattern calibrated, while the `.todo` beside it that would fail on the 30 hand-rolled
copies stays off until they are decided rather than replaced.

## OPEN — `scattered_concept` cannot tell a proper noun from a category word

The detector asks whether a module's own name has spread beyond the package that owns it.
`_names_things_after_itself` is the guard that decides whether the name is a *thing* at all:
it requires the word to lead an identifier the module declares, on the grammar that a proper
noun modifies — `QwenSpeechProvider` is a speech provider that is Qwen's.

`BaseMessage` leads with `base`, and so does every other `Base*` class in Python. The guard
passes, `base` is treated as a concept, and the repository is then full of the word for
reasons that have nothing to do with the module. On `langchain_core` (180 modules) this
reported `messages.base` named in 97 modules and `tracers.base` in 103.

**Two guards now catch most of it.** A name several modules answer to owns nothing
(`langchain_core` has thirteen `base.py` files), which removes `base`, `fake`, `image` and
`string` — 8 of the 15. Type parameters no longer count as constants, which is a different
detector but the same class of error.

**Five remain, and no test in the parse separates them.** `agents`, `transform`,
`generation`, `configurable` and `router` are category words owned by exactly one module.
Four candidate rules were measured against the corpus and the five bundled examples, whose
`qwen`, `ollama` and `northwind` are the shapes this detector exists to find:

| rule | result |
| --- | --- |
| the concept must be reached by the modules naming it | deletes every example's true positive; `boundary-review` has 6 structural edges and 0 references |
| the concept must not name a callable anywhere | catches `transform` only, and wrongly suppresses `deterministic` here |
| the concept must appear in few distinct identifiers | does not separate: `qwen` is in 3 or 4, `router` in 2 |
| an absolute ceiling on naming modules | does not separate: true positives are 2–5, false positives run 1–110 |

So this is left as it is, on the grounds the detector already states in
`_SCATTERED_CONCEPT_LIMITS`: a mention is not evidence of a dependency, the candidate says so,
and the judgement is the stage that can see the case. The residue is about five candidates
per 180-module repository, and a candidate is about 15,000 input tokens.

`tests/unit/test_detector_probes.py::test_a_module_named_for_a_category_word_is_not_a_scattered_concept`
is the reproduction, marked `xfail(strict=True)` so that a rule which does work turns the
suite red rather than passing unnoticed.
