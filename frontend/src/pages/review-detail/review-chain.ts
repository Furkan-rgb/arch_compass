/** Which passes belong to the run a review is one of, and in what order. */

import type { BoundaryReviewSummary } from "../../types";

/**
 * The run this review is one pass of, oldest pass first.
 *
 * Walked in both directions from the review on show: back along `elicited_from` to the pass
 * that asked, and forward to whichever pass answers this one. The listing of the case's
 * reviews already holds both links, so nothing here is guessed — a pass that has been
 * deleted simply ends the walk on that side.
 */
export function chainAround(
  reviewId: string,
  reviews: BoundaryReviewSummary[],
): BoundaryReviewSummary[] {
  const byId = new Map(reviews.map((item) => [item.review_id, item]));
  const current = byId.get(reviewId);
  if (!current) return [];
  const chain = [current];
  let earlier = current.elicited_from ? byId.get(current.elicited_from) : undefined;
  while (earlier) {
    chain.unshift(earlier);
    earlier = earlier.elicited_from ? byId.get(earlier.elicited_from) : undefined;
  }
  let later = reviews.find((item) => item.elicited_from === reviewId);
  while (later) {
    chain.push(later);
    const answeredId = later.review_id;
    later = reviews.find((item) => item.elicited_from === answeredId);
  }
  return chain;
}
