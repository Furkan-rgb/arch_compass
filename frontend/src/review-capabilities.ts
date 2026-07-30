/**
 * What a review will let you do at the status it is in, and what to say when it will not.
 *
 * Extracted from the pages for the reason `start-selection.ts` was: the answer to "may this
 * be asked about / deleted" must be checkable without rendering anything. It lived as one
 * exported helper on the review detail page and one inline `status === "running"` on the
 * reviews list, so the same kind of rule was written twice in two spellings, and the second
 * one had no sentence to show a reader at all.
 *
 * Every rule here mirrors a refusal the server already makes. That is the whole contract: no
 * stricter, because a control this module greys out is a surface the workspace would have
 * served; no looser, because a control it allows leads to a 4xx the reader did nothing to
 * earn. Each entry names the guard it mirrors so the pair can be checked by reading.
 *
 * A refusal is a sentence and not a boolean. A disabled control that does not say why is
 * worse than no control: the reader is left to guess whether the feature is broken.
 *
 * There is no `rerun` entry because there is no rerun. The API has no route for it — running
 * a case again is `POST /api/reviews`, which is a new review and is refused at no status —
 * so a gate here would be inventing a rule the server does not have.
 */

import type { ReviewStatus } from "./types";

/** A sentence saying why not, or `null` when the affordance is allowed. */
export type Refusal = string | null;

/**
 * Asking about a whole review.
 *
 * Mirrors `ReviewConversationService._load`, which admits `succeeded` and nothing else for a
 * conversation about a whole review: `running` has no report to ground an answer on, and
 * `awaiting_answers` has one whose verdicts are the very ones the run said it could not
 * settle — the page withholds that provisional set, and a conversation about the review would
 * hand it over through a side door.
 *
 * A conversation about a *single* open question is a different request and stays allowed
 * while holding (§6C.7), which is why the held copy points at it instead of only refusing.
 * The surface for that is the open questions tab, not the ask panel.
 */
const ASK: Record<ReviewStatus, Refusal> = {
  succeeded: null,
  running: "The review is still running — ask once the verdicts are in.",
  awaiting_answers:
    "The verdicts are still held, so there is nothing settled to ask about yet. Answer " +
    "the open questions — or ask about one of them under Open questions.",
  // Failed and cancelled reach the `Unfinished` page before the control renders, so these
  // two share the honest catch-all rather than each getting copy of its own.
  failed: "This review reached no verdicts, so there is nothing to discuss.",
  cancelled: "This review reached no verdicts, so there is nothing to discuss.",
};

/**
 * Deleting a review.
 *
 * Mirrors `SqliteReviewRepository.delete`, which refuses while the run is live: deleting the
 * row a run is holding would have that run fail on its own record when it tries to finish.
 * Every settled status deletes, including the held one — a review nobody intends to answer is
 * exactly the kind a reader wants gone.
 *
 * The copy names cancelling because cancelling is right there: a running row carries its own
 * Cancel button beside the menu this refusal is read in, so it is an instruction the reader
 * can follow rather than a state they have to wait out.
 */
const DELETE: Record<ReviewStatus, Refusal> = {
  running: "The review is still running — cancel it first, or let it finish.",
  awaiting_answers: null,
  succeeded: null,
  failed: null,
  cancelled: null,
};

/**
 * A status that has not arrived yet refuses everything.
 *
 * Not a rule about reviews but about what is known: a control offered before its record has
 * loaded is a control whose gate has nothing to evaluate.
 */
const UNLOADED = "This review has not loaded yet.";

/**
 * A status is a `string` here and not a `ReviewStatus`, because that is what one listing
 * actually carries: `BoundaryReviewSummary.status` is generated as a bare string, the enum
 * having been serialised by value. Taking the wider type keeps the narrowing in this module
 * instead of spreading a cast across the pages that call it.
 *
 * A status this build has never heard of is allowed rather than refused. Guessing would be
 * inventing a rule; the server has the real one and says so in its own words.
 */
function lookup(rules: Record<ReviewStatus, Refusal>, status: string | undefined): Refusal {
  if (!status) return UNLOADED;
  return status in rules ? rules[status as ReviewStatus] : null;
}

/** Why this review cannot be asked about as a whole, or `null` when it can. */
export function ask(status: string | undefined): Refusal {
  return lookup(ASK, status);
}

/** Why this review cannot be deleted, or `null` when it can. */
export function deletion(status: string | undefined): Refusal {
  return lookup(DELETE, status);
}
