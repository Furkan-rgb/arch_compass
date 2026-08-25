# The experience

What a person does in ArchCompass, in what order, and what each surface owes them at that
moment.

Five documents describe the interface and they do not overlap.
[The charter](charter.md) says what the product is for and which rules settle an argument
about it. [The design system](design-system.md) says what it looks like and why — the
tokens, the three typographic voices, the two structural devices.
[Frontend regions](frontend-regions.md) is the vocabulary, so a sentence like "the queue
footer overlaps the last row" means one thing. [The landing page](landing-page.md) is the
one surface with an argument to make rather than work to do.

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

### The queue and the workbench are one list

The first answer to "the queue is not a tab" was to make it the page's left column: a sticky
rail with its own scroller, beside a detail column that switched between a finding, the
delta, the report and a conversation. That fixed the queue being hidden six ways out of
seven and left the harder problem untouched, which is that **two panes are two panes**.

What it cost, measured on the example repository:

- **The rail could not be read.** A 266px column has room for a leaf name, so the rows read
  `Clock`, `ConfigLoader`, `IdGenerator`. Nothing on a row said what the finding claimed, so
  there was no way to tell from the list which of six rows mattered — and the only way to
  find out was to open all six.
- **The detail could not be scanned.** Everything the rail could not carry was 900px to the
  right, in a column that repeated the identifier and the verdict the row had just shown.
- **Every item cost two crossings of the screen.** Click left, read right, decide right,
  return left. A hundred times.
- **A phone got a second interface.** Below 1024px the rail became a bottom sheet behind a
  button, with a back bar to get out of a finding — its own navigation, its own bugs, and
  nothing in common with the arrangement people learn on a laptop.

So they are one column. Every candidate is a row that **carries its own claim as a
sentence**, which is what makes the list readable and the reason most rows never have to be
opened; a row **opens in place**, under itself, with the list still around it, so checking a
claim never moves you anywhere; and the assessment inside a row is the argument beside the
evidence rather than a repeat of the row's own heading.

`Delta`, `Report` and `Ask` stay as peers of the docket rather than modes of a column. They
are documents *about* the review — what moved, the write-up, a conversation — and none of
them is a way of working through it. Your place in the docket is page state, so reading one
and coming back leaves the same row open, the same filter set and the same scroll.

*Which* of them you are reading is not page state — it is in the URL, so
`/reviews/:id?tab=atlas` is a link that can be sent to somebody and a refresh lands back where
it was. The two are separate on purpose: which document you are reading is where you are, and
your position inside the docket is what you were doing there.

That it is a query parameter rather than a path segment is not an aesthetic choice. A segment
changes which route the URL matches, and a changed match remounts the page — which throws away
the open row, the filter and the scroll, breaking the paragraph above. Both spellings of the
segment were tried and both did it. The docket carries no parameter at all, because arriving
at a review and arriving at its docket are the same arrival, and rewriting the URL on mount to
say so would put a second entry in the reader's history for every review they open.

The one column is the same column at 390px. Nothing moves into a sheet, and there is no back
bar, because opening a row never took you anywhere to come back from.

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

### Atlas comes back as a tab, scoped to the review rather than to the repository

This reverses half of the decision above, and the reason is worth writing down rather than
quietly editing away.

What was deleted was an explorer with no relationship to the work: a search box over the
whole repository, seeded with five ANDed terms, opening on "0 matched". The objection was
never that a map is not useful. It was that *that* map was not about this review.

The tab that is back is the review's own neighbourhood. It anchors on the elements the
findings were actually made about — every participant of every finding, by the atlas node the
detector recorded and by qualified name where an older review has no node id — and asks the
atlas for what surrounds them, under a node budget that shrinks the radius as the number of
anchors grows. It opens on the **Judged** lens, so the first thing on screen is the elements a
verdict was written about and whatever reaches them, each card carrying its finding's tone and
a way into the finding. It is seeded with something, and it answers with something.

So the peer question from *What was wrong* — is this a way of working through the review? —
gets a different answer than it did for the old surface. Not because the rule changed, but
because the surface did. The docket is still where the work happens; the atlas is where a
reader goes to ask *where* the work is, and it is a document about the review in the same
sense that Delta and Report are.

Three things keep it honest, and each of them is a rule the old one broke:

- **It says what it is reading.** Every card and every connector comes from the atlas the
  review was pinned to. The header says so, and every exploration repeats it. A map that let a
  reader believe it showed the repository as it stands now would be the more dangerous kind of
  wrong.
- **An empty answer is an answer.** Asking for an element's dependants and watching the map
  not change is indistinguishable from a broken button, so every exploration and every trace
  writes back one sentence — including "nothing came back". What the reader explicitly asked
  for also survives every lens and every filter, because answering a request by not drawing
  what came back is not answering it.
- **Absent is not cleared.** Most of what is on the map was never looked at. The map draws no
  verdict on those cards at all, rather than drawing them the way it draws a cleared one.

The re-scoped Atlas inside the judgement-context drawer stays. The two are not the same
question: the drawer's is "what else touches *this candidate*", asked while deciding it; the
tab's is "what shape was this review looking at", asked before or after.

### The status ribbon is deleted

The counts it uniquely carried go where they can be acted on. *Policies retrieved* moves to
the judgement-context drawer, beside the policies. *New or changed* becomes the docket's group
heading, where it labels the rows it counts. The other three were already the docket's filter.

### The docket groups by what moved, and by where things live

When the review has a predecessor, the list is two groups: **Moved since review N** and
**Carried forward**, in that order, each with its count in its heading. Not a fourth filter —
a filter is a claim that the reader wants only one of these, and the second visit wants both
with the changed ones first.

Where every row in a group shares a package, the heading says it once — *Carried forward · 12
· in `domain.orders`* — and the rows show only the leaf. Twelve rows reading `domain.orders.`
before the name they differ by is twelve copies of one fact, printed ahead of the half that
distinguishes them. The whole name stays on the hover and in the accessible name.

The sort inside a group stays what needs a human first. Across groups, movement wins: a new
material finding outranks a material finding that has been there for four reviews and is
still there.

The first review in a lineage has no predecessor, so it has no groups. A wall of forty
candidates is still a wall; the filter and the ordering are what stand between the reader and
it, and this document does not claim to have solved a first review of a large repository.
See *Where this is still open*.

### A decision knows what it was decided against

`needsAttention` reads `decision.finding_verdict`. When it differs from the finding's current
verdict the candidate returns to the Attention filter, its row says **decided against a
different verdict**, and the decision bar leads with the discrepancy: what the team decided,
what it was decided against, what ArchCompass now says. The reader is offered the same three
dispositions to re-affirm against the current judgement.

Nothing is inferred. The old decision is not withdrawn, downgraded or annotated — it is a
record, and records do not change. What changed is that the interface now says the record was
made about something else.

### The docket is worked from the keyboard, and deciding carries you on

`↑` `↓` and `j` `k` move down the visible rows, opening each as they land on it; the moved-to
row scrolls into view. `A`, `P` and `W` take the three dispositions on whatever is open. Held
inside the docket, and refused while anything typeable has focus — with `W` bound to a single
letter there is no keystroke in a text field that is not also a decision.

**Recording a decision opens the next row that wants a person.** The earlier answer was a
named "next item" control at the foot of a finding, on the argument that moving somebody
without asking is the interface inferring they were finished. That reading does not survive
contact with the work: nothing is inferred and nothing is recorded — you asked to move by
taking a decision, and the charter's rule is about what goes in the record, not about where
the cursor is. A hundred items at one extra click each was the whole cost of the old rail
paid again.

What the rule does buy is the correction that came with it: **a row that settles under you
stays listed**. Under the Attention filter the row you just decided no longer matches, and a
row that disappears at the instant you act on it takes with it any way to check what you did
or to change your mind. The counts move immediately, because they are the truth. The row
stays, showing the decision on it, until you change the filter and ask the list a different
question.

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
happen: *Continues case revision 2 on `main` — 4 answers.* Starting clean is a
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

### The report says what it amounts to before it says how much of it there is

The document opened on counts — *Seven candidates judged: 2 material, 3 held, 2 cleared* —
and then went straight into the first verdict. That is orientation, and the charter is
explicit that orientation is read once on the way to the work. It is not an answer. It does
not say whether the two material findings are one problem in two places, whether either can
wait, or which to open first, and those are the questions somebody has when a report lands
in a pull request.

So the model writes a paragraph about the review as a whole, and it is the only place in the
product where it is asked about anything larger than a candidate. It reasons over verdicts
it has already reached: it is given the findings, their hinges, their policies and their
delta states, and it is given no evidence and no measurements, because a sentence about a
line of code is a sentence it would be inventing.

It is written once, when the review is composed, and stored on the review. Composing it when
somebody opens the report would mean two readers of one immutable review seeing two
different documents and the downloaded Markdown matching neither, which is the third
commitment given away for a convenience.

It appears twice in one sense and once in every place it is read. `report.py` writes it into
the document under a run-in label, because the document is downloaded, printed by the CLI
and attached to pull requests, and has to stand on its own. The report surface hoists the
same paragraph out and sets it the way every model-authored paragraph in this product is set
— an attribution line naming the model, then the sentences at the reading size — and renders
the document below it without that one paragraph. A page that showed both would be saying
the same three sentences twice on one screen.

A review with nothing judged has no summary, and the report opens on its counts as it did
before. That is a state, not a hole: no model was available, or there was nothing to
summarise, and a heading over a blank space reads as a component that failed.

### The clarification is a menu, and the case has no other door

The round was built to the charter's rule — *never make someone type what they could pick;
never make them pick when the truth is not on the menu* — and then almost never showed a
menu. Two things stood in the way, and both were upstream of the component.

`QuestionOutput.options` was optional, "when the honest answers are too open to enumerate".
That put the escape hatch in the wrong place: writing your own answer and skipping outright
are offered structurally, beneath every question, so a menu here is never a closed set and
the model never needed to leave room for one. Optional meant empty in practice, and empty
meant a blank box — the exact thing the rule exists to prevent. Two to four proposed answers
are now required; a question the model cannot propose two answers to is too open to be worth
a person's interruption, and it should ask a narrower one.

The second was that the round rarely ran at all. Judgement permitted a hinge and gave it no
standing, and an empty case reached the model as three empty arrays beside a full policy
corpus — so it judged on the policy and never stopped. The contract now says an empty case
in words, gives asking first-class standing, and says when *not* to ask, because a hinge
interrupts a person and one raised on something the evidence already settles is worse than
none.

**The round is a stack, and that is the docket's rule applied to questions.** It used to be
a slideshow: one question on screen, a stepper saying where you were, Previous and Next to
move, and an animation to carry the swap. All four were paying for one decision — that
answering a question should take it away — and that decision was already settled the other
way two sections up: *rows open in place, and recording a decision opens the next row that
wants a person while the row you just decided stays listed.* A clarification round is a list
of things that want a person. It is a docket.

So every question is on screen from the start. The one that wants you is open; the ones
settled are single rows carrying **the answer that was given**, so the round reads back as a
record of what you said rather than as a progress bar over questions you can no longer see;
the ones still to come are single rows carrying their question, so nothing further down is a
surprise waiting to happen. Answering or skipping opens the next row that wants a person —
and where nothing else does, the row you just settled stays open, because a row closes when
another one opens and with nothing to open nothing closes. That is not a special case for the
round of one; the round of one is simply where it shows.

Nothing travels, so there is nothing to animate but the opening itself, which is
`--animate-expand` — the same token the docket's own rows use. The mirrored slide written for
the swap was deleted with it.

**And answering it does not take it away either.** The same rule, one level up. Pressing
*Save and rejudge* used to navigate to the run's own address, so the item a person had just
spent ten minutes on left the screen along with the findings, the scroll position, the open
row and the filter — for a review they were already reading, being judged again. The round
now stays where it is and becomes the record of itself: what was asked, what was said, and
what that set going. The run's progress is on this page, and `/runs/{id}` is still a real
address for anybody who lands on it.

The acknowledgement is local and immediate, because the server's 202 has already accepted the
answers and everything after it is reconciliation. It used to be the other way round — the
press awaited a refetch of the full reviews listing, every review with all its findings and
its whole atlas, before anything on screen moved — so the honest reading of a button that
appeared to do nothing for several seconds was that it had not worked.

**The estimate belongs at the moment of commitment.** Answering starts half an hour of model
work on one press. How long that looks like taking, and that it survives a closed tab, are
facts a person needs *before* deciding to wait — not on a page they have to find afterwards.
So the run's rate and the offer to be notified sit in the round they were committed from.

**A round says which round it is.** Being asked a second time is an event, and it read as the
first time happening again. The Rounds surface is every round **this case** has been through —
each question with what was said to it, oldest first, the open one last — and it names the
ceiling out loud: a review asks at most twice, and then it is filed as it stands, and a later
review continues the same case. The case rather than the review, because that is what the
record is: a case carries its answers forward across revisions, and a second review of a
repository continues the newest case, so the rounds above the last group belong to the reviews
that asked them. Saying "this review" printed a count of three directly above a sentence
saying a review asks at most twice. That history existed on the review all along and was
rendered nowhere but the per-candidate judgement drawer, which shows only the answers bearing
on the candidate you have open.

**And what became of a round is not read off what became of the review.** A record that has
been replaced carries the status of the record the execution now stands on — which for round
one of a review cancelled at round two says `cancelled` about a round that was answered. So
that status is said once, about the review, in the banner at the top; the surfaces that talk
about a *round* say where to look instead of guessing. The one state that is knowable is the
one with no successor filed at all: stopping a review files its successor immediately, so a
waiting record that has none is one whose round was taken and is being judged.

**A record that has been replaced says so.** A revision is recorded once per round it waits
in and once more when it finishes, so one review is several records under one number. The
listing keeps the newest, which is right, and leaves the earlier ones reachable by a URL
somebody is already holding. Reading one, a person saw a review waiting on questions they had
answered an hour before, a docket of verdicts that had since moved, and a report composed
before their answers existed — every word true about the moment it was recorded, none of it
true now, and nothing on the page saying which. It says so now, at the top, with a link to
the record that replaced it.

And the case has no other door. Constraints and decisions are gone from the domain: nothing
in the product ever offered to write one and no review ever produced one, so the only way to
fill them was hand-authoring YAML — the "confirm the architecture case" step from further up
this page, wearing a different shape. What a review needs to know arrives as an answer to a
question it asked, carrying who answered and when. Which is what the charter said all along;
the record just had a second door nobody could reach and nothing could close.

## Rules for content

These decide the small questions the way the design system's token table decides colour.

**Lead with the identifier, and never stop at it.** A row, a heading or a card that names a
candidate leads with its qualified name in mono and puts the summary sentence beneath — and
the sentence is not optional. A rail that led with the identifier and had no room for
anything else obeyed half of this rule and produced a list of `Clock`, `ConfigLoader`,
`IdGenerator` that could not be read. Where every row in a group shares a namespace, the
group heading says it once and the rows show the leaf; the whole name stays on the hover and
in the accessible name, because `orders` is not an identity when three packages have one.

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
| Every row says what it claims | "carries each candidate's claim on its own row, so the list can be read" |
| Reading a document keeps your place | "keeps your place in the docket while another surface is read" |
| A phone gets the same column, not a second interface | "is the same one column on a phone as on a desk" |
| A stale decision re-enters attention | "re-raises a decision taken against a verdict that has since moved" |
| The docket moves from the keyboard | "walks the queue with the keyboard and opens what it lands on" |
| The second visit leads with what moved | "puts what moved since the last review at the top of the queue" |
| The end of the work is a state | "marks a review that is worked through, rather than showing an empty list" |
| The audit is behind what it audits | "keeps the audit behind the judgement it audits" |
| The report leads with the summary, once | "leads the report with what the review comes to, and says it once" |
| The docket has no box of its own to clip | `overflow.test.tsx` — "scrolls with the page rather than inside a box of its own" |
| You can always see which document you are on, and leave it | "keeps the surface strip on screen while a long docket is read" |
| A question is answered by picking | `tests/browser/test_workspace.py` — "answering a clarification completes the revision" |
| The round is a stack, not a slideshow | "stacks the round, and opens the next question when one is answered" |
| A settled row still says what was said | "says where each question in the round stands, and reopens one" |
| Answering keeps you where you are | "keeps the round on screen as the record of what was just answered", and `tests/browser/test_workspace.py` end to end |
| A record that has been replaced says so | "says when a snapshot has been replaced, and points at the one that replaced it" |
| A surface never says what it cannot know | "does not tell somebody who stopped a review that it was answered", and its siblings |
| A case can only be told an answer | `tests/unit/test_case_management.py` — "a case has no way to be told anything but an answer" |
| No count without a control | none; enforced by review against this document |

The browser suite carries the same claims end to end: `tests/browser/test_workspace.py`
runs a real deterministic review and asserts the three voices, the open row surviving a trip
to another surface, and the provenance reachable from the drawer rather than from a tab. It
also counts
the report's summary, which is the one claim in the product that depends on a literal being
spelled the same way in Python and in TypeScript — neither side's own tests can see the
other's copy.

## What this does not change

The domain, the API and the persistence model are untouched. Every behaviour here reads
fields that already cross the boundary — `delta`, `previous_review_id`,
`DecisionResponse.finding_verdict` — and no endpoint is added.

The design system's rules are untouched — a hue never carrying meaning alone, and one
accent that always means *look here* — though the devices that used to carry the three voices are not the
ones that carry them now. The attribution gutter and the queue spine are gone; what keeps the
machine, the model and the person apart is placement and a line naming the author, which
`review-workbench.test.tsx` holds in exactly the way it used to hold the gutter.

The clarification round's mechanics are untouched: proposed answers, writing your own, and an
explicit skip, all of which the charter settles and none of which was wrong. What changed is
only the shape it is worked in — one question at a time became the stack described above.

## Where this is still open

- **A first review of a large repository.** Grouping by movement does nothing when nothing
  has moved yet, and the charter admits that a thousand-candidate review is unanswered. The
  ordering and the filter are all a first-time reader gets. If this needs solving it is
  probably by grouping on something the machine already measured — pattern, or subtree —
  and that is a detection question as much as an interface one.
- **A bulk waiver still needs one reason for many findings.** `BulkBar` ships and calls
  `/api/decisions/bulk`, so twelve cleared candidates are no longer twelve times the same
  three clicks. What it does not solve is the reason: a waiver wants a reasoning string, and
  one that fits twelve different findings is usually not a reason. Bulk accept is the safe
  case; bulk waive is the open one.
- **The Structure tab.** Scoping the atlas search to the candidate is better than not
  scoping it, but it is still a search box. Whether a reviewer judging a coupling finding
  wants a search or wants the resolved neighbourhood drawn for them is not answered here.
