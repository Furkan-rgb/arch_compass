# ADR 0005 — Evidence scope belongs to ownership, and a closed set is a type

**Status:** Accepted
**Date:** 2026-07-25
**Related:** ADR 0001 (composed synthesis), ADR 0003 (derived budgets)

## Context

The first live capture of a real consultation ran nine model calls through the whole
pipeline and produced a bundle under `tests/replay/recordings/`. Replaying it — with no
model running — surfaced two contract defects that the deterministic suite could not,
because a substitute reasoner satisfies whatever the code expects of it.

Both are the same shape: a rule stated in one layer and contradicted in another, with a
repair pass quietly absorbing the difference. That is the brittleness this project has
been removing, and it survives precisely where nothing real exercises it.

## Decision 1 — a claim owned by no cluster is citable from any finding

`build_claim_pool` offers a finding every handle in the pool, including case statements
(confirmed requirements, derived constraints, assumptions). `validate_proposal`
deliberately permits them. But `validate_report_evidence` required every finding claim
to appear in its own cluster's focused packet, so the repair pass stripped them.

The live model cited a confirmed user requirement — *"A provider interface exists but
does not own voice discovery"* — as support for a finding about that exact leakage. The
citation was correct, invited by the schema, and deleted before the report was stored.

Scope is now decided by **ownership rather than absence**:

- a claim owned by *another* cluster is foreign, and still rejected;
- a claim owned by *no* cluster belongs to the consultation, and any finding may rest on
  it.

Cross-cluster contamination — the rule's actual purpose — is untouched. Fabricated IDs
cannot hide in the allowance, because an ID absent from the report's claim registry is
already rejected as unknown before scope is considered. A finding must still cite at
least one claim from its own cluster, so this widens support without weakening grounding.

Rejected: constraining the schema per cluster instead, via a `oneOf` over `cluster_ref`
variants. It would make the stricter rule structural rather than checked, which is the
better shape in the abstract — but it buys that consistency by removing the ability to
ground a finding in the user's own stated requirement, which makes the advice weaker.

## Decision 2 — `DesignForce.importance` is a level, not prose

`ArchitecturalFinding.importance` was already `ImportanceLevel`. `DesignForce.importance`
was `str`, and the discovery prompt asked the model to "explain why each matters now" —
so the model wrote **"Critical: Directly drives the 'Brownfield provider leakage'
problem…"** into a field the UI renders as an uppercase badge and the markdown report
renders as a parenthetical.

The model was not misbehaving. It had one field and two things to say, which is a schema
admitting it is missing a field. `DesignForce` now carries a typed `importance` and a
separate `importance_rationale`, mirroring `ArchitecturalFinding` exactly, and the prompt
directs the reasoning to the field that exists for it.

Two things fall out. The enum, now shared by two concepts, is renamed `FindingImportance`
→ `ImportanceLevel`. And the workflow's synthetic force for user-stated design forces no
longer sets `importance="user-specified"` — a provenance note wearing a level's clothing —
so provenance moved to the rationale and the level says what a level says.

This is the third instance of the same bug class, after `SupportedStatement.legacy`
(ADR 0002) and the free-text recommendation disposition: **a closed set left as free text
is a constraint the schema cannot enforce and the model cannot see.**

## Decision 3 — a surfaced node's own span is projected, not demanded back

Two further captures died in concern analysis: *"Repository finding has an invalid or
unsurfaced source location."* The model had cited a **surfaced** node with
`location: null`, on claims like *"The VoiceProvider interface exhibits high change
amplification, with a structural proxy of 5 likely affected modules."*

That claim is about a node, not a line range. There is no span narrower than the node to
name, and the packet already carries the node's span — so the requirement was asking the
model to reproduce data the application owns, and reading its omission as an unsupported
claim. The constraint also lived only in prompt prose (*"Repository observations require
supplied node IDs and locations"*) while the schema left `location` nullable: the model
was told, and told is not enforced.

A repository observation citing a surfaced node without a span now receives that node's
span, audited as `projected_surfaced_span_for_repository_finding`. What did not change:

- a claim naming a node the packet never surfaced is still unsupported and dropped;
- a span the model *does* supply must still lie inside its node — an omitted location is
  a claim about the node, while a wrong one is a claim of precision the packet does not
  support.

Node membership is what proves a claim is about surfaced code, so that is what is
required. This was not a rare stumble: it killed two of three captures, and the one
success survived only because other claims happened to carry spans.

## Consequences

- The recorded consultation now validates first-pass clean, with zero repair actions.
  Repair firing on a *correct* answer had been polluting the contract-achievability
  signal the quality harness exists to measure.
- Both scope properties — neutral claims accepted, cross-cluster and unknown claims
  rejected — are pinned by deterministic tests, so they do not depend on a recording that
  a re-capture could change.
- The prompt version bump invalidated the existing recording, and the staleness check
  reported it by name and fingerprint rather than replaying an answer produced under
  wording that no longer exists. The mechanism works.
- `config/models.yaml` was raised to 131072/8192 in the same pass. At 32768/16384 only
  16384 tokens remained for input while a focused concern packet runs to ~29k, so the
  committed configuration could not complete a consultation at all.
