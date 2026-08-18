# Domain model

The public domain is a small conceptual facade backed by focused value objects. All domain
records use frozen stdlib dataclasses, immutable tuples, and explicit constructors.

```text
ArchitectureCase                          RepositoryRef
  |                                           |
Question -> Answer                            v
  |                                     RepositoryAtlas
  |                                           |
  +---------------------> Candidate <---------+
                              |
Policy -----------------------+
                              v
                           Finding
                              |
                       StandingDecision
                              |
                              v
                            Review
                              |
                         ReviewDelta
```

## Primary concepts

- `ArchitectureCase` is revisioned human context: goal, categorized constraints,
  contextual decisions, answers, and timestamps. `with_answer()` returns a new revision.
- `Question` has application-owned identity and an equivalence key derived from case facet
  plus sorted supporting candidate IDs.
- `Answer` records answered or skipped status, optional value, actor, and time.
- `RepositoryRef` identifies the repository, branch line, canonical path, optional remote,
  optional branch/commit, and deterministic content identity.
- `RepositoryAtlas` is the deterministic structural analysis result. It is distinct from
  repository identity.
- `Policy` is architectural guidance with identity, applicability, strength, source, body,
  tags, and content hash. It contains no retrieval score.
- `Candidate` is a deterministic structural shape with participants, evidence,
  measurements, detector rationale, and limitations. It is not a violation.
- `Finding` contains the verdict, reasoning, pinned evidence, policy bearings, uncertainty,
  recommendation, reuse provenance, and model/prompt/retrieval identities.
- `StandingDecision` records accept, waive, or park independently from the finding. Waivers
  require reasoning and every decision pins the finding context it answered.
- `Review` is an immutable snapshot linking repository, atlas, case, findings, questions,
  status, delta, report, provenance, lineage, and timing.

`ReviewDelta` records unchanged, changed, new, and addressed candidates. Supporting records
retain causes, predecessor identity, resurfacing, and last-seen provenance. The initial
case-revision strategy rejudges every extant candidate, but that policy is replaceable and
is not a domain invariant.

## Supporting values

Focused values include `SourceLocation`, `Evidence`, `PolicyBearing`, candidate IDs,
verdicts, dispositions, change causes, and retrieval provenance. Infrastructure records,
vectors, model requests, checkpoints, and database rows never enter the domain.

## Boundary conversion

Pydantic validates HTTP payloads, structured model replies, and stored representations.
Adapters resolve model-returned positions against application-owned candidates and policies
before constructing domain values. Validated transport shapes do not become the domain
representation.
