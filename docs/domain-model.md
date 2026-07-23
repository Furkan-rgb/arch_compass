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

## RepositoryAtlas

An `Atlas` contains one immutable `AtlasVersion`, nodes, edges, metric profiles, and objective
signals. Node IDs are stable within and across analyses while path, node kind, and qualified name
remain unchanged. An atlas version captures the evidence at one repository state.

## PolicyCorpus

`PolicyDocument` preserves authored metadata and original Markdown. `PolicyChunk` represents one
semantic section. `PolicyIndexVersion` fixes corpus hash, embedding provider/model, dimensions,
and creation time. Retrieval returns original documents and chunks, never vectors.

## ConsultationRun

A run records the input case revision, optional atlas and policy-index versions, model and prompt
identities, forces, query plans, focused packets, alternatives, scenarios, validation outcome,
report, timestamps, and execution metadata. Successful advice creates a new case revision with
the recommendation. Failed evidence validation records a failed run and does not change the case.

## Claims

Every important claim is one of:

- confirmed user requirement;
- derived constraint;
- repository observation;
- policy guidance;
- scenario assumption;
- advisor inference.

Repository observations require surfaced atlas node IDs. Policy guidance requires IDs retrieved
for the run. Pydantic models reject unknown fields.

