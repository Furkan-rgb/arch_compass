# Domain model

`domain/` holds the types and the rules that hold whatever the storage and the provider happen
to be. Nothing here reads or writes anything, and nothing here is authored by a model: every
identifier a record keys on is derived by the application from content it can see. Pydantic
models forbid unknown fields and validate the current schema only — there are no compatibility
shims, and a stored document written by a superseded schema is reported rather than reinterpreted
(ADR 0002).

## The case: stated intent

An `ArchitectureCase` is what a person says they are trying to do. Title, problem statement and
desired outcome; actors and workflows, functional requirements, quality attributes, technical and
organisational constraints, expected future changes and non-goals; four statement collections
(`confirmed_facts`, `derived_constraints`, `assumptions`, `unresolved_questions`) and
`design_forces`; an optional repository reference, policy subjects and alternatives.

Only `title` is required. Requiring the problem statement made authoring a case the price of
seeing a single verdict, which is the tax elicitation exists to remove: a review can run against
a repository alone and ask for what it lacked.

Nothing the advisor concludes is written back into the case — the case is intent, its conclusions
live in the review that reached them (ADR 0007). The one thing that does come back is an answer,
and it comes back as a `Clarification`: the question and the user's reply as a pair, first-class
on the case, because the second pass sees the case alone and an answer without its question is
not legible (ADR 0014).

A `CaseUpdate` is partial — omitted fields are preserved, supplied collections replace their
previous value — and each update produces a complete immutable `CaseRevision`. A revision that
answered a review carries `AnsweredQuestions`: the review it answered and, per answer, the `Q-n`
it responds to, the `CaseField` the answer belongs in, and the raw text. Skipped questions are
absent rather than flagged (ADR 0012).

## The atlas: observed structure

An `Atlas` is one immutable `AtlasVersion` plus nodes, edges, metric profiles, obscurity signals
and module facts. The version captures the content fingerprint, the git identity, the parser
version and the analysis configuration at one repository state, so a review pins the exact
evidence it saw. Node ids are stable across analyses while path, kind and qualified name are.

Metrics carry their `MetricNature` and `MetricScope` with them, because a number presented
without what it can and cannot mean is an invitation to over-read it.

`AtlasQueryPlan` and the query types beside it are the read surface: the explorer and the
investigation tools both go through them, so what a model may ask of a repository is a closed
list of validated queries rather than an open door.

## Candidates: what detection found

A `FindingCandidate` is a structural shape derived from the atlas — the `FindingPattern` that
recognised it, the participants involved, what was measured with each measurement's nature and
limitations, the relationships between participants, and what the detection method could not see.

A candidate is N-ary by construction: duplicated knowledge is a fact about a set of modules, and
a type holding one node would discard the finding while appearing to record it. It is explicitly
not a violation — materiality depends on circumstances the static view cannot see, so "this does
not matter here" stays a first-class answer downstream.

`boundary_fingerprint` derives a candidate's run-independent identity from what it *is*: the
detector and the qualified names that participate. Paths, line numbers and measurements are left
out because they churn; anything a model wrote is left out because identity is not prose. The
companion `content_fingerprint` hashes the code under the boundary. **Shape is identity, content
is an input** — a team's opinion about a boundary is not undone by somebody editing it, but its
verdict is.

## The review: one judgement, pinned

A `BoundaryReview` is immutable and pinned to one case revision, one atlas version, one model
identity and one prompt identity. Its `ReviewStatus` decides its shape, and validators enforce
that rather than convention: exactly the two statuses that reached verdicts (`succeeded`,
`awaiting_answers`) carry a report, and the three that did not carry none — a report on a failed
run would be a claim about a repository nothing examined.

- `CandidateVerdict` — what the model made of one candidate: `material`, the reasoning, the
  `PolicyBearing`s that bear on it, an optional `VerdictHinge`, and a recommended response
  present only when material. It carries no identifier the model authored: `candidate_id` is
  copied from the request and each bearing takes its policy identity from the position it
  occupied in the presented corpus. A bearing asserted without saying how is dropped rather than
  recorded as an unexplained flag.
- `VerdictHinge` — what the verdict assumed because *the case* did not state it, and the verdict
  under each answer. The other half of what a verdict rests on: the candidate already says what
  the *method* could not see, and only this half is something the reader can fix. `None` is the
  ordinary answer and is translated from an explicit declaration rather than inferred from a
  blank field.
- `ReviewedBoundary` — a `BR-nnn` reference assigned by the application in detection order, the
  candidate, the verdict and its parts, and `BoundaryExcerpt`s showing the code. A non-material
  boundary carrying a response is rejected: an advisor that always has a next action has not
  answered the question.
- `ReviewOverview` / `OpenQuestion` — themes, a sequence, and the questions the run would need
  answered. A question holds a `Q-n` assigned in presentation order, the unknown, why it matters,
  the `CaseField` an answer belongs in, and the `BR-nnn` values it rests on. Questions are
  consolidated across boundaries, and one resting on no boundary is discarded exactly as an
  ungrounded theme is. They are advisor output and live in the review; an answer enters the case
  only as a user-authored revision (ADR 0011, ADR 0012).
- `RecordedInvestigation` — the lookups the run made before it composed its questions, in order,
  with the stage's closing note, why the looking stopped where it did, and the prompt identity it
  ran under. This is what makes a question legible: a question asked because the repository is
  silent and one asked because nobody looked are different questions.

Deliberately absent: design forces, alternatives, scenario analysis, an ADR, an implementation
sequence. A review judges boundaries that already exist rather than weighing competing designs.

## The delta: what one revision changed

`domain/delta.py` is the rule that makes the ninth revision readable by someone who read the
eighth. Every boundary lands in exactly one `BoundaryState` against the branch's previous
revision:

- **carried** — the inputs identity is unchanged, so the verdict, the standing and the silence
  carry. No model call, and no question may be asked about it.
- **judged** — new, or something it rests on moved: its own source, the case, the policy corpus,
  the model, the prompt (`JudgedBecause` says which). Only these may earn an elicitation question,
  which is what makes re-asking a settled question structurally impossible rather than cached
  away.
- **succeeded** — the shape moved and was matched to one that disappeared, so the standing carries
  across wearing a visible mark. Succession matching is a pure function of two sets of shapes.
- **addressed** — present before, matched by nothing now: the loop closing. Nothing is deleted, so
  a fingerprint that comes back resurfaces with its history.

`RevisionDelta` is the counted form, stored on the review because it is a fact about two immutable
revisions. `BoundaryLineEvent` is the append-only record of successions, closures and
resurrections on a branch.

`CachedVerdict` and `verdict_cache_key` are the other side of the same rule. The key is the whole
question rather than its subject: boundary shape, content, policy-corpus fingerprint, case
fingerprint and revision, model identity, prompt identity. Every component is content-derived and
known before the model is called, so the lookup is free and unconditional. Deliberately outside
the key: `repo_id`, `branch_id`, the atlas version and the review that produced the verdict — the
same structure under the same code and the same question has the same answer wherever it is
found, which is what makes a cached verdict useful to CI.

## Lineage: durable identity

`repository_identity` — the hash of a canonical path — answers "where is this on this machine",
and only that. `RepositoryLineage.repo_id` is the repository itself and `BranchLineage.branch_id`
is one line of work in it, derived from the root commit and the branch name. That is the level at
which humans hold opinions ("on main, this boundary is accepted"), which is why the standing
decisions, the living case and the line of revisions attach here and not to any single run. A
branch records the branch it came from, so a run can read through to its base.

## Triage: what the team decided

A judgement is not a disposition. `StandingDecision` records the team's, with an author, a reason
and the verdict it was taken against, keyed on `(branch_id, boundary_fingerprint)` — never a
review id or a `BR-nnn`, both of which are minted per run. Three states are written down
(`accepted`, `waived`, `parked`); *unreviewed* is absence, because a stored "unreviewed" would
claim somebody decided not to decide. History is append-only: changing a decision appends another,
and the latest by `decided_at` stands. `DecisionComment`s thread on the boundary rather than on a
decision row, because argument routinely precedes the decision it produces.

The invariant the design rests on: nothing in the review pipeline reads this module. The model
judges; the team disposes.

## Policies

`PolicyDocument` preserves the authored metadata, the applicability subject and the original
Markdown, and is what every stage is shown — whole, never chunked or ranked.
`PolicyApplicabilityContext` identifies the current user, organisation and repository subjects;
scope resolution fails closed for a scoped policy whose subject does not match, and missing
identity never widens access. `PolicySourceRegistration` records a workspace source by path; the
documents themselves are re-read per request rather than stored.

## Conversations

A `ReviewConversation` is append-only and pinned to one review and, through it, to the exact case
revision the verdicts were reached against. Each turn presents the whole review, so there is no
retrieval plan to validate, no cumulative budget to spend and no rolling summary to revise. A
`ReviewAnswer` marks supporting boundaries by position and the application resolves those into
`supporting_references`; `grounded` is derived from that list rather than asked for. A
`ReviewMessage` carries exactly one of an answer or a failure, and a turn that produced nothing is
still appended — silently discarding it makes the conversation read as though the question was
never asked. A message may also carry its own `RecordedInvestigation`.

## What used to be here

The consultation era's vocabulary was removed rather than deprecated, per ADR 0002, and its
storage went with migration 010. Gone: `ConsultationRun`, `ConcernCluster`, `FocusedAnalysisPacket`
and `ConcernAnalysis`; the claim taxonomy and `SupportedStatement`; `RecommendationDisposition`;
`FollowUp` and the report-conversation types. `PolicyChunk`, `PolicyIndexVersion`,
`RetrievedPolicy`, `PolicyEvidenceSummary` and `PolicyConflict` went with the retrieval index
(migrations 017 and 020) — a review now records what it was *shown* instead: `policies_presented`
names every policy the judging stage saw, and a `PolicyBearing` says which of them bore on one
boundary and how. `FailureDiagnostic` was the last of that vocabulary and left with migration 033;
the baseline types (`BaselineEntry`, `BoundaryDisposition`) left with it, retired in favour of the
delta rule above.
