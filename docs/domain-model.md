# Domain model

## ArchitectureCase

An `ArchitectureCase` is the current immutable snapshot of an architectural decision. It contains
the problem, outcome, actors, workflows, requirements, quality attributes, technical and
organisational constraints, expected changes, non-goals, facts, derived constraints, assumptions,
questions, user-authored design forces, advisor-observed design forces, optional repository
reference, policy-applicability subjects, policy IDs, alternatives, recommendation, confidence,
reversal conditions, revisit triggers, timestamps, and revision.

Case statements have stable IDs, a kind, text, and optional provenance. `CaseUpdate` is partial:
omitted fields are preserved and supplied collections replace their previous value. Each update
creates a complete immutable `CaseRevision`.

New cases use schema version 2. Facts, derived constraints, assumptions, questions, and design
forces are distinct statement collections; validation rejects a statement placed in a collection
with the wrong kind, and user-authored design-force IDs must be unique. A successful consultation
replaces only `advisor_design_forces`.
`design_forces` remains byte-for-byte user intent and is deterministically included in the next
clustering pass. Force ownership is explicit in the schema: a case states its user-authored
and advisor-authored forces in separate fields rather than inferring ownership from a source
string.

## RepositoryAtlas

An `Atlas` contains one immutable `AtlasVersion`, nodes, edges, metric profiles, and objective
signals. Node IDs are stable within and across analyses while path, node kind, and qualified name
remain unchanged. An atlas version captures the content fingerprint, Git identity, parser, and
analysis configuration at one repository state. Atlas and atlas-version outputs use schema
version 2.

## PolicyCorpus

`PolicyDocument` preserves authored metadata, applicability subject, and original Markdown.
`PolicyChunk` represents one semantic section. `PolicyIndexVersion` fixes corpus hash, embedding
provider/model, dimensions, and creation time. `PolicyApplicabilityContext` identifies the
current user, organisation, and repository subjects. Retrieval fails closed for scoped policies
whose subject does not match and returns original documents and chunks, never vectors.
`PolicySourceRegistration` records a canonical persistent workspace source.

`PolicyEvidenceSummary` is report-facing evidence with policy ID, title, scope, applicability
subject, strength, and up to three normalized matched section names. `PolicyConflict` cites at
least two distinct policies and records both the conflict and its reconciliation.

## Concern analysis

A `ConcernCluster` names and explains a group of design-force IDs. One to four clusters must form
an exact partition of the discovered and preserved user forces. A `FocusedAnalysisPacket` carries
one cluster's explicit node evidence and selection reasons, labelled metric observations, resolved
relationship evidence, tests, source excerpts, applicable policies, assumptions, and uncertainty.
Successful runs contain exactly one packet and one `ConcernAnalysis` for each cluster.

The Ollama boundary does not ask a model to create or reproduce these internal IDs. Force
discovery returns content and receives application-generated IDs.

## FindingCandidate

A structural shape derived from an `Atlas`, carrying the participants involved, what was
measured with each measurement's nature and limitations, the relationships between the
participants, and what the detection method could not see.

A candidate is N-ary by construction. Duplicated knowledge is a fact about a set of
modules, and a type holding one node would discard the finding while appearing to record
it. It is explicitly not a violation: materiality depends on circumstances the static view
cannot see, so "this does not matter here" stays a first-class answer downstream.

## CandidateVerdict

What the model made of one candidate: `material`, the reasoning, the policies that bear on
it, and a recommended response present only when material.

The verdict carries no identifier the model authored. `candidate_id` is copied from the
request, and each `PolicyBearing` gets its policy identity from the position it occupied in
the presented corpus. A bearing asserted without saying how is dropped rather than recorded
as an unexplained flag.

## BoundaryReview

An immutable review pinned to one case revision, one atlas version, and the exact prompt
identity that produced it. A succeeded review carries its report; a failed one carries
diagnostics and no report, and both invariants are enforced by validators rather than
convention.

`BoundaryReviewReport` holds the case title, the problem and desired outcome, the policies
presented, and every `ReviewedBoundary` examined. `reviewed` may be empty: the detector ran
and found no candidate, which is a result rather than a failure.

`ReviewedBoundary` carries a `BR-nnn` reference assigned by the application in detection
order, the candidate, the verdict, the reasoning, the policy bearings, and a recommended
response. A boundary that is not material carrying a response is rejected — an advisor that
always has a next action has not answered the question.

Deliberately absent: design forces, alternatives, scenario analysis, an ADR, an
implementation sequence. A review judges boundaries that already exist rather than weighing
competing designs, so there is nowhere to put those and nothing to invent to fill them.

## ReviewConversation

An append-only aggregate pinned to one review and, through it, to the exact case revision
the verdicts were reached against.

Each turn presents the whole review — roughly 25,000 characters — so there is no retrieval
plan to validate, no cumulative budget to spend and no rolling summary to revise. The
answer marks supporting boundaries by position, and `ReviewAnswer.supporting_references`
holds the `BR-nnn` values the application resolved from those positions. `grounded` is
derived from that list rather than asked for.

A `ReviewMessage` carries exactly one of an answer or a failure. A turn that produced
nothing is still appended: silently discarding it makes the conversation read as though the
question was never asked.

## Claims

Every important claim is one of:

- confirmed user requirement;
- derived constraint;
- repository observation;
- policy guidance;
- scenario assumption;
- advisor inference.

Repository observations require surfaced exact Atlas artifacts. Policy guidance requires IDs
retrieved for the relevant cluster. Brownfield locations must use the artifact's exact path and
an ordered, in-range source span. Relationships, metric values, signal observations, and source
excerpts are validated by their complete persisted identity rather than accepted because their
node ID happens to be known.

Substantive report prose is a `SupportedStatement`: text, a claim classification, and supporting
claim IDs. It is used for the decision, architecture, responsibility allocation, conceptual
interfaces, blast-radius conclusion, trade-offs, implementation steps, reversal conditions,
revisit triggers, and ADR decision/consequences. `RecommendationDisposition` separately records
whether advice introduces a boundary, moves responsibility, keeps behavior local, delays,
preserves, or gathers information.

Pydantic models reject unknown fields and validate the current schema only. Reports and runs
declare schema version 3 explicitly: the field is required, so a payload that omits it fails
validation instead of being reinterpreted as an earlier shape. Migration heuristics never run
against live model output, and findings are authored evidence that is never synthesized from
claims. Rows written by an earlier, unreleased schema are reported through
`UnreadableStoredRecordError`, which names the record and asks for the consultation to be re-run.
