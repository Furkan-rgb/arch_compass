# Domain model

The public domain consists of focused implementations in `domain/*.py`. All domain records
use frozen stdlib dataclasses, immutable tuples, and explicit constructors. There is no
second `domain/core/` implementation or compatibility re-export layer.

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
  measurements, relationships, detector rationale, and limitations. It is not a violation.
  Its identity is derived from the pattern and the sorted participant names only, so the
  same structural situation keys the same on every run. Measurements, evidence, and
  relationships are deliberately excluded from that derivation: they move under ordinary
  editing, and an identity that moved with them could not anchor a standing decision or a
  line across revisions.
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

### RepositoryAtlas migration boundary

`RepositoryAtlas.nodes`, `edges`, `metrics`, `facts`, and `signals` currently contain
canonical-JSON strings produced by the deterministic analyzer. The canonical encoding is
intentional: it preserves stable fingerprints and the analyzer's complete representation
without importing the existing Pydantic atlas DTO graph into the dataclass domain. Adapters
own encoding and decoding, and consumers must not interpret tuple order as extra meaning.

This is a migration boundary, not the final atlas design. A focused follow-up must choose
one of two directions: introduce typed, immutable atlas domain records, or replace these
collections with a deliberately opaque atlas snapshot value. That choice must preserve
canonical serialization and fingerprint compatibility; this correctness pass does not
redesign the atlas.

## Supporting values

Focused values include `SourceLocation`, `Evidence`, `Measurement`, `Relationship`,
`PolicyBearing`, candidate IDs, verdicts, dispositions, change causes, and retrieval
provenance. Infrastructure records, vectors, model requests, checkpoints, and database rows
never enter the domain.

Three of these carry an explicit epistemic claim, because a judge shown a bare number or a
bare fragment cannot tell what it is looking at:

- `Measurement` keeps `value` numeric alongside `unit`, `definition`, `limitations`, and a
  `MetricNature` of `objective_measurement` or `structural_proxy`. The distinction is the
  point: `dependants_of_abstraction = 0` reads the same for an abstraction nothing uses and
  for one reached only through wiring the parse cannot see, and the two lead to opposite
  verdicts. The value stays numeric rather than pre-formatted because comparing or bucketing
  candidates has to read the number, and a string that must be parsed back is a number that
  has been lost; `display` renders it for a reader.
- `Relationship` names the edge between participants — `source`, `target`, `kind`, and the
  `resolved_by` pass that established it. Endpoints are qualified names rather than atlas
  node IDs, resolved at the one boundary where the atlas is still in hand. A pattern judged
  from participants in isolation is a lint rather than an architectural finding, so this is
  the placement evidence a verdict rests on.
- `Evidence` carries an optional `note` beside its excerpt: a caption about the text rather
  than a line of it, saying when a span was truncated at the ceiling or widened upward to
  pick up a definition's leading comment.

## Boundary conversion

Pydantic validates HTTP payloads, structured model replies, and stored representations.
Adapters resolve model-returned positions against application-owned candidates and policies
before constructing domain values. Validated transport shapes do not become the domain
representation.
