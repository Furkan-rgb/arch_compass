# ADR 0006 — The review-centred master plan and workspace

**Status:** Accepted
**Date:** 2026-07-26
**Amends:** master plan (structural revision); adds `docs/workspace-design.md`
**Related:** ADR 0001 (composed synthesis), ADR 0002 (legacy purge), ADR 0004
(conversation panel)

## Previous direction

The master plan carried both eras at once. The consultation path — clustered findings,
focused packets, policy retrieval, the twenty-field recommendation contract — was marked
"superseded by §6A" in place but remained the bulk of the document, and two of the five
durable domain concepts (`ConsultationRun`, `ReportConversation`) described artifacts
that no longer exist server-side. §16's "Remaining" list named work (the conversation
layer, the web review view, the bundled-case picker) that had since shipped, and Phase 1
of the development sequence described concern clustering the review path deleted.

The workspace had no direction document at all. `docs/web-workspace.md` describes the
implementation and itself mixes eras — it both documents the shipped question dock and
states that V1.2 ships no conversation UI. The frontend reflects the same drift: pages
organised as noun peers, dead links into consultation-era routes, ~1,250 unrouted lines,
and no way to author the case — the one input the product depends on most — in the
browser.

## New direction

**The master plan describes one era.** Superseded sections are removed rather than kept
marked in place; git history holds them. The plan now states the advisory path as two
independent rails — deterministic structure and user-authored intent — converging on
per-candidate judgement, with the review page and its conversation named as part of the
path rather than a viewer after it. The durable concepts become six: `ArchitectureCase`,
`RepositoryAtlas`, `PolicyCorpus`, `FindingCandidate`, `BoundaryReview`,
`ReviewConversation`. Section numbers cited from code and tests (§3.1, §4.1, §6A, §8A,
§12.0) and the invariant numbering cited from ADRs (13, 14, 16) are preserved; §6 and §8
stay vacant so `6A`/`8A` keep meaning what the citations say they mean.

**The workspace gets a governing rule and a direction document.** Master plan §6B states
the rule — the navigation is the flow; a surface earns primary navigation only as a step
of the review flow or a library it reads from — and `docs/workspace-design.md` argues it
in full: Home as the flow's front door, the two rails as the start step (absorbing the
Cases and Repositories pages), a visible per-boundary run, the review page as the centre
of gravity, and the atlas held to its three roles (substrate, evidence, parked explorer
that re-enters from findings).

**The milestone changes accordingly.** §16 becomes the review-centred workspace,
sequenced subtraction-first. The second detector and greenfield candidates remain next
in line, deliberately after it.

## Why now rather than later

The engine finished crossing eras before its documentation and surface did. Every reader
of the old plan had to reconstruct which half of the document was real — the same
"lost the overview" failure the product exists to prevent, reproduced in its own
direction document. And the workspace's gaps are not cosmetic: a flow whose case rail
requires a CLI detour cannot demonstrate the product's central claim, that the case is
what separates a justified boundary from an unjustified one.

## Consequences

- Citations of removed sections (§6, §7, §11, §13, old §16 mandates) in ADRs 0001–0005
  and `docs/plans/` remain historical records against the plan as it stood; those
  documents are already marked historical where they are superseded and are not
  rewritten.
- `docs/web-workspace.md` continues to describe the current implementation and is
  updated milestone by milestone as `docs/workspace-design.md` lands; its
  consultation-era passages fall out with workspace milestone 1 (subtraction).
- `.agents/AGENTS.md` still uses consultation-era names (`ConsultationRun`,
  `application/synthesis.py`) for rules whose mechanics survive in the review era. It
  needs a matching revision; until then, where it and the master plan disagree, the
  master plan governs (its own precedence rule 1).
- A new non-goal is recorded: no job queue or background-execution infrastructure for
  reviews. Visible run progress is a presentation obligation, not an infrastructure
  project.
- Invariant 22 promotes §12.0's division of labour to the invariant list; invariants 5,
  6, 9, 10 and 21 are restated in review-era terms at their existing positions.
