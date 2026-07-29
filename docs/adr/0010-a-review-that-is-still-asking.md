# ADR 0010 — A review that is still asking is not a finished review

**Status:** Accepted
**Date:** 2026-07-28
**Amends:** master plan §6C.2, §6C.5; adds §6C.6
**Supersedes:** the "value first, questions after" ordering in ADR 0009
**Related:** ADR 0009 (elicitation and decision moments), ADR 0002 (no shims for superseded schemas)

## Previous direction

ADR 0009 shipped elicitation as one review that reports its verdicts and then asks. The
ordering was deliberate and the argument for it was good: a review that opens by demanding a
better case has put its price ahead of its value, which is the adoption tax elicitation
exists to remove. So the questions went last, addressed to a reader who had already seen
what the review was worth.

## What measurement showed

The argument assumed the first pass was worth something. It largely was not.

`eval/cases/warehouse-sync` judged with no case, then re-judged against answers to its own
questions, against the same repository, atlas and model:

| boundary | pass 1 (no case) | pass 2 (answered) |
|---|---|---|
| `sync.ports.WarehouseFeed` | should change | leave as is |
| `sync.ports.StockLedger` | leave as is | leave as is |
| `reporting.digest.BATCH_SIZE` | leave as is | **should change** |
| `reporting.digest.RETRY_LIMIT` | should change | leave as is |
| `warehouse.northwind` | leave as is | **should change** |

**Four of five verdicts moved.** Those first-pass verdicts were rendered with the same
unconditional labels a settled verdict wears — "Earning its place", "Separate concerns" —
because `_VERDICT_LABELS` has exactly two states per pattern and both are definitive. The
page was reporting, confidently, conclusions with roughly a one-in-five survival rate.

Two further observations rule out the softer fixes:

- **The hinge does not predict movement.** `WarehouseFeed` carried no hinge and moved;
  `StockLedger` carried one and held. So "show the verdicts that admitted no contingency"
  is not a sound partial reveal — the model's hinge discipline is not good enough to
  underwrite it, and this is measured rather than assumed.
- **The record lied for ever.** A first pass was stored as `succeeded`, so a run holding
  questions nobody had answered read as a finished review in every listing, indefinitely.

## New direction

A review is **two passes across two records**, drawn to the reader as one journey: sweep,
judge, ask, *answer*, write the case, judge again, conclude.

It cannot be one record. A review is immutable and pinned to one case revision, and the
second pass judges a different one — the revision the answers created. So the second names
the first in `elicited_from`, and that link is stored rather than inferred: revising a case
by hand also produces a newer review of the same case, and the old heuristic ("is there a
newer review?") would have read that as the questions having been answered.

**`awaiting_answers` is a fifth review status,** on the reasoning that made `cancelled` its
own status rather than a flavour of `failed`: it is a different outcome, and a listing that
showed the two alike would have readers acting on provisional verdicts. It is terminal.
Nobody is obliged to answer, and a record that says "still waiting" a year later is the
truthful account of a question nobody came back to. Answering does not move it — it produces
a second review beside it.

**Asking gets its own stage.** `elicit_questions` replaces the question half of
`summarise_review`, whose contract loses `open_questions` entirely. Two reasons, and the
second is the important one:

- A first pass usually runs against a case that says nothing, so the conclusion half of that
  reply was being composed out of silence and discarded by the second pass — a model call
  spent on a document nobody reads.
- **The summarising stage now has no field in which to ask, which is what terminates the
  loop.** A second pass able to open a fresh round would leave the flow with no ending, and
  stating that as an instruction would leave it to a model to obey. Removing the field means
  a reply carrying a question does not parse.

## What is deliberately *not* changed

- **The order.** Judgement still runs before anything is asked. A question asked before
  looking is generic — *"what are your requirements?"* — and the specific ones are the
  residue of real judgement. §6C.5's ban on an intake interview stands unchanged: what a
  first pass may withhold is its verdicts, never its willingness to look first.
- **The verdict vocabulary.** An earlier reading of this problem proposed a third,
  provisional label set. Once first-pass verdicts stop being presented as findings that
  mostly dissolves, and the per-boundary hinge already states contingency where it survives
  into a concluded review. One vocabulary is kept.

## Consequences

- **Roughly double the model calls**: 2N+2 against N+1. Re-judging only the hinged
  boundaries would halve it and is refused — `WarehouseFeed` is the counterexample.
- **A skip path is required, and is not an equal path.** The waiting page can reveal its
  provisional verdicts under a warning stating the measured movement rate. Revealing
  resolves nothing and the record still says nobody answered. Without it, "answer my
  questions or you get nothing" is the adoption tax in a new shape, charged hardest to the
  reader least able to pay it: someone reviewing unfamiliar code.
- **A waiting review is not a subject for questions.** The conversation service refuses it.
  Its verdicts are exactly the ones the run said it could not settle, so discussing them
  would hand back through a side door the set the page withholds.
- **A waiting review survives a restart.** `abandon_running` targets `running` alone: a run
  waiting on a person has nothing executing, and the wait is precisely what should still be
  there tomorrow.
- **Migration 018** widens the status CHECK and adds the `elicited_from` column. Deleting a
  first pass leaves its second standing with the link cleared — the second pass is a complete
  review with its own case revision, verdicts and conclusion, and neither cascading nor
  refusing the delete would be right.
- **`BoundaryReview.elicited_from` needs no schema bump.** It is an optional field with a
  default, so every stored document still parses; ADR 0002 refuses shims for a *narrowed*
  schema, and this widens.
