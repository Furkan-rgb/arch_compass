# Design: standing decisions and discussion

**Status:** Approved design, implementation in progress. Companion to
`company-readiness.md` §4; this document is the binding design.
**Scope:** The domain object, persistence, API, and interaction design for per-boundary
triage (accept / waive / park) and its discussion thread. No auth: authorship is
self-reported until identity exists (`company-readiness.md`, deferred list).

## Placement in the architecture

A standing decision is a **new aggregate**, not a change to any existing one.
`BoundaryReview` stays immutable; `ArchitectureCase` stays about intent; the decision
records the team's disposition toward a structural state of the repository. It therefore
keys on `(branch_id, boundary_fingerprint)` — the branch lineage from
`company-readiness.md` §1 and the structural fingerprint from §2 — never on a review id
or a `BR-nnn` reference, both of which are per-run.

**The one invariant that must survive every future change:** `ReviewService` never reads
the decisions repository. Decisions are joined onto review data in the presentation
layer only. The model judges; the team disposes; neither can contaminate the other.

## Domain model

New module `domain/triage.py`:

- `DecisionState` (StrEnum): `accepted`, `waived`, `parked`. Absence of any decision is
  the fourth state, *unreviewed*, and is represented by absence — no row, no enum value.
- `StandingDecision` (DomainModel): `decision_id` (`new_id("dec")`), `branch_id`,
  `boundary_fingerprint`, `state`, `author` (free text, min 1 char), `reason`
  (**required when `state == waived`**, optional otherwise — a waiver without a reason
  is noise wearing a uniform), `decided_at`, and the **verdict context** it was taken
  against: `review_id`, `boundary_reference` (the BR-nnn in that review), `material`,
  `verdict_label`. The context pins what the human actually looked at; when a later
  run's verdict differs from the context, the UI can say so.
- `DecisionComment` (DomainModel): `comment_id` (`new_id("dcom")`), `branch_id`,
  `boundary_fingerprint`, `author`, `body`, `created_at`.

Decision history is **append-only**: changing a decision appends a new
`StandingDecision` row; the latest by `decided_at` (tie-broken by rowid) is current.
Comments thread on the *boundary* (`branch_id + fingerprint`), not on a decision row —
argument can precede any decision, and the thread survives decision changes. No edits,
no deletes, matching `review_conversation` discipline.

## Persistence

One migration (`standing decisions and their discussion`):

- `standing_decisions`: columns for both key parts, `state`, `author`, `reason`,
  `decided_at`, the four context columns, plus `decision_json` holding the aggregate —
  the hybrid pattern used everywhere else.
- `decision_comments`: key parts, `author`, `created_at`, `comment_json`.
- Indexes on `(branch_id, boundary_fingerprint)` for both.

New `SQLiteStandingDecisionRepository` (`append_decision`, `current_for_branch` — latest
decision per fingerprint, `history`, `append_comment`, `comments_for`), port protocol in
`ports/repositories.py`, wired through `bootstrap.Runtime`.

## API

- `GET /api/branches/{branch_id}/decisions` — current decision per fingerprint, with
  comment counts.
- `POST /api/decisions` — body: branch_id, boundary_fingerprint, state, author, reason,
  verdict context. Appends; returns the new current decision. Refuses a waive without a
  reason with a field-level validation error.
- `GET /api/decisions/{branch_id}/{fingerprint}/history` — full decision history.
- `GET`/`POST /api/decisions/{branch_id}/{fingerprint}/comments` — the thread.
- Review detail (`GET /api/reviews/{id}`) response gains, per reviewed boundary, a
  `fingerprint` and an optional joined `decision` (current state, author, decided_at,
  reason, `taken_on_current_verdict: bool` — false when the stored context's
  material/label differs from this run's). Join happens in the web layer.

## Interaction design (summary — built in the frontend phase)

- Each ledger row's expanded detail gains a **disposition footer**: three quiet segmented
  controls (Accept · Waive · Park), an author field that remembers its last value
  (localStorage), a reason field that becomes required and focused when Waive is
  selected. Submitting renders the decision line in place: "Waived by Deniz ·
  2026-08-04 — intentional seam for the billing split."
- The collapsed row carries a **decision tick**: a small neutral badge (state word only)
  after the verdict chip. Unreviewed rows carry nothing — silence is the unreviewed
  state, and the filter bar gains an "Unreviewed" filter to find it.
- A decision whose stored verdict context no longer matches the current run's verdict
  renders with an attention rule and the sentence "Decided against an earlier verdict —
  review again." It does not auto-expire; re-affirming is a human act.
- **Discussion** is a disclosure under the disposition footer ("Discuss this boundary"),
  an append-only thread with author + body, newest last, `aria-live="polite"` on append.
- All controls keyboard-first; the segmented control is a `role="radiogroup"`; the
  decision badge is text, not colour alone.

## What this deliberately does not do

- No decision ever blocks, suppresses, or re-weights a verdict. Baseline (§3 of the
  plan) controls what CI surfaces; decisions record judgement about what it surfaced.
- No auth, no roles, no notifications. The author field is honest self-report; the
  schema needs zero migration when identity arrives (author becomes a validated value).
- No cross-branch propagation in V1. Merging a PR branch's decisions into the base
  branch is the manual "adopt" action named in the plan, built with the CI phase.
