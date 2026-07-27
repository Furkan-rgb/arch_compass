# ADR 0009 — Elicitation, and a sequence ordered by decision moments

**Status:** Accepted
**Date:** 2026-07-27
**Amends:** master plan §5.5, §6A, §15–§17, §19; adds §6C
**Related:** ADR 0007 (the review overview, and the case as intent only)

## Previous direction

The case is authored before the first review. Everything downstream is honest about what
that buys — a run against *"SMS ships next release"* and one against *"feature freeze"*
reach opposite verdicts on identical code — but the effort precedes the value: a new user
must write `expected_future_changes`, `non_goals` and `confirmed_facts` before the
advisor has shown them anything. The development sequence then ordered the remaining work
by engine completeness: greenfield candidates, decision lifecycle, agent integration,
diff analysis, memory, languages.

Two observations argued against leaving it there.

First, the case is the product's differentiator and its adoption tax for the same
reason — judgement is conditioned on stated intent — and a tool whose effort precedes its
value does not get adopted, however good the verdicts are.

Second, advice changes an action at the moment the action is taken, and in software
there are two such moments: a pull request is open, or a coding agent is about to write
code. A whole-repository review read outside any decision has no natural slot in a
working week. It remains the demonstration and the evaluation harness; it is not, by
itself, the product.

## New direction

**Elicitation (master plan §6C).** A review may run against a thin case. Two response
contracts are extended and no stage or model call is added:

- The per-candidate judgement gains a **hinge** between the rationale and the verdict:
  the circumstance the verdict assumed because the case did not state it, and which way
  the verdict moves under each answer. "No hinge" is stated explicitly. Reasoning-first
  field order (§12.0) is preserved — a hinge is part of the argument, so it precedes the
  conclusion that rests on it.
- The overview, which already reads the whole set and already owes "what the review
  could not see", gains **open questions** consolidated from the hinges. Each question
  states the unknown, then which boundaries turn on it — cited by position — then the
  question itself, then the case field the answer belongs in, chosen from a closed enum.
  A question citing no boundary is discarded; a citation to an unknown position fails
  validation with the standard single repair round. `Q-n` identity is assigned by the
  application in presentation order.

Questions live in the immutable review. Answers are **user-authored case revisions**
through the existing revise-and-review loop, shown to the user before they are saved.
The rule, now invariant 25: the advisor supplies the question, the user supplies the
answer, and only the answer enters the case. The case accretes from use instead of being
authored up front, which turns the cold-start problem into the onboarding mechanic.

**A sequence ordered by decision moments (§17).** Elicitation is the current phase.
Then: greenfield candidates (§4.1, which elicitation makes practical — a greenfield case
starts thin by definition); diff-scoped review (the pull-request moment, where cost is
bounded by the change and a boundary is judged once, when it is introduced); a
coding-agent MCP surface composing the two (consult a proposed boundary before the code
exists, review a diff after); then decision lifecycle and longitudinal memory, which
only pay once the advisor is in the loop; and additional languages last.

## Why now rather than later

The engine and its workspace are complete enough that the binding constraint has changed
shape: it is no longer what the advisor can see, but what a new user must do before the
advisor shows them anything. Elicitation removes that constraint with the smallest
possible change — two schema extensions on calls that already run, an answer path on a
loop that already exists — and every later phase benefits from it: a greenfield case, a
PR review and an agent consultation all begin thin.

## Consequences

- The judgement response contract gains the hinge field; its versioned prompt contract
  is revised, and the deterministic providers gain hinge fixtures so `make check` covers
  the path without a model.
- The overview response gains open questions. `BoundaryReviewReport.schema_version`
  becomes 3, `open_questions` required. Under ADR 0002 there are no shims: stored
  version-2 reviews no longer parse, are reported through `UnreadableStoredRecordError`,
  and must be re-run.
- The review page and the CLI gain the question surfaces: questions rendered beside the
  boundaries they cite, an answer composing a case revision the user confirms before it
  is saved.
- A case revision may record which review and question it answers. This is not
  `origin_run_id` returning: that field (removed by ADR 0007) marked revisions authored
  by a run, where this pointer marks a revision the user authored and records what
  prompted it.
- §18's non-goals are unchanged. Elicitation adds no pull-request comments, no
  monitoring and no new model calls; the diff and agent phases remain future work and do
  not license building toward them early.
- Invariant 25 is added; §15 and §16 are refreshed to the delivered detector catalogue
  (three detectors, three scored examples) as part of the same revision.
