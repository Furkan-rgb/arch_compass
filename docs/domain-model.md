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
discovery returns content and receives application-generated IDs. Clustering sees only
request-local constrained handles (`F1` through `Fn`); ArchCompass validates exact coverage and
maps them back to the canonical force IDs before constructing domain clusters.

## ConsultationRun

A schema-v3 run records status, the input and optional result case revisions, exact atlas and
policy-index versions, model/config identities, only the prompt identities that executed, forces,
clusters, cluster query plans, focused packets, concern analyses, alternatives, alternative-keyed
scenarios, validation/repair history, stage timings, report, timestamps, and execution metadata.
Successful advice creates exactly the next case revision. A failed run requires a failure stage
and sanitized error, has no result revision, and does not change the case. Safe structured
failure diagnostics may additionally identify missing or repeated request-local force handles;
unknown model references are represented only by a count.

## Canonical findings and report conversations

`ArchitecturalFinding` is the stable, user-addressable unit of report interpretation. New reports
contain one to twelve ordered findings. The workflow assigns `FIND-001` style IDs after synthesis;
each finding records its cluster, contextual importance and rationale, confidence, consequence,
claims, Atlas nodes, policies, affected locations, metric/signal evidence, recommended response,
and uncertainty. The reasoning provider authors meaning, importance, confidence, response, and
claim links. After synthesis or repair, the application projects nodes, locations, metric values,
signals, and policies from that finding's own focused packet, validates cluster coverage, and only
then assigns ordered IDs. Providers cannot introduce altered measurements or evidence from
another cluster.

`ReportConversation` is an append-only aggregate pinned to one successful validated run and its
exact case revision, Atlas version, and policy-index version. `FindingDigest` keeps all ordered
finding identities and qualitative priority available without copying their detailed evidence.
`PinnedCaseSummary` carries the exact revision's title, problem, desired outcome, actors and
workflows, requirements, quality attributes, technical and organisational constraints,
first-class derived constraints, confirmed facts, expected future changes, non-goals, and
assumptions.

An immutable assistant `ConversationMessage` requires a structured `ConversationAnswer`, compact
`ConversationRetrievalRecord`, model identity, and executed prompt identities. Direct answers,
supporting points, and uncertainty are typed answer statements; each factual statement identifies
the answer claims, findings, or report claims that support it. `AnswerClaim` cites exact artifact
identities for nodes, relationships, metrics, signals, and excerpts. Evidence scope is therefore a
property of the cited artifact, not of a whole query result or merely a node ID.

`ReportConversationContext` is a transient reasoning dossier and is not stored in message rows.
It contains no Atlas aggregate, repository root, source tree, full policy corpus, or unlimited
history. A typed `ConversationSummary` retains descriptive narrative plus source-ordinal-linked
user corrections, hypotheticals, unresolved questions, and already-known evidence IDs. Immutable
summary revisions and failed assistant attempts are explicit durable records. See
[report-conversations.md](report-conversations.md).

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
