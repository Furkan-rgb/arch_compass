# The experience

What a person does in ArchCompass, in what order, and what each surface owes them at that
moment.

Four documents describe the interface and they do not overlap.
[The charter](charter.md) says what the product is for and which rules settle an argument
about it. [The design system](design-system.md) says what it looks like and why — the
tokens, the three typographic voices, the two structural devices.
[Frontend regions](frontend-regions.md) is the vocabulary, so a sentence like "the queue
footer overlaps the last row" means one thing.

This one is about *the work*. The design system asked whose voice is speaking; this asks
what the reader is trying to do and whether the screen in front of them is helping. It is
the contract for flow, content and component behaviour the way the design system is the
contract for type and colour: if a surface exists that answers none of the questions below,
that is the bug — not a missing feature.

## What a person actually does

Three visits, and they are not the same visit.

**The first review.** Somebody points ArchCompass at a repository they are responsible for
and waits several minutes. What they want when it lands is an answer to "is anything here
actually wrong", and they have no priors: no case, no policies of their own, no previous
review to compare against. Every candidate is new, so the delta says nothing. Their real
risk is drowning — a review with forty candidates and no order is a wall.

**The working visit.** They have a review open and a list to get through. This is the
visit the product exists for and it is overwhelmingly the longest: pick the next thing that
needs a human, read what the machine measured, weigh what the model concluded, decide, move
on. It is repetitive by design. The measure of the interface is how little it costs to do
that a hundred times.

**The second visit.** A review has been run again — a week later, after a merge, after
answering a clarification. Almost everything is the same as last time and they already dealt
with it. What they want is the short list of what is *different*, and to not be asked again
about the things they already settled. This is the visit that makes immutable reviews worth
the cost of keeping them.

Everything below follows from the fact that these three want different things from the same
screen, and that the second and third are the ones that repeat.

## What was wrong

Written down with the counts, because none of this was carelessness. Every one of these was
a reasonable local decision.

### The queue existed one-seventh of the time

`review-page.tsx` had seven peer surfaces — Workbench, Delta, Atlas, Evidence, Retrieval,
Report, Ask — as a tab strip across the top of the page. Six of them unmounted the queue
entirely. The charter's first interface rule is *the queue is the product*, and the product
was hidden six ways out of seven, behind a control that looked like it was switching between
views of the same thing.

It also put the queue third on the page. A reviewer arriving at `/reviews/:id` met a review
head, then a five-cell ribbon of counts, then a tab strip, and only then the list they came
to work down — about 260 vertical pixels of preamble before the work.

### Four of the seven surfaces were not the work

The charter is explicit: *every surface is either that list, something that helps you decide
an item on it, or the record of what you decided. Anything that is none of those is
competing with the work.* Applied honestly:

| Surface | The list? | Helps decide an item? | A record of a decision? |
| --- | --- | --- | --- |
| Workbench | yes | yes | yes |
| Delta | it *is* a list, of the same objects | which one to take next | no |
| Atlas | no | not as built — unscoped | no |
| Evidence | no | duplicate | no |
| Retrieval | no | duplicate, in audit form | no |
| Report | no | no | yes |
| Ask | no | yes | no |

**Evidence was a literal duplicate.** `EvidenceSurface` rendered `candidate.evidence`
grouped by candidate; `FindingDetail` rendered `finding.evidence` for the open candidate.
A comment in `surfaces.tsx` records that every producer sets `finding.evidence` to
`candidate.evidence` verbatim. The surface was the same excerpts, one click further away,
for candidates the reader had not asked about.

**Retrieval was the same duplication in audit clothing.** Every field it showed for a
candidate was already in the judgement-context drawer's Provenance tab for the candidate in
front of you. Its one real contribution — seeing every candidate's retrieval at once — is an
audit, and an audit is not a peer of the queue.

**Atlas was an explorer with no relationship to the work.** A search box over the whole
repository, seeded from the review's first five participant names and then entirely the
reader's. It answered "what else is in this codebase", which is a genuine question and not
one this page is for. The design system already flagged it as the one region with no
attribution, because exploring a structure is not one of the three jobs.

It was also broken, and being a surface nobody's work led to is why nobody noticed.
`SearchNodesQuery` **ANDs** its terms — every one has to appear in the same node's name or
path — so seeding it with five participant names asked the atlas for a single node called
both `ports.Clock` and `adapters.SystemClock`. On any real review it opened on "0 matched".

### The counts were decoration by the charter's own definition

*Not a dashboard. Counts are orientation, read once, on the way to the work. A number that
nobody acts on is decoration.* The status ribbon printed five numbers and not one of them
was a control. Two hundred pixels below it, the queue's filter printed three of the same
numbers — attention, settled, all — as buttons that *did* something. The page said the same
thing twice, and the decorative version came first and was larger.

### The queue could not be worked from the keyboard

The most repeated interaction in the product — move to the next item, open it, decide it —
was pointer-only. `Tabs` had roving arrow-key focus; the queue, which a reviewer touches a
hundred times to the tab strip's twice, had none.

Nor did anything carry a reader forward. Recording a decision left the selection where it
was, and finding the next item meant travelling back up to the rail with the mouse.

### The second visit was not served by the queue at all

`orderedFindings` sorts by verdict rank and then by the summary *alphabetically*. It does
not know what moved. On a second review with thirty unchanged candidates and two new ones,
the two new ones land wherever their sentences sort. The delta existed on another tab, where
consulting it cost the queue.

### A stale decision counted as settled

This is the one that matters most, because the domain already solved it and the interface
never read the answer.

`StandingDecision` records `finding_verdict`, `finding_model_identity`,
`finding_prompt_identity` and `finding_retrieval_identity` — *what the team decided
against*. Those four fields cross the HTTP boundary in `DecisionResponse`. In the whole
frontend they appeared only in test fixtures. Nothing read them.

So `needsAttention(finding, decision)` returned `false` for any decision at all. A team that
accepted a material finding in review 1, and saw it re-judged **held** in review 4 because
somebody answered a clarification, was never told. The row stayed settled and silent. The
charter says a decision never edits a judgement, and that "we already decided this" must
survive a rerun — it must not survive a rerun *that changed what was decided about*.

### The start page asked for the case before anything could be answered

*ArchCompass does not demand context up front. A case starts empty and fills in as reviews
ask for what they actually need. Anything a form asks for before the first finding exists is
asked of someone with no reason yet to answer it.*

Step 3 of 4 was "Confirm the architecture case", and on a first review there is no case to
confirm. Its only control was an advanced checkbox reading "Do not carry **the goal**,
constraints, decisions and clarification answers" — naming a field removed from the domain
three commits earlier. Beside it, a panel of charter copy, "What ArchCompass will not do",
sat on a form: positioning statements addressed to somebody who has already chosen to use
the product and is trying to start a job.

### The reviews page hid the thing that makes reviews worth keeping

Reviews are immutable and sequenced per branch and case — the third commitment, and the
reason the delta can exist at all. The reviews page rendered them as a flat list of
identical cards, every one titled with the repository folder name, so eight reviews of the
same branch read as eight peers with no relationship. The sequence was a line of small grey
text. Nothing on the page showed that review 4 succeeded review 3.

## The decisions

### The queue is not a tab

It is the page's left column, present at every width and in every mode, sticky, with its own
scroller. The tab strip moves down beside the detail column and stops pretending to switch
between views of the review; it switches what the *detail column* is showing, which is what
it actually did.

Three review-scope entries survive as detail modes — **Delta**, **Report**, **Ask** — and
the fourth mode is a finding, which is what the column shows by default and returns to
whenever the queue is used. Selecting a row in the queue puts the finding back, because the
queue's job is to hand you an item and a mode that ignored it would make the list ornamental.

### Evidence and Retrieval are removed; Atlas is re-scoped

Evidence is deleted. It printed the finding's own excerpts a click further away.

Retrieval moves into the judgement-context drawer, which already showed exactly these fields
for the open candidate. When no candidate is selected the drawer's Provenance tab lists
every candidate's retrieval — the audit, reachable, and no longer a peer of the work.

Atlas moves into the same drawer as **Structure**, and is *scoped to the candidate in front
of you*: seeded with one term — the leaf of that candidate's first participant — so it
answers "what else touches this" rather than "what is in this repository", and answers it
with something rather than with nothing. That is the difference between an explorer and
something that helps decide the item. Repository-wide exploration stays on the repositories
page, which is the page for a repository.

### The status ribbon is deleted

The counts it uniquely carried go where they can be acted on. *Policies retrieved* moves to
the judgement-context drawer, beside the policies. *New or changed* becomes the queue's group
heading, where it labels the rows it counts. The other three were already the queue's filter.

### The queue groups by what moved

When the review has a predecessor, the list is two groups: **Moved since review N** and
**Carried forward**, in that order, each with its count in its heading. Not a fourth filter —
a filter is a claim that the reader wants only one of these, and the second visit wants both
with the changed ones first.

The sort inside a group stays what needs a human first. Across groups, movement wins: a new
material finding outranks a material finding that has been there for four reviews and is
still there.

The first review in a lineage has no predecessor, so it has no groups. A wall of forty
candidates is still a wall; the filter and the ordering are what stand between the reader and
it, and this document does not claim to have solved a first review of a large repository.
See *Where this is still open*.

### A decision knows what it was decided against

`needsAttention` reads `decision.finding_verdict`. When it differs from the finding's current
verdict the candidate returns to the attention queue, its row says **decided against a
different verdict**, and the decision bar leads with the discrepancy: what the team decided,
what it was decided against, what ArchCompass now says. The reader is offered the same three
dispositions to re-affirm against the current judgement.

Nothing is inferred. The old decision is not withdrawn, downgraded or annotated — it is a
record, and records do not change. What changed is that the interface now says the record was
made about something else.

### The queue is worked from the keyboard

`↑` `↓` and `j` `k` move the selection through the visible rows; `Enter` opens; the moved-to
row scrolls into view. Held inside the queue's own list, so it does not fight a text field
elsewhere on the page.

At the foot of a finding, after the decision, is **the next item that needs you**, named. Not
an auto-advance: deciding something and being moved somewhere else without asking is the
interface inferring that you were finished, and the charter forbids exactly that. It is an
explicit control that says where it goes.

### The review head is one line

The `h1` was "Architecture review of arch_compass" at 30px — the largest type on the page
spent on the fact the reader is least in doubt about. It becomes the review's identity in the
measured voice, which is what identifies it and what a reader scanning a browser history is
looking for:

```
REVIEW 4 · CASE REVISION 2 · STARTED 3 DAYS AGO
payments · main · a4f5182c1e                    [ completed ]  [ Run a new review ]
/work/payments
```

### Nothing needing you is a state, not an empty list

When attention reaches zero the queue does not print "Nothing here". It says the review is
worked through, gives the count of what was decided and by which dispositions, and offers the
two things a person actually does next: read the report, or run the next review. That is the
one moment in the product worth marking, and it was an `EmptyState` with a shrug.

### The hinge reaches the question

A finding whose verdict is **held** says what it is waiting on. When the review is awaiting
answers and an open question affects this candidate, the hinge block links to it, because
"waiting on a person" followed by no way to be that person is a dead end. When there is no
open question — the round was concluded with the uncertainty preserved — it says that
instead.

### The start page asks two things

**1 · Which repository. 2 · How much of it to read.** That is the whole form.

The case is stated rather than confirmed, in the run footer, as a sentence about what will
happen: *Continues case revision 2 on `main` — 3 constraints, 4 answers.* Starting clean is a
link inside that sentence, not a numbered step with an advanced disclosure. On a first review
the sentence says a new case will be opened, which is a fact, not a question.

"What ArchCompass will not do" is removed. It is charter copy and the landing page already
carries it; on a form it is a positioning statement addressed to someone who has already
decided.

### The reviews page is a list of lineages

Reviews group by repository, branch and case — the three things they are sequenced under.
Each lineage is one block headed by the repository and branch, carrying its newest review's
state, with its revisions beneath it in sequence, newest first, and a run in flight at the
top of its own lineage rather than in a separate list above everything.

## Rules for content

These decide the small questions the way the design system's token table decides colour.

**Lead with the identifier.** A row, a heading or a card that names a candidate leads with
its qualified name in mono and puts the summary sentence beneath. This already held in the
queue and the delta; it did not hold in the Evidence or Retrieval surfaces, both of which
titled a panel with a sentence.

**A count is a control or it is not on screen.** If a number cannot be clicked, filtered by,
or acted on, it belongs in a sentence next to the thing it describes, not in a cell of its
own.

**Say what a control does, in the words of the result.** "Accept and act on it" produces a
decision that reads "Accepted". A button never names the mechanism (`Save and rejudge` is
fine: rejudging is what happens) and never names the widget.

**Never navigate away from unsaved input.** The clarification round is a form with answers in
it. Nothing in it links anywhere that would unmount it — the candidates a question affects
are named, in mono, and not made into links.

**An explicit unknown outranks an implied one.** "nobody yet", "not indexed", "explicitly
skipped" — never a blank, which reads as a rendering fault.

## What enforces this

Every rule below is a test in `frontend/src/features/review/review-workbench.test.tsx`,
except the last, which is not the kind of thing a test can hold.

| Rule | The test that fails |
| --- | --- |
| The queue survives every detail mode | "keeps the queue on screen while another surface is read" |
| A stale decision re-enters attention | "re-raises a decision taken against a verdict that has since moved" |
| The queue moves from the keyboard | "walks the queue with the keyboard and opens what it lands on" |
| The second visit leads with what moved | "puts what moved since the last review at the top of the queue" |
| The end of the work is a state | "marks a review that is worked through, rather than showing an empty list" |
| The audit is behind what it audits | "keeps the audit behind the judgement it audits" |
| No count without a control | none; enforced by review against this document |

The browser suite carries the same claims end to end: `tests/browser/test_workspace.py`
runs a real deterministic review and asserts the three voices, the queue surviving a mode
change, and the provenance reachable from the drawer rather than from a tab.

## What this does not change

The domain, the API and the persistence model are untouched. Every behaviour here reads
fields that already cross the boundary — `delta`, `previous_review_id`,
`DecisionResponse.finding_verdict` — and no endpoint is added.

The design system is untouched. Three voices, no accent, verdict chroma only, the attribution
gutter and the queue spine all survive exactly as specified; this document changes what is on
screen and in what order, not what it is made of.

The clarification round's mechanics are untouched: proposed answers, writing your own, and an
explicit skip, all of which the charter settles and none of which was wrong.

## Where this is still open

- **A first review of a large repository.** Grouping by movement does nothing when nothing
  has moved yet, and the charter admits that a thousand-candidate review is unanswered. The
  ordering and the filter are all a first-time reader gets. If this needs solving it is
  probably by grouping on something the machine already measured — pattern, or subtree —
  and that is a detection question as much as an interface one.
- **Bulk decisions.** `/api/decisions/bulk` and `decide_many` exist in the workspace and have
  never been called by the interface. Twelve cleared candidates decided one at a time is
  twelve times the same three clicks. What stopped this landing here is that a bulk waiver
  needs one reasoning string for twelve different candidates, and a reason that fits twelve
  findings is usually not a reason.
- **Decision history.** `api.decisionHistory` is written, typed, and called from nowhere.
  Now that a stale decision is visible, the natural next question is "what did we decide the
  last four times", and there is no surface for it.
- **The Structure tab.** Scoping the atlas search to the candidate is better than not
  scoping it, but it is still a search box. Whether a reviewer judging a coupling finding
  wants a search or wants the resolved neighbourhood drawn for them is not answered here.
