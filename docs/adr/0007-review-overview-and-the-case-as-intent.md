# ADR 0007 — The review overview, and the case as intent only

**Status:** Proposed
**Date:** 2026-07-26
**Amends:** ADR 0006 (the review-centred plan); master plan §5.1, §5.5, §6A, §16, §17
**Related:** ADR 0001 (composed synthesis), ADR 0002 (legacy purge), ADR 0004 (conversation
panel), ADR 0005 (scope of finding evidence)

## Previous direction

A review is a list of boundaries, each with a verdict, and nothing above them. That was a
deliberate reaction to the consultation era: a model-composed twenty-field
`RecommendationReport` that read as authoritative prose while its claims could not be traced
to anything the advisor had actually looked at, and whose identity fields the model itself
supplied. ADR 0006 deleted it rather than repairing it.

The result is honest and hard to read. Six verdicts against six boundaries do not tell a
reader that four of them exist for variation this case rules out — that is one observation
about a repository, and the workspace makes each person assemble it themselves, every time.

The `ArchitectureCase` still carries `current_recommendation`, `confidence` and
`advisor_design_forces`, and `CaseRevision` still admits an `event_type` of `"consultation"`
with an `origin_run_id`. Nothing writes any of them. They are the shape of an advisor that
wrote its conclusions back into the user's own statement of intent.

## New direction

**A review composes an overview from its own verdicts.** One further model call, over the
boundaries the review has just composed plus the case, producing the situation, the themes
that run across boundaries, a recommended sequence, and what the review could not see. It is
part of the same immutable record and is written at the same moment.

The overview is bound by the same rule as everything else (§12.0): it is shown the
boundaries positionally, it cites them by position, and ArchCompass attaches `BR-nnn`
afterwards. Two structural guarantees keep it from becoming the old report:

- **It has no verdict field.** There is no place in its schema to record that a boundary is
  material, so it cannot disagree with a verdict as data — and nothing downstream reads its
  prose as a key.
- **Its analytical statements must cite.** A theme or a step that rests on no boundary fails
  validation. One constrained repair is permitted, as everywhere else; a second failure
  fails the review rather than persisting an ungrounded overview.

**The `ArchitectureCase` is user intent, and only that.** The advisor never writes back into
it. Advisor output lives in the review, where it is pinned to the exact revision, atlas and
policy set that produced it. `current_recommendation`, `confidence`, `advisor_design_forces`,
`CaseRevision.event_type: "consultation"` and `origin_run_id` are therefore removed rather
than repurposed. A case that changes is a new revision authored by a person; a review of it
is a new review.

**There is no `Project` concept.** For brownfield — the only mode in scope — the unit of work
is a case whose `repository` is set, and its reviews are its history. Every review already
pins the pairing exactly. A seventh durable concept would hold no fact the review does not
already hold, and would need persistence, identity and a migration to say it twice.

**Review conversations are plural and durable, which they already are.** Many threads may
hang off one review; each is append-only and stored. This is a surface obligation only: the
domain, the persistence and the routes support it today and the workspace renders the first
thread and no other.

**Batch evaluation runs on the local model, from the CLI.** Scoring every bundled example is
an evaluation artifact, not a browser flow: it is tens of model calls, it is the kind of
long-running fan-out §18 keeps out of the workspace, and metered free-tier providers cannot
serve it. `demo-local` already proves the local model can carry a whole review.

## Why now rather than later

The engine's output is correct and illegible, and that gap is what the product exists to
close — a reader who has to assemble the overview themselves has been handed the same "lost
the overview" problem §3.1 describes. The workspace milestones are finished, so the surface
can carry an overview the moment the engine produces one.

The case's write-back fields are being kept alive by nothing but inertia, and every surface
that touches a case has to decide what to do about them. Removing them now, while the case
form is being built, is cheaper than building the form around fields that are about to go.

## Consequences

- `BoundaryReviewReport.schema_version` becomes 2, with `overview` required. Under ADR 0002
  there are no shims: stored reviews written before this change no longer parse, are reported
  through `UnreadableStoredRecordError`, and must be re-run. This is accepted rather than
  worked around — a review that may or may not have an overview would multiply states on
  every read path from here on.
- A synthesis failure fails the whole review, discarding the verdicts that had already
  landed. All-or-nothing persistence is preserved: either a whole review exists or none
  does. The cost is real (a failure late in a several-minute run wastes it) and is accepted
  because the alternative is a partial record that every reader must then interpret.
- Removing the write-back fields is a schema change and a SQL migration: the
  `origin_run_id` column and the `"consultation"` event type leave the case revision table.
- The reasoning port gains a third stage (`SUMMARISE_REVIEW`) with its own versioned prompt
  contract, and one more model call per review — roughly a seventh more, for a six-boundary
  review.
- The master plan needs a matching revision: §5.1 (the case holds no advisor output), §5.5
  (a review carries an overview), §6A (the path gains a composition stage), §16 and §17
  (what is now current), and the invariant list.
- Greenfield remains out of scope (Phase 4). Brownfield requires a repository in the
  workspace flow, which the schema continues to keep optional.
