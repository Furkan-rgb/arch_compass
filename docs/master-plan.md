# ArchCompass Master Plan

**Status:** Living architecture document
**Authority:** Product direction and architectural ground truth
**Project:** ArchCompass
**Repository:** `Furkan-rgb/archcompass`

## 1. Purpose of This Document

This document records the long-term product vision, architectural principles, central
domain concepts and planned development sequence for ArchCompass.

It is the primary reference for developers and coding agents working on the project.
Before proposing or implementing substantial changes, contributors should read this
document and verify that the change supports the intended product rather than only
improving an isolated implementation detail.

This document describes **what ArchCompass is meant to become and which architectural
boundaries must remain stable**. More detailed documents describe how individual
subsystems currently work.

When documentation conflicts:

1. This master plan governs product direction and core architectural boundaries.
2. Accepted ADRs govern deliberate exceptions and later decisions.
3. Subsystem documentation governs implementation details.
4. Existing code does not automatically override documented architectural intent.

Changes to this document should be explicit and reviewed as architectural decisions.

> **Revision note (2026-07-26).** This revision removes the superseded consultation-path
> sections — the old §5.4–§5.5 (`ConsultationRun`, `ReportConversation`), §6 (the
> clustered flow), §7 (focused packets), §8 (force discovery and clustering), §9.2
> (progressive zoom), §11 (policy retrieval) and §13 (the twenty-field recommendation
> contract) — rather than keeping them marked superseded in place. Git history holds
> them, and ADR 0006 records the change. The section numbers `6A` and `8A` are retained
> even though `6` and `8` no longer exist, because code, tests and other documents cite
> them by those numbers.

> **Revision note (2026-07-27).** This revision adds §6C — elicitation, the review asking
> for the case — re-orders §17 around the two moments where architecture advice changes an
> action, and brings §15–§16 up to the delivered detector catalogue. ADR 0009 records the
> change.

---

# 2. Product Vision

ArchCompass is a persistent, context-aware software architecture advisor for developers
and coding agents.

Its purpose is to help answer questions such as:

- Is an abstraction justified by credible variation?
- Where should a new responsibility live?
- Which implementation details should be hidden?
- Is complexity being removed, or merely spread across more files?
- How will the current structure behave under expected future requirements?
- Is the simplest local implementation currently the better design?

Today the product answers those questions by **reviewing the boundaries that already
exist in a repository** — every abstraction the detector can find, judged one at a time
against the user's stated circumstances and the whole policy corpus, with both verdicts
recorded and a conversation over the finished review.

The long-term ambition is wider. ArchCompass should operate throughout the software
lifecycle:

```text
Greenfield idea
    → initial architecture
    → implementation planning
    → implementation review
    → later architectural changes
    → architectural memory and governance
```

It should be useful when no code exists and become more evidence-rich when a repository
is available.

ArchCompass is not intended to replace the developer's judgement. It provides structured
evidence, relevant policies and contextual reasoning so that the developer can make a
better architectural decision.

---

# 3. Core Product Thesis

Software architecture is the placement and containment of complexity under specific
circumstances.

A design cannot be assessed only from generic principles. Its suitability depends on:

- The actual problem.
- Functional requirements and quality attributes.
- Technical and organisational constraints.
- Known future plans and credible forms of variation.
- Existing repository structure and migration cost.
- Team and repository conventions.
- Relevant design policies.
- The consequences of likely future changes.

The central question ArchCompass should answer is:

> Given the available context and expected changes, where should the complexity live?

ArchCompass should not assume that more modularisation, more interfaces or more patterns
automatically produce a better design.

A locally complicated module may improve the overall system when it hides complexity
from the rest of the application. Conversely, a simple-looking value or function may
create substantial system-wide complexity when many unrelated parts depend on it.

## 3.1 The failure ArchCompass exists to correct

Code generation is no longer the constraint. Structure is.

A coding agent asked to satisfy a requirement will satisfy it, and will tend to reach for
an interface, a layer, a registry or a configuration point at each decision — each one
locally defensible, and collectively producing software that is more complex than the
problem requires and harder to understand than the code it replaced. The agent has no
memory of the decisions it already made, no view of the system it is adding to, and no
cost model for indirection, so it cannot tell a boundary that hides complexity from one
that only forwards calls across it.

The result is not incorrect code. It is unnecessarily complex code: abstractions without
credible variation, knowledge duplicated because nothing looked for it first, and
behaviour spread across locations that must now change together.

ArchCompass exists to make that visible and to argue the other way. Its most valuable
answer is frequently **"do not add that"** — and a system that cannot say so is an
abstraction generator, not an advisor.

---

# 4. Unified Greenfield and Brownfield Model

Greenfield and brownfield reviews use **one advisory architecture**.

The only fundamental difference is where finding candidates come from.

## Greenfield

A greenfield case may include the problem statement, desired outcome, actors and
workflows, requirements, quality attributes, constraints, future plans, non-goals,
assumptions and proposed technologies. No repository map exists.

## Brownfield

A brownfield case includes the same contextual information, plus a repository the
advisor can parse: structure, dependencies, call relationships, interfaces and
implementations, tests, configuration and quantified structural signals.

Repository analysis enriches the review. It does not create a separate product or
workflow.

## 4.1 How the model survives the move to candidates

The advisory path begins with a **finding candidate** (§8A). That looks at first like a
brownfield-only design, because the one detector that exists reads an atlas. It is not,
and the distinction matters for what gets built next.

The judgement stage takes `(case, candidate, policies)`. Nothing in it refers to a
repository. The same call, the same corpus and the same verdict shape work for a boundary
that exists and for one that is merely proposed — the question *"is this boundary earning
its place under these circumstances"* does not depend on whether the code has been
written.

What differs between the two is only **where candidates come from**:

- **Brownfield** — a detector derives them from the atlas. Deterministic and complete.
- **Greenfield** — the case states the boundaries the proposed design would introduce,
  and the application enumerates them. Also deterministic: the user supplies the design,
  the application turns each proposed boundary into a candidate, and nothing is invented.

§12.0 holds in both. The application still decides what to look at; in greenfield the
answer comes from the case instead of from a parse, which is a different source of truth
rather than a different rule.

**Status.** Only the brownfield source is built. Greenfield is architecturally reachable
and unbuilt, which is a narrower claim than the one this section made before and should
not be read as more. One concrete obstacle is known: `FindingParticipant.node_id` assumes
an atlas node exists, so a proposed boundary has no honest value to put there. That is
the first thing to resolve when the greenfield source is built, and it must not be
resolved by inventing an identifier.

---

# 5. Six Durable Domain Concepts

ArchCompass is organised around six persistent concepts.

## 5.1 ArchitectureCase

`ArchitectureCase` is the persistent, revisioned model of the architectural decision
currently being considered: the problem and desired outcome, requirements and quality
attributes, technical and organisational constraints, expected future changes,
non-goals, confirmed facts and assumptions, and a repository reference when one exists.

The case is the lens that makes judgement possible at all. The same abstraction is right
in one case and wrong in another, and the case is where that difference lives: a run
against a case saying *"SMS ships next release"* and one saying *"feature freeze, no
variation planned"* reach opposite verdicts on identical code — which is the whole
point.

An ArchitectureCase is not a temporary prompt. Revisions are append-only; every revision
remains available, updates must not silently erase user-authored context, and a review
pins the exact revision it ran against.

The case holds **intent, and only intent**. The advisor never writes into it: no current
recommendation, no confidence, no advisor-authored forces, no revision authored by a run.
Advisor output belongs to the review, where it is pinned to the exact revision, atlas and
policy set that produced it. A case that is both the question and the answer cannot be
re-asked, and the era that tried it could not say which half a reader was looking at
(ADR 0007).

## 5.2 RepositoryAtlas

`RepositoryAtlas` is a deterministic, versioned and queryable map of an existing
repository: containment structure, packages, modules and symbols, imports and
dependencies, known call relationships, interfaces and implementations, tests,
configuration relationships, source locations, structural metrics, change-amplification
and cognitive-scope proxies, and obscurity signals.

The atlas is not an LLM-generated repository summary. Language-specific analyzers
construct it without executing or importing the analysed code, and the same commit
always produces the same atlas.

The complete atlas must not be sent to the reasoning model, and the atlas is substrate
rather than destination (§9.2).

## 5.3 PolicyCorpus

`PolicyCorpus` owns reusable normative guidance: intent, guidance, signals, diagnostic
questions, likely consequences, exceptions, examples, counterexamples and related
policies. Scopes include general design policies, user-authored policies, organisation
or team policies, repository-specific policies, and policies derived from accepted
ADRs.

Policies are reasoning lenses, not automatic violations. Case-specific circumstances
remain in `ArchitectureCase`; reusable normative guidance belongs in `PolicyCorpus`.

The corpus is also the **specification for detection** (§8A.1): every policy that can be
violated structurally implies a detector, and the corpus is presented whole with every
candidate rather than retrieved from.

Repository-local policies must never leak into reviews of another repository, and
conflicting relevant policies remain visible so the advisor can explain the trade-off.

## 5.4 FindingCandidate

`FindingCandidate` is a structural shape found in the atlas, with the evidence that
establishes it: the pattern, the participants (N-ary by construction), the measurements
that made it detectable, the relationships that connect the participants, and **what the
detection method could not see**.

A candidate is explicitly not a violation, and not yet a finding. §8A defines it in
full.

## 5.5 BoundaryReview

`BoundaryReview` is the immutable record of one review: the exact case revision, the
atlas version, the policies presented, every boundary examined with its verdict,
rationale, policy bearings and recommended response, and an **overview** of what those
verdicts amount to together.

The overview is composed in one further model call over the verdicts the review has just
produced, and is written at the same moment as the rest of the record. It states the
situation, the themes that run across boundaries, a recommended sequence and what the
review could not see. It has no verdict field of its own, and every theme and step names
the boundaries it rests on by position, so it can say what a set of verdicts means without
being able to overrule any of them (ADR 0007). The overview also carries the review's
**open questions** — the unknowns its verdicts turned on, consolidated across boundaries
and bound to them by position (§6C).

Both outcomes are stored. A boundary the advisor cleared is the record that it looked —
a report listing only problems reads the same whether every boundary was examined and
cleared or none was ever inspected, and telling those apart is most of §3.1.

## 5.6 ReviewConversation

`ReviewConversation` is the durable, append-only question thread pinned to one
`BoundaryReview`. Each turn puts the whole review in front of the model, and the answer
comes back marking which boundaries it rests on, by position. Every citation is resolved
by ArchCompass from those positions; an answer grounded on nothing is labelled as such
rather than presented as though the review supported it.

A conversation is read-only with respect to the ArchitectureCase and the review. Changed
circumstances become a new case revision and a new review, never an edit.

---

# 6A. The Advisory Path

The advisory path is **two rails converging on one judgement**, and it ends at a page,
not a file.

```text
RAIL A — structure                         RAIL B — intent
(deterministic, case-independent)          (user-authored)

Python repository                          ArchitectureCase
      │  parse AST — the repository        problem, constraints, non-goals,
      │  is never imported or executed     expected future changes
      ▼                                    (append-only revisions)
RepositoryAtlas                                   │
versioned structural map                          │
      │                                           │
      ▼                                           │
Detect FindingCandidates                          │
complete over the atlas — not sampled,            │
not ranked, no model involved                     │
      │                                           │
      └────────────────────┬──────────────────────┘
                           │
                           │      PolicyCorpus — presented whole,
                           │      fixed order, never retrieved from
                           ▼
        Judgement — one model call per candidate:         [model]
        candidate + case + the entire policy corpus
                           │
                           ▼
        Verdict per boundary                              [model]
        material or cleared · rationale · one bearing
        per policy, bound by position
                           │
                           ▼
        Number the boundaries                             [application]
        BR-nnn assigned in detection order, policy
        identity resolved by position
                           │
                           ▼
        Overview — one model call over all of them:       [model]
        what the verdicts amount to as a set · themes ·
        sequence · limits · open questions (§6C), each
        claim bound to the boundaries it rests on, by
        position
                           │
                           ▼
        Compose and persist the BoundaryReview            [application]
        JSON + Markdown, overview included
                           │
                           ▼
        The review page                                   [the destination]
        every boundary examined, material and cleared,
        with the conversation beside it — each question
        carries the whole review; answers cite the
        boundaries they rest on, by position
```

Six properties define the path, each adopted for a stated reason.

**The application chooses what to look at.** A detector decides deterministically and
completely where the advisor's attention goes. Design forces remain a useful *concept* —
the pressures the case exerts — but they are read from the case by the stage that
judges, not discovered as a separate model artifact.

**The rails are independent until judgement.** Detection never sees the case; judgement
never sees the repository, only the candidate's own evidence. Three consequences follow.
The rails are order-free — a repository can be indexed before its case exists, and the
reverse. A case revision invalidates only judgement, so *revise the case, review again*
re-runs the model calls over unchanged candidates. And greenfield (§4.1) is reachable by
replacing only Rail A's source.

**There is no retrieval step.** The whole policy corpus is presented with every
candidate. It is roughly 21,000 characters against an input budget of ~490,000, so
ranking policies would introduce a way to be wrong in exchange for nothing. When the
corpus outgrows one request this changes, and the change will be deliberate rather than
inherited.

**There are no zoom rounds.** A candidate carries its own participants, measurements and
connecting edges, so the evidence for judging it is assembled by the detector rather
than requested iteratively.

**"Not material" is a stored result.** A boundary examined and cleared is recorded with
its reasoning. This is §3.1 made operational: an advisor that only reports problems
cannot be distinguished from one that never looked.

**One stage reads the set.** Judgement is per candidate, so nothing in it can see that
four boundaries fail for the same reason. That observation is worth a model call of its
own, and it is the only stage shown conclusions rather than evidence. It is bounded twice:
its shape has no verdict field, so it cannot contradict a judgement as data, and every
claim it makes names the boundaries it rests on — a claim resting on none is discarded
rather than recorded as unsupported prose.

**The destination is a page, not a file.** The product's value lands when a person reads
the report and interrogates it — *what should I do first, why is BR-003 in here, what is
the biggest risk*. The review page and its conversation are part of the advisory path,
not a viewer bolted on afterwards. §6B governs that surface.

## 6A.1 What a review produces

A `BoundaryReviewReport`: the case title, problem and desired outcome; the policies
presented; every boundary examined, each with its BR-nnn reference, the abstraction and
its sole implementation located in source, the verdict and its reasoning, a recommended
response only when material, the policies that bear on it and how, and what the detection
method could not see; and the overview of what all of it amounts to, with the open
questions whose answers would settle its hinges (§6C).

It contains no alternatives, no scenario analysis, no ADR and no implementation
sequence. A review judges boundaries that already exist; it does not weigh competing
designs, so there is nowhere in the report to put those and nothing to invent to fill
them. Filling such fields from a review would mean inventing alternatives nobody
weighed — §3.1's failure reproduced inside the one artifact a person reads.

---

# 6B. The Workspace

The workspace carries the path in §6A, and its organising rule is:

> **The product is one verb.** Point ArchCompass at a repository and a case, run the
> review, read it, interrogate it. The workspace is that flow made walkable — not a
> collection of pages about the nouns the flow happens to use.

Four commitments follow, argued in full in `docs/workspace-design.md`:

- **The flow has a spine.** One guided path — repository and case as two order-free
  inputs, then run, then the review page. Past reviews and policies are supporting
  surfaces beside it, not peers competing with it.
- **The review page is the centre of gravity.** It is where advice, cleared boundaries,
  scores and the conversation live, and every other surface exists to get a user there.
- **The atlas is backgrounded** (§9.2). Indexing is a progress step inside the flow, and
  atlas evidence surfaces inside findings. The graph explorer is not a primary
  destination; it re-enters later as an evidence drill-down from a finding.
- **Both rails must be completable in the browser.** A flow whose case rail requires a
  CLI detour is not a flow.

`docs/workspace-design.md` is the direction for this surface; `docs/web-workspace.md`
describes the current implementation and follows it milestone by milestone.

---

# 6C. Elicitation — The Review Asks for the Case

## 6C.1 The problem it solves

The case is the product's differentiator and its adoption tax, and both for the same
reason: judgement is conditioned on stated intent. A run against *"SMS ships next
release"* and one against *"feature freeze"* reach opposite verdicts on identical code —
which is the point — but it also means the quality of every verdict is bounded by a
document the user must author before seeing any value. Nobody writes
`expected_future_changes` YAML to evaluate a tool. The effort precedes the value, and
tools shaped that way do not get adopted.

The discipline that fixes it is already the house style. Every stage reports what it
could not see; elicitation makes that report actionable. A review may run against a thin
case. Instead of pretending the thin case settled anything, each verdict states the
circumstance it turned on, and the review hands back the questions whose answers would
settle them. Each answer becomes an ordinary case revision, and the case **accretes from
use** instead of being authored up front. The cold-start problem becomes the onboarding
mechanic.

A verdict against a thin case is not a worse verdict dressed as a better one. It is a
verdict that names its hinge — and a review that says *"BR-004 turns on whether a second
vendor is actually coming"* is more honest than one that guessed silently, whatever the
case contained.

## 6C.2 Two contract extensions, no new stages

Elicitation adds no model call and no pipeline stage. It extends the response contracts
of two calls §6A already makes.

**Judgement states its hinge.** The per-candidate judgement response gains a field
between the rationale and the verdict — reasoning-first ordering (§12.0) is preserved
because a hinge is part of the argument, and an argument states what it rests on before
the conclusion that rests on it. A hinge is the circumstance the verdict *assumed
because the case did not state it*: what is unknown, and which way the verdict moves
under each answer. A verdict that stands whichever way the unknown falls carries no
hinge, and "no hinge" is stated explicitly rather than inferred from absence. This lives
in judgement because judgement is the only stage that knows what it lacked about this
boundary: the candidate says what detection could not see, the hinge says what the case
did not say.

**A set-level call consolidates hinges into questions.** Consolidation is why this is
set-level work: four boundaries turning on whether a second vendor is coming are one
question, not four — asked four times it is noise, asked once with four boundaries cited
it is the most important sentence in the report.

That call is its own stage, `elicit_questions`, and not a widened overview. It was the
overview's tail until measurement moved it (§6C.6): a first pass usually runs against a
case that says nothing, so the conclusion half of that reply was being composed out of
silence and then discarded by the second pass. Splitting them also gives the summarising
stage no field in which to ask, which is what makes the loop terminate — see §6C.6.

Each question carries, in this order:

1. **The unknown** — the circumstance the case does not state.
2. **Why it matters** — which boundaries turn on it, cited by position, and which way
   each verdict moves under each answer.
3. **The question itself**, phrased so the user can answer it from knowledge they have.
   A question the user cannot settle — *"will requirements change?"* — is not a
   question; it is the model returning its own uncertainty to sender.
4. **Where the answer belongs** — one of the case's own fields, chosen from a closed
   enum: `expected_future_changes`, `confirmed_facts`, `technical_constraints`,
   `non_goals`, `assumptions`. The model picks a slot from a bounded set; it never names
   a field freely. Five of the case's fields rather than all of them: these are the ones
   that decide whether a boundary is earning its place, and offering a destination that
   cannot flip a verdict would only give a wrong answer somewhere to go.

## 6C.3 Binding discipline

§12.0 applies unchanged, and elicitation introduces no new kind of key.

- Boundaries are cited by position in the presented set, exactly as the overview's
  themes and the conversation's answers already are. A question citing no boundary is
  discarded rather than recorded as unsupported prose; a citation to an unknown position
  fails validation, with the standard single repair round behind it (§12.1).
- The target case field is an enum in the response schema, never free text.
- Question identity (`Q-n`) is assigned by the application in presentation order, after
  validation. No model-written identifier exists to leak.

## 6C.4 The answer path

Questions are advisor output, so they live in the review — immutable, pinned to the case
revision, atlas version and policy set like every other conclusion (§5.5). They are
never written into the case.

An answer is a **user-authored case revision** through the loop that already exists:
revise the case, review again. Rails independence (§6A) already supplies the economics —
a case revision invalidates only judgement, so answering re-runs the model calls over
unchanged candidates and nothing is re-parsed.

The workspace renders each question beside the boundaries it cites, with an answer box;
submitting composes a case revision that is shown to the user before it is saved.
Pre-filling from the question is allowed; saving without the user seeing what enters
their case is not. The CLI exposes the same two halves — print a review's questions,
apply an answer as a case update — and both rails stay completable in the browser (§6B).

The rule that keeps invariant 23 intact under all of this:

> **The advisor supplies the question. The user supplies the answer. Only the answer
> enters the case, and only as a revision the user has seen.**

A revision **records** which review and which questions it answers, as an `answered` block
carrying the review, and per answer its `Q-n`, the case field the question named, and the
line the reader saw. That is provenance, not write-back: the removed `origin_run_id` (ADR
0007) marked revisions *authored by a run*, where this marks a revision the user authored
and says what prompted it. The substance of the answer is the user's, including when the
user's whole contribution is confirming a phrasing the question suggested.

Its absence is load-bearing: a revision with no block was authored by hand, which is the
only thing that tells the two apart. Skipped questions are absent rather than flagged — what
was skipped is the review's questions minus the ones recorded, and a stored flag would be a
second copy of a fact that can be computed. One review is asked once, so it maps to at most
one answering revision, and the store says so.

Answering is therefore its own operation — `POST /api/reviews/{id}/answers` — and not a case
patch the client composes. The workspace resolves each `Q-n` against that review's own
report and reads the destination from the question, so a client cannot route an answer into
a list its question never named, and cannot produce a revision that has silently lost the
link back to what prompted it. `PATCH /api/cases/{id}` remains, for editing a case by hand.

What this buys is attribution. A question names the boundaries it would settle and the
revision names the questions it answered, so a verdict that moved between passes can be
traced to the sentence that moved it — which is the whole claim of §6C.6 made checkable
rather than asserted.

A verdict that flips after an answer is the mechanism working, not churn: the earlier
review recorded the hinge, the revision settled it, the new review records what it
settled to, and the two reviews pin different case revisions. Nothing is overwritten and
nothing needs reconciling.

## 6C.5 What elicitation may not become

- **Not an intake interview.** The first review runs on whatever case exists, including
  a nearly empty one, and it runs *before* anything is asked. Investigate, then ask. A
  wizard that must be completed before the first run rebuilds the adoption tax with
  better upholstery. What a first pass may withhold is its *verdicts* (§6C.6); what it
  may never do is refuse to look until the reader has filled something in.
- **Not a structure oracle.** A question the atlas could answer — how many
  implementations, who depends on this — is a detector or query gap, not a case gap, and
  must not be asked of the user.
- **Not unbounded.** The bound is structural rather than numeric: every question must
  trace to at least one hinge, hinges exist only where a verdict admitted contingency,
  and consolidation merges duplicates. A numeric cap would encode an opinion about how
  much uncertainty a review is allowed to admit — §8A.4's rule, applied to questions.
- **Not self-answering.** The model never proposes the answer inside the question, and
  the application never promotes an unanswered question into an assumption. An
  unanswered question remains open in the review that asked it.

## 6C.6 A pass that is still asking is not a finished review

§6C shipped as "value first, questions after": one review, its verdicts reported, and the
questions appended to the conclusion. Measurement overturned the premise. On the bundled
`warehouse-sync` example, judged with no case and then re-judged against answers to its own
questions, **four of five verdicts moved.** The "value" the questions were placed after was
mostly wrong, and it was displayed in the same confident vocabulary a settled verdict wears.

Two further observations rule out the obvious softer fix. The one verdict that carried no
hinge moved anyway, and one that did carry a hinge held — so the hinge does not mark which
verdicts are safe to show, and "reveal the un-hinged ones" is not a sound refinement. And
because a first-pass review was stored as `succeeded`, it read as finished in every listing
for ever, whether or not anyone ever answered.

So a review is **two passes across two records**, and the reader walks one journey:

1. Sweep the atlas. 2. Judge every boundary. 3. Ask what it needs to know.
4. *The reader answers.* 5. Their answers become a case revision.
6. Judge every boundary again. 7. Read the verdicts as a set.

Both records are immutable and each pins its own case revision, which is why this cannot be
one record: pass 2 judges a different case. The second names the first in `elicited_from`,
which is what makes it a second pass — and is stored rather than inferred, because revising a
case by hand also produces a newer review and must not be mistaken for answering.

The rules this introduces:

- **A pass with questions outstanding reports `awaiting_answers`, never `succeeded`.** Its
  verdicts are stored — they are what the questions were built from — but nothing presents
  them as findings. That status is terminal: nobody is obliged to answer, and a record
  saying "still waiting" is the truthful account of a question nobody came back to.
- **A pass with nothing to ask concludes immediately.** The flow is conditional, not always
  two passes: a case someone actually wrote usually settles its own verdicts, and asking is
  the exception rather than the toll.
- **The second pass cannot ask.** The summarising contract has no field for a question, so
  termination is enforced by the grammar rather than by prose a model may or may not follow.
  A verdict that still hinges — because a question was skipped — is reported as a finding
  with its contingency stated, which is a caveat rather than another gate.
- **There is always a way past.** The waiting page can reveal its provisional verdicts,
  under what the measurement actually says about them. Revealing resolves nothing and the
  record still says nobody answered. Withholding unconditionally would rebuild the adoption
  tax in a new shape — *answer my questions or you get nothing* — for the reader most likely
  to be unable to answer, which is someone looking at unfamiliar code.

The cost is honest and named: roughly double the model calls, 2N+2 against N+1. Re-judging
only the hinged boundaries would halve that and is refused, because the boundary that moved
without a hinge is the reason it cannot be trusted to.

## 6C.7 Asking about the question

A question the reader cannot make sense of stops the loop as completely as one they cannot
answer, and it fails in a worse way: they do not know that is what happened. Three things
follow, and the first two are repairs to what §6C.2 was already producing.

**A question carries what the review saw.** `what_the_review_saw` states the observation —
which abstractions, what the code does today, what the case says about it now — and it is
the field a reader is shown under the question. It exists because `unknown` was being
written as the question with its question mark removed, so the second line taught nobody
anything. `unknown` survives as a *subject*, one line, phrased to stand as the subject of a
sentence, because that is what the recorded answer is composed from.

**An answer is recorded joined to what it settles.** The case is read with no question
beside it — by the second pass, which judges against the snapshot alone, and by whoever
opens the case editor later. `"They shouldn't rely on it"` was recorded verbatim from a live
run and its "it" refers to nothing. So the workspace composes `unknown` and the answer into
one line, shows it, and lets the reader edit it before it saves. That is §6C.4 exactly:
pre-filling from the question is allowed, saving something unseen is not.

The alternative — threading the questions into the judging stage alongside the case — is
refused. A review pins a case revision, an atlas version and a policy set, and those inputs
determine its verdicts. A judge that also read the *asking review's* record would make two
reviews of the same revision reach different conclusions depending on which one elicited
them, and a verdict would no longer be reproducible from what it says it ran against.

**A reader may discuss one question while the review is still waiting.** Not the review — a
conversation about that is still refused at `awaiting_answers`, because its verdicts are the
ones being withheld. A conversation pinned to `(review, Q-n)` is shown that question, the
boundaries it cites *and no others*, the case, and the method background. The held set is
not in the input, so there is nothing there to leak, and the narrower scope is what makes
the surface safe rather than a promise the stage is asked to keep.

It may help the reader reach an answer, and may offer a phrasing in `suggested_answer` —
which exists only in that stage's reply schema, so a conversation about a concluded review
cannot propose a case entry however it is prompted. What the suggestion does is fill the
answer box when the reader presses a button. It then walks the same preview as anything
typed by hand. §6C.5's *not self-answering* is unchanged and now has a sharper edge: the
model may not treat an answer as given, and the application never promotes a suggestion into
an answer. Invariant 25 holds across all of it — the advisor supplies the question, the user
supplies the answer, including where their whole contribution is confirming a phrasing they
were shown.

---

# 8A. Finding Candidates

## 8A.1 What a finding candidate is

> A finding candidate is a structural pattern that could make a policy in the corpus
> relevant.

The policy corpus is the specification. Every policy that can be violated *structurally*
implies a detector; the detector finds where the policy might apply; the model decides
whether it does. Policies that cannot be checked structurally — deliberate consistency,
designing it twice — remain judgement input rather than detector targets.

A candidate carries:

- **Pattern** — which shape of complexity was detected.
- **Participants** — every node involved, located. A candidate is **N-ary by
  construction**: duplicated knowledge is a fact about a set of modules, and a type that
  holds one node would discard the finding while appearing to record it.
- **Measurements** — what made it detectable, so the candidate is evidence rather than
  opinion, with each measurement's nature and limitations retained (§9.3, §9.4).
- **Relationships** — the dependencies, dependants and implementations that connect the
  participants, so the model can judge blast radius rather than inspecting nodes in
  isolation.

A candidate is explicitly **not a violation**. Materiality depends on circumstances the
static view cannot see, so "this does not matter here" must remain a first-class answer
at every stage that consumes one.

## 8A.2 Detection is relational, not isolated

A pattern found by looking at one node in isolation is nearly always a lint, not an
architectural finding. Architecture is about placement, so the detectable evidence is
almost always a relationship: the same knowledge in several modules, one concept edited
in several places, an abstraction with nothing behind it, several implementations with
no common owner.

Detectors therefore read the atlas graph — edges, implementations, callers, reverse
reach — and not only node attributes. A detector that cannot express "these N nodes,
related this way" cannot express the findings that matter.

## 8A.3 The catalogue has two halves; both are built

**Sole implementation** — an abstraction with exactly one implementation behind it. It is
chosen because it is the direct structural trace of the failure in §3.1, because the policy
corpus already states the rule it makes relevant, and because it is decidable from edges the
atlas already records.

For a long time it was the whole catalogue, and the cost of that was written down here
rather than discovered later: unnecessary complexity has two directions, and an advisor that
detects only one becomes an advocate for the other. That cost was then paid in public. Run
against a real repository whose actual problem was the opposite — an agent spreading vendor
customisations through modules with no reason to know a vendor existed — the advisor
reported nothing at all, which reads as approval.

**Indirection without hiding** — an abstraction that adds a boundary while hiding
nothing: an interface with a single implementation and no credible variation, a module
whose public surface only forwards calls, a configuration point with one value. The
advice is usually *remove it, or do not add it*. This is the direction that ships.

**Repetition without ownership** — the same knowledge or shape repeated with no common
owner. The advice is usually *give this one owner* — an agnostic boundary with specific
implementations behind it. Two detectors ship for it:

- **Duplicated knowledge** — one module-level constant stated in several modules. The
  measurements say how many copies and how many distinct values, so a set that has already
  drifted is distinguishable from one that merely might.
- **Scattered concept** — a module that already sits behind an abstraction whose name is
  nonetheless spelled out in modules outside its package. Restricted to concepts that have
  somewhere to live, because the question is not "is this name used" but "is this name used
  by code that was given a boundary to use instead".

Both are name-based, and both say so. A name match cannot tell a dependency from a
coincidence, two modules can define `TIMEOUT` about unrelated things, and a composition root
naming a backend is doing its job — which is why these are candidates and never verdicts.
Knowledge that leaked without carrying its name along is invisible to either.

Both halves are the same underlying judgement — where should the complexity live — reached
from opposite sides. A single-implementation interface and three parallel bespoke providers
are each a candidate; only the case can say which one is wrong here, and often neither is.
The advice they lead to runs in opposite directions, so the judging contract names the
pattern it was given before it reasons: applying the wrong frame produces confident
nonsense, and "remove this boundary" is exactly the wrong answer to a fact with no owner.

**Still unbuilt.** Several bespoke implementations preparing the same request in parallel is
computed by the analyzer but only as a signal, not yet a candidate. No review may present
its silence on that as evidence that none is there.

## 8A.4 What a detector may not do

A detector may not decide importance, assign severity, or state that a policy was
violated. It reports that a pattern is present, with the evidence that establishes it
and the limitations of the method that found it. Ranking and prioritisation, when they
exist, are application concerns computed from measurements — never from model output,
and never smuggled into the detector as a threshold that encodes an opinion.

## 8A.5 From candidate to verdict

One model call per candidate, carrying the case, that candidate, and **the entire policy
corpus**. The corpus is small enough to present whole, so there is no retrieval step:
nothing ranks policies, nothing thresholds them, and the advisor is never silently
denied a policy that would have applied.

Policies are presented in a fixed order and the reply returns one bearing per policy in
that order. No policy identifier is sent and none is read back. Arity is therefore the
entire binding — a reply one entry short does not lose one answer, it shifts every later
answer onto the wrong policy and still parses — so the count is fixed in the response
grammar and checked again after parsing.

The verdict is `material` or not, with the reasoning, and a recommended response only
when material. **An immaterial verdict is a recorded result, not a discarded
intermediate.**

---

# 9. RepositoryAtlas Principles

## 9.1 Objective map first

The LLM should not be responsible for reconstructing repository structure from raw
source files. Language-specific analyzers produce a canonical structural graph before
model reasoning begins. For Python V1, analysis uses the built-in AST without importing
or executing repository code.

## 9.2 Substrate, not destination

The atlas plays three roles, and they deserve different treatment:

1. **Substrate for detection.** Candidates are derived from it. This role needs no
   surface at all: "index the repository" is a step inside starting a review, not a
   concept the user manages.
2. **Evidence inside findings.** Locations, participants and measurements in a report
   come from the atlas and surface *as the finding's content* — the reader never needs
   to know the atlas exists.
3. **An explorable map.** A graph view of the atlas answers questions a report reader
   actually has — *what depends on the thing this verdict says to remove?* — but only
   when it is entered **from a finding**, with a question attached. As a free-standing
   destination it is a map with no question, and it competes with the flow for the
   user's orientation.

Roles 1 and 2 are permanent and invisible. Role 3 earns a surface only as an evidence
drill-down reached from a review, not as a peer of the flow (§6B).

## 9.3 Self-describing evidence

Atlas query results should identify what the node is, where it exists, why it was
selected, which metric or signal made it relevant, which dependencies and dependants are
involved, and which tests may be affected.

Opaque IDs remain necessary for validation but are insufficient as reasoning context.

## 9.4 No universal complexity score

ArchCompass must preserve separate metric dimensions.

A module may have high local control-flow complexity, low outward dependency impact,
strong information hiding and low change amplification all at once. Collapsing these
into one score would erase the distinction between contained implementation complexity
and complexity imposed on the rest of the system.

---

# 10. Complexity Model

ArchCompass uses the following broad model.

## Causes of complexity

- **Dependencies:** code cannot be understood or changed in isolation.
- **Obscurity:** important information or relationships are difficult to discover.

## Symptoms of complexity

- **Change amplification:** a conceptually small change requires many coordinated edits.
- **Cognitive load:** a developer must understand too much information to complete a
  task.
- **Unknown unknowns:** important dependencies or consequences are not apparent.

ArchCompass cannot measure human cognitive load or obscurity directly. It reports
objective proxies and evidence-backed signals.

## Structural dimensions

The atlas may quantify physical size, logical statements, branching and nesting,
parameters, public API surface, fan-in and fan-out, forward and reverse dependency
reach, dependency depth, cycles, number of implementations, known callers, associated
tests and configuration relationships.

## Change-amplification proxies

Likely affected modules, interfaces crossed, implementations requiring coordinated
changes, configuration locations involved, tests in the reverse dependency
neighbourhood.

## Cognitive-scope proxies

Modules in the relevant dependency neighbourhood, symbols on representative paths,
boundaries traversed, related configuration locations, local control-flow complexity,
public API surface.

## Obscurity signals

Wildcard imports, dynamic imports, implicit registration, shared mutable state,
duplicate sources of truth, cyclic dependencies, unresolved calls, similar constants
across modules, important behaviour spread across unrelated locations, misleading
relationships between a domain category and an incidental implementation property.

Signals require architectural interpretation. They are not automatic violations.

---

# 12. Evidence and Claim Discipline

## 12.0 Division of labour

> **The application decides what to look at. The model decides what it means. Nothing
> the model writes is ever used as a key.**

This governs every reasoning stage.

*What to look at* is search and bookkeeping: which nodes are relevant, which policies
were presented, which candidate a verdict describes, which boundary an answer cites. All
of it is derivable, reproducible and testable, and the application already holds the
answer on both sides of the call.

*What it means* is judgement: whether a structural pattern matters given this case,
which policies bear on it, what the consequence is, what should change. Only the model
can do this, and it is the only thing worth spending a model call on.

The third clause is the operational one. A model that must reproduce an identifier to be
understood will eventually reproduce it wrongly — not by inventing it, but by copying it
imperfectly — and the failure is silent because the value looks plausible. So an
application-owned identifier must never cross the wire in either direction. Where a
stage needs the model to point at something, it presents a bounded set and takes back
either a short request-local handle constrained by the response schema, or a position in
the set it presented. Where the application already knows the answer, the stage does not
ask.

This extends §9.3: opaque IDs are necessary for validation and insufficient as reasoning
context — and they are also unsafe as model output.

### Delivering evidence is not retrieval

The same rule decides how a stage gets source code, and decides it against the obvious
answer. A reader asking to see the leak is asking for lines the detector already picked:
every finding participant records a span, so selection happened when the verdict was
reached. The application reads those spans and puts the text in the input. A tool the model
could call to fetch source would invert the division — the stage would be choosing its own
evidence — and it would be solving a search problem that does not exist.

"It will not fit in the context" is the reason to look for a retrieval layer, and it is
worth checking before building one. It did fit: bounded by the detector's spans, a review's
source is order 10–15k characters against an input budget near 490k. The same measurement
removed policy retrieval from the judging stage (§6A) and an embedding index from the
conversation's background. Where the evidence fits, retrieval is indirection in front of one
concrete thing (ADR 0013).

**Delivering it in does not license handing it back.** Evidence goes to a stage so that it
can reason about what the evidence shows, and the reply says what it means — never the
evidence again. Where a stage's answer needs a value the application already holds, the
stage points at it and the application renders it; a model reproducing that value can only
produce a second copy, and a second copy can disagree with the first.

This was learned in the direction the third clause above predicts. The answering stage was
given each finding's source and told to quote it back "character for character", which is
the one remedy that clause rules out — and the run after that instruction landed returned
`"chelsine"` where the file says `"chelsie"`. The reader sees a line attributed to their own
repository that is not in it, and no validation can catch it, because a plausible identifier
is exactly what a well-formed string field accepts.

The distinction that survives is between *reproducing* and *composing*. An illustrated fix
is still written by the model: it does not exist anywhere to be rendered, so nothing else
can write it, and it is labelled as an illustration the review never ran. A wrong name there
is a bad suggestion beside the correct spelling; a wrong name in a quotation is a false
record of the repository.

### Field order is part of the contract

A structured-output model fills a response schema in the order the schema declares, so
**a conclusion declared before its reasoning is a conclusion reached before its
reasoning.** Put the argument first and the verdict last, and the verdict follows what
was argued; put the verdict first and the prose becomes justification for a choice
already made — including when the prose ends up disagreeing with it.

This is not a style preference. The judgement stage shipped with `material` ahead of
`rationale` and a live run returned `material=false` beside a rationale concluding that
removing the abstraction would cost nothing. Both halves validated. Nothing downstream
could have detected the contradiction, because each field was individually well-formed.

So: every stage orders its response fields as reasoning → conclusion, and a schema whose
first field is a verdict is a defect regardless of what the prompt says.

## 12.1 Grounding

Every statement a person reads must be traceable to something that was actually
presented to the stage that produced it.

- A verdict's policy bearings refer only to policies presented with that candidate,
  bound by position.
- A report locates every participant in source and prints each candidate's detection
  limitations against the boundary itself, not once in a footer.
- A conversation answer marks the boundaries it rests on, by position; an answer
  grounded on none is labelled as such rather than presented as supported.
- Unknown or unsupported references fail validation. One constrained repair attempt is
  permitted; if validation still fails, the failure is recorded explicitly and nothing
  is persisted as though it had succeeded.

ArchCompass must never present assumptions or model interpretations as repository
facts.

---

# 14. Persistent Advisor Vision

ArchCompass should eventually act as a continuous architectural reasoning layer around
development.

**Before implementation** it advises on responsibility boundaries, initial architecture,
alternatives, risks and expected change. **During implementation** it may later advise a
coding agent: whether the plan matches the accepted direction, whether responsibilities
are moving into the intended modules, whether new dependencies create unplanned blast
radius. **After implementation** it may later analyse whether the repository aligns with
the decision, whether complexity leaked, whether revisit triggers have become true.

This continuous-advisor vision is a long-term goal. It must not cause premature
implementation of monitoring, autonomous modification or governance infrastructure.

---

# 15. Current Baseline

The review path exists end to end:

- Typed domain models and immutable ArchitectureCase revisions.
- Versioned Python AST atlases: nodes, edges, metrics, obscurity signals and
  deterministic bounded queries.
- Three structural detectors (§8A.3), both catalogue directions, producing complete,
  evidence-carrying candidates.
- Judgement of each candidate against the case and the whole policy corpus, policies
  bound by position, no identifier crossing the wire in either direction (§12.0).
- Immutable `BoundaryReview` persistence with JSON and Markdown reports.
- Append-only `ReviewConversation` pinned to one review, answers grounded by position.
- Markdown policy parsing, validation and source management.
- Configurable providers — local Ollama, hosted Google AI Studio — plus deterministic
  substitutes so the whole suite runs without a model.
- CLI commands for the full path and a browser workspace: bundled examples, the review
  report with its question dock, and an atlas graph view.
- Three scored examples with known answers. `boundary-review` asks whether a boundary
  absorbs any variation at all; `speech-vendor` asks whether it is in the right place,
  and its case is written to state no finding; `audiobook-studio` exercises all three
  detectors at once, with both verdicts appearing under each repetition detector. `make
  demo` grades a live run against the first, `make eval-local` against all three.

The broad dependency architecture is correct:

```text
Presentation
    → application workflows
        → domain models and ports
            ← adapters

bootstrap.py = composition root
```

Domain and application code must remain independent from Typer, HTTPX, SQLite and AST
implementation details.

---

# 16. The Review-Centred Workspace (delivered)

The engine was ahead of its surface. Bringing the workspace in line with §6B and
`docs/workspace-design.md` is done, in the order that document sequenced:

1. **Subtraction** — the consultation era removed from the frontend: dead `/new` and
   `/runs/:id` links, the unrouted `architecture-workspace.tsx`, era copy, and the era's
   types and fields rendered on case cards.
2. **The spine** — Home is the flow: repository and case as two order-free rails
   converging on run. Primary navigation is Home, Policies and Reviews — the flow, the
   library it reads and the record it writes; the noun pages are dissolved and the graph
   explorer is demoted to an entry from the repository rail and from each finding.
3. **The case rail in the browser** — a case is authored, imported and read back as YAML
   through the existing endpoints, so the flow needs no CLI detour. The form since gained
   a structured mode whose fields carry a good and a bad example each.
4. **A run the user can see** — the stages a review has, with every boundary named and its
   verdict shown as it lands, from a streamed response. No job queue (§18); the mechanism
   and its reasoning are recorded in `docs/web-workspace.md`.
5. **The iterate loop** — revise the pinned case into a new revision and review again,
   with the reviews of one case linked both ways and the review's pinning printed.

`docs/workspace-design.md` §7.6 left three follow-ons. Two are now delivered: the
structured case form, and the atlas drill-down — reached from a finding, and carried on the
review page as a map of the boundaries it examined with each verdict on its node. The
greenfield rail waits on §4.1.

Two things were deliberately excluded. The second detector — *repetition without
ownership*, §8A.3 — has since shipped, both halves of it. Greenfield candidates (§4.1)
remain sequenced (§17).

---

# 17. Planned Development Sequence

The sequence is ordered by a product observation as much as an engineering one: advice
earns its keep at the moment a boundary decision is being made, and there are two such
moments — a pull request is open, or a coding agent is about to write code. A
whole-repository review read outside any decision is how the mechanism is demonstrated
and evaluated; the same review, arriving at one of those two moments, is the product.
The phases therefore move the judgement toward those moments — and first remove the cost
of getting started at all.

## Phase 1 — The review path (delivered)

Deterministic candidates, per-candidate judgement against the whole corpus, immutable
reviews, grounded conversations, scored evaluation.

## Phase 2 — The review-centred workspace (delivered)

§16. The flow is walkable in the browser, both rails included: start, run visibly, read,
interrogate, revise and run again.

## Phase 3 — The second detector (delivered)

*Repetition without ownership* (§8A.3): duplicated knowledge and scattered concept,
completing the catalogue's other half so the advisor sees both directions of unnecessary
complexity.

## Phase 4 — Elicitation (current)

The review asks for the case, §6C in full: judgement states its hinge, the overview
consolidates hinges into questions bound by position, and answers return as
user-authored case revisions through the existing revise-and-review loop. Sequenced
first because it removes the adoption tax — the case accretes from use instead of being
authored up front — and because it costs no new model calls and no new stages.

## Phase 5 — Greenfield candidates

Candidates stated in the case instead of parsed from code (§4.1), so a boundary can be
judged before it is built. Elicitation makes this practical as well as reachable: a
greenfield case starts thin by definition, and the questions are how it thickens.

## Phase 6 — Change and implementation review

Branch and diff analysis — the pull-request moment. A diff carries a handful of
candidates rather than a repository's worth, so cost is bounded by the change, and a
boundary is judged once, when it is introduced, rather than re-litigated on every run.
Comparing atlas versions and estimating introduced or reduced blast radius belong here.

## Phase 7 — Coding-agent advisory integration

An MCP surface over contracts the earlier phases made stable: consult a proposed
boundary before the code exists (Phase 5), review a diff after it is written (Phase 6).
The consumer of architecture advice at scale is increasingly the agent about to create
the boundary — §3.1 addressed at its source rather than after the fact.

## Phase 8 — Decision lifecycle

Explicit states for recommendations: proposed, accepted, rejected, superseded,
deferred. Acceptance is what keeps a repeated review quiet — an accepted boundary
appears as accepted rather than re-argued — and accepted decisions may become
repository-local architectural memory or accepted-ADR policies. Do not automatically
promote every recommendation to policy. Sequenced after the advisor is in the loop,
because acceptance only pays once something runs repeatedly.

## Phase 9 — Longitudinal architectural memory

Git co-change evidence, decision histories, revisit-trigger evaluation, supersession
chains, trend analysis.

## Phase 10 — Broader analysis

Only after the Python architecture is proven: additional languages, runtime evidence,
data-flow models, deployment topology. Deliberately last rather than early: the teams
feeling §3.1 first are reachable in one language, and a detector set that has not earned
trust in one language is not improved by being wrong in two.

---

# 18. Explicit Non-Goals for the Current Stage

Do not currently add:

- Autonomous code modification.
- Automatic pull-request comments.
- Continuous repository monitoring.
- Fine-tuning or model training.
- Multiple programming languages.
- Runtime tracing.
- Git co-change analysis.
- Whole-program data flow.
- Cloud accounts or multi-tenancy.
- A job queue or background-execution infrastructure for reviews.
- A generic agent framework.
- A universal complexity or maintainability score.
- Automatic enforcement of every policy.
- A broad plugin marketplace.
- Architecture changes without evidence.

Interfaces may permit later adapters, but the project should not contain unused
extension infrastructure.

---

# 19. Architectural Invariants

Contributors and coding agents must preserve these invariants.

1. Greenfield and brownfield use one advisory architecture.
2. `ArchitectureCase` owns case-specific context.
3. `RepositoryAtlas` owns deterministic repository evidence.
4. `PolicyCorpus` owns reusable normative guidance.
5. `BoundaryReview` is immutable.
6. `ReviewConversation` is append-only and pinned to one review.
7. The analysed repository is never imported, executed or modified.
8. The complete atlas or repository is never passed to the reasoning model.
9. Reasoning contexts are bounded: a candidate carries its own evidence; a conversation
   turn carries one review.
10. A review records every boundary examined, cleared ones included.
11. Metrics remain separate dimensions.
12. Policies are guidance, not automatic violations.
13. Facts, assumptions, policies and inferences remain distinguishable.
14. Every repository or policy reference is validated.
15. Failed validation cannot mutate the ArchitectureCase.
16. A local or unchanged design is a valid recommendation.
17. No provider-specific technology may leak into the domain or application core.
18. `bootstrap.py` remains the composition root.
19. New abstractions require a concrete responsibility and credible need.
20. Documentation and tests must describe metric limitations honestly.
21. Old reviews retain the exact case, atlas and policy versions they used.
22. The application decides what to look at; the model decides what it means; nothing
    the model writes is used as a key (§12.0). Nor does the model reproduce a value the
    application already holds: where an answer needs one, it points and the application
    renders. Composing something that does not yet exist — an illustrated fix — is the
    model's and stays labelled as such. *A retyped copy is not a key and was permitted by
    the first clause alone, which is how a stage came to be told to quote source "character
    for character" and returned an identifier the repository does not contain.*
23. `ArchitectureCase` holds user intent only; the advisor never writes into it.
24. A review's overview may summarise its verdicts and may not revise them: no verdict
    field, and every claim names the boundaries it rests on.
25. Elicited questions are advisor output and live in the review; an answer enters the
    case only as a user-authored revision the user has seen before it is saved (§6C).
    A phrasing may be suggested — by the question, or by a discussion of it — and becomes
    an answer only when the user adopts it (§6C.7).

---

# 20. Guidance for Coding Agents

Before changing ArchCompass:

1. Read this document.
2. Read the relevant subsystem documentation.
3. Inspect the current implementation and tests.
4. State which master-plan objective the change supports.
5. Identify affected domain concepts and responsibility boundaries.
6. Avoid broad refactoring unless required by the requested capability.
7. Preserve evidence validation and versioning.
8. Add deterministic tests before relying on a live model.
9. Update documentation when a public contract changes.
10. Do not add features listed as non-goals.

A coding agent should not treat this document as permission to implement the entire
roadmap. Implement only the current requested milestone.

When a requested change conflicts with this master plan, stop and describe the conflict
rather than silently changing the project direction.

---

# 21. Documentation Map

This document governs product direction.

- `docs/product-design.md` — product purpose and boundaries.
- `docs/architecture.md` — dependency direction and subsystem relationships.
- `docs/domain-model.md` — central domain objects.
- `docs/repository-atlas.md` — atlas construction and query model.
- `docs/atlas-metrics.md` — exact metric definitions and limitations.
- `docs/policy-format.md` — policy schema and applicability.
- `docs/persistence-model.md` — immutable versions and storage ownership.
- `docs/workspace-design.md` — the workspace direction (§6B in detail).
- `docs/web-workspace.md` — the workspace as currently implemented.
- `docs/evaluation.md` — evaluation cases and acceptance criteria.
- `docs/adr/` — accepted architectural decisions.
- `docs/plans/` — implementation plans; marked in place where superseded.

Subsystem documentation should not repeat the entire master plan. It should link back to
it and explain the concrete implementation.

---

# 22. Maintaining This Master Plan

Update this document when:

- The product purpose materially changes.
- A core durable domain concept is added or removed.
- The advisory pipeline changes.
- A new roadmap phase is accepted.
- An architectural invariant is intentionally changed.
- A major non-goal becomes an active product capability.

Do not update it for internal refactoring, dependency upgrades, minor CLI changes, new
tests that do not change product behaviour, or implementation details already covered by
subsystem documentation.

Material changes should be accompanied by an ADR explaining the previous direction, the
new direction, why the change is justified, consequences and migration implications.

---

# 23. Definition of Long-Term Success

ArchCompass succeeds when it can help a developer or coding agent make architecture
decisions that are:

- Grounded in the actual problem.
- Informed by available repository evidence.
- Explained using relevant design policies.
- Sensitive to future change.
- Honest about uncertainty.
- Explicit about trade-offs.
- Careful about introducing abstractions.
- Traceable through validated evidence.
- Persistent across the development lifecycle.

The intended value is not generating more code.

The intended value is helping software systems remain understandable and changeable as
code generation becomes easier.
