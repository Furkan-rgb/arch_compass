# Domain model

## ArchitectureCase

An `ArchitectureCase` is the current immutable snapshot of an architectural decision. It contains
the problem, outcome, actors, workflows, requirements, quality attributes, technical and
organisational constraints, expected changes, non-goals, facts, derived constraints, assumptions,
questions, design forces, optional repository reference, policy IDs, alternatives,
recommendation, confidence, reversal conditions, revisit triggers, timestamps, and revision.

Case statements have stable IDs, a kind, text, and optional provenance. `CaseUpdate` is partial:
omitted fields are preserved and supplied collections replace their previous value. Each update
creates a complete immutable `CaseRevision`.

New cases use schema version 2. Facts, derived constraints, assumptions, questions, and design
forces are distinct statement collections; validation rejects a statement placed in a collection
with the wrong kind.

## RepositoryAtlas

An `Atlas` contains one immutable `AtlasVersion`, nodes, edges, metric profiles, and objective
signals. Node IDs are stable within and across analyses while path, node kind, and qualified name
remain unchanged. An atlas version captures the content fingerprint, Git identity, parser, and
analysis configuration at one repository state. Atlas and atlas-version outputs use schema
version 2.

## PolicyCorpus

`PolicyDocument` preserves authored metadata and original Markdown. `PolicyChunk` represents one
semantic section. `PolicyIndexVersion` fixes corpus hash, embedding provider/model, dimensions,
and creation time. Retrieval returns original documents and chunks, never vectors.
`PolicySourceRegistration` records a canonical persistent workspace source.

`PolicyEvidenceSummary` is report-facing evidence with policy ID, title, scope, strength, and up
to three normalized matched section names. `PolicyConflict` cites at least two distinct policies
and records both the conflict and its reconciliation.

## Concern analysis

A `ConcernCluster` names and explains a group of design-force IDs. One to four clusters must form
an exact partition of the discovered forces. A `FocusedAnalysisPacket` carries one cluster's
explicit node summaries, metric profiles, selected relationships, test IDs, source excerpts,
retrieved policies, assumptions, and uncertainty. Successful runs contain exactly one packet and
one `ConcernAnalysis` for each cluster.

## ConsultationRun

A schema-v2 run records status, the input and optional result case revisions, exact atlas and
policy-index versions, model/config identities, only the prompt identities that executed, forces,
clusters, cluster query plans, focused packets, concern analyses, alternatives, alternative-keyed
scenarios, validation/repair history, stage timings, report, timestamps, and execution metadata.
Successful advice creates exactly the next case revision. A failed run requires a failure stage
and sanitized error, has no result revision, and does not change the case.

## Claims

Every important claim is one of:

- confirmed user requirement;
- derived constraint;
- repository observation;
- policy guidance;
- scenario assumption;
- advisor inference.

Repository observations require surfaced atlas node IDs. Policy guidance requires IDs retrieved
for the relevant cluster. Brownfield repository observations additionally require a source path
and span within the surfaced node.

Substantive report prose is a `SupportedStatement`: text, a claim classification, and supporting
claim IDs. It is used for the decision, architecture, responsibility allocation, conceptual
interfaces, blast-radius conclusion, trade-offs, implementation steps, reversal conditions,
revisit triggers, and ADR decision/consequences. `RecommendationDisposition` separately records
whether advice introduces a boundary, moves responsibility, keeps behavior local, delays,
preserves, or gathers information.

Pydantic models reject unknown fields. Compatibility validators load schema-v1 case, report,
packet, scenario, and run shapes. Legacy report strings are wrapped as explicitly marked legacy
supported statements; all newly produced output uses schema version 2.
