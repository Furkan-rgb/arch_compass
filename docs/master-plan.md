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
atlas version, the policies presented, and every boundary examined with its verdict,
rationale, policy bearings and recommended response.

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
        Compose and persist the BoundaryReview            [application]
        BR-nnn assigned in detection order, policy
        identity resolved by position, JSON + Markdown
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

**The destination is a page, not a file.** The product's value lands when a person reads
the report and interrogates it — *what should I do first, why is BR-003 in here, what is
the biggest risk*. The review page and its conversation are part of the advisory path,
not a viewer bolted on afterwards. §6B governs that surface.

## 6A.1 What a review produces

A `BoundaryReviewReport`: the case title, problem and desired outcome; the policies
presented; and every boundary examined, each with its BR-nnn reference, the abstraction
and its sole implementation located in source, the verdict and its reasoning, a
recommended response only when material, the policies that bear on it and how, and what
the detection method could not see.

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

## 8A.3 The catalogue has two halves; one is built

**Sole implementation** — an abstraction with exactly one implementation behind it. That
is the whole catalogue today. It is chosen because it is the direct structural trace of
the failure in §3.1, because the policy corpus already states the rule it makes
relevant, and because it is decidable from edges the atlas already records.

One detector is a deliberate limit, and its cost has to be written down rather than
discovered later. Unnecessary complexity has two directions, and an advisor that detects
only one becomes an advocate for the other.

**Indirection without hiding** — an abstraction that adds a boundary while hiding
nothing: an interface with a single implementation and no credible variation, a module
whose public surface only forwards calls, a configuration point with one value. The
advice is usually *remove it, or do not add it*. This is the direction that ships.

**Repetition without ownership** — the same knowledge or shape repeated with no common
owner: a constant duplicated across modules, several bespoke implementations preparing
the same request in parallel, one concept requiring coordinated edits in unrelated
locations. The advice is usually *give this one owner* — an agnostic boundary with
specific implementations behind it. This is not detected yet, and is the first detector
added after the workspace milestone (§16).

Both are the same underlying judgement — where should the complexity live — reached from
opposite sides. A single-implementation interface and three parallel bespoke providers
are each a candidate; only the case can say which one is wrong here, and often neither
is. Until the second direction exists ArchCompass sees half the problem, so no review
may present its silence on repetition as evidence that none is there.

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
- One structural detector (§8A.3) producing complete, evidence-carrying candidates.
- Judgement of each candidate against the case and the whole policy corpus, policies
  bound by position, no identifier crossing the wire in either direction (§12.0).
- Immutable `BoundaryReview` persistence with JSON and Markdown reports.
- Append-only `ReviewConversation` pinned to one review, answers grounded by position.
- Markdown policy parsing, validation and source management.
- Configurable providers — local Ollama, hosted Google AI Studio — plus deterministic
  substitutes so the whole suite runs without a model.
- CLI commands for the full path and a browser workspace: bundled examples, the review
  report with its question dock, and an atlas graph view.
- A scored example with known answers (`eval/cases/boundary-review`); `make demo` grades
  a live run against it.

The broad dependency architecture is correct:

```text
Presentation
    → application workflows
        → domain models and ports
            ← adapters

bootstrap.py = composition root
```

Domain and application code must remain independent from Typer, HTTPX, SQLite,
sqlite-vec and AST implementation details.

---

# 16. The Review-Centred Workspace (delivered)

The engine was ahead of its surface. Bringing the workspace in line with §6B and
`docs/workspace-design.md` is done, in the order that document sequenced:

1. **Subtraction** — the consultation era removed from the frontend: dead `/new` and
   `/runs/:id` links, the unrouted `architecture-workspace.tsx`, era copy, and the era's
   types and fields rendered on case cards.
2. **The spine** — Home is the flow: repository and case as two order-free rails
   converging on run, with past reviews beside them. Primary navigation is Home and
   Policies; the noun pages are dissolved and the graph explorer is demoted to an entry
   from the repository rail.
3. **The case rail in the browser** — a case is authored, imported and read back as YAML
   through the existing endpoints, so the flow needs no CLI detour.
4. **A run the user can see** — `judging boundary k of n`, named, from a streamed
   response. No job queue (§18); the mechanism and its reasoning are recorded in
   `docs/web-workspace.md`.
5. **The iterate loop** — revise the pinned case into a new revision and review again,
   with the reviews of one case linked both ways and the review's pinning printed.

`docs/workspace-design.md` §7.6 leaves three follow-ons: the finding-level atlas
drill-down, a structured case form beside the YAML editor, and the greenfield rail once
§4.1 exists.

Two things were deliberately excluded and remain next in line. The second detector —
*repetition without ownership*, §8A.3 — and greenfield candidates (§4.1). Neither is
blocked; both are sequenced.

---

# 17. Planned Development Sequence

## Phase 1 — The review path (delivered)

Deterministic candidates, per-candidate judgement against the whole corpus, immutable
reviews, grounded conversations, scored evaluation.

## Phase 2 — The review-centred workspace (delivered)

§16. The flow is walkable in the browser, both rails included: start, run visibly, read,
interrogate, revise and run again.

## Phase 3 — The second detector

*Repetition without ownership* (§8A.3), completing the catalogue's other half so the
advisor sees both directions of unnecessary complexity.

## Phase 4 — Greenfield candidates

Candidates stated in the case instead of parsed from code (§4.1), so a boundary can be
judged before it is built.

## Phase 5 — Decision lifecycle

Explicit states for recommendations: proposed, accepted, rejected, superseded,
deferred. Accepted decisions may become repository-local architectural memory or
accepted-ADR policies. Do not automatically promote every recommendation to policy.

## Phase 6 — Coding-agent advisory integration

Expose structured review and decision context to coding agents. MCP or another
integration may be considered here, but only after the advisory contracts are stable.

## Phase 7 — Change and implementation review

Branch or diff analysis, comparing atlas versions, estimating introduced or reduced
blast radius, detecting architectural drift.

## Phase 8 — Longitudinal architectural memory

Git co-change evidence, decision histories, revisit-trigger evaluation, supersession
chains, trend analysis.

## Phase 9 — Broader analysis

Only after the Python architecture is proven: additional languages, runtime evidence,
data-flow models, deployment topology.

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
    the model writes is used as a key (§12.0).

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
- `docs/plans/` — historical implementation plans; marked in place where superseded.

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
