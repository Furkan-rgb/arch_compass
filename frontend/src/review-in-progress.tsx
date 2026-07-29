import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Square } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "./api";
import { ErrorPanel, formatDate, shortId } from "./components";
import { RunProgress, type RunState } from "./run-progress";
import type { BoundaryReview, BoundaryReviewSummary } from "./types";

/**
 * A review being produced, wherever it is being watched from — the only such surface.
 *
 * There used to be two: the start step drew a run it owned, and the review's own page drew
 * a thinner version of the same thing from polled counts. Two renderings of one fact drift,
 * and the reader has to work out which of them to believe. So this is the component, and
 * the review's page is the place: starting a run goes there as soon as the stream says what
 * the review is called.
 *
 * It reads from whichever source knows more. The browser holding the stream has the
 * boundary names and each verdict as it lands; any other browser — a second tab, a reload,
 * a run started from the CLI — has the counts the run writes to its own record. Both are
 * the same run, and the panel says which of the two it is looking at rather than pretending
 * the thinner one is complete.
 */

/** The record's own counts, as the shape the flow already draws. */
export function progressFromSummary(
  summary: BoundaryReviewSummary | undefined,
): RunState {
  if (!summary || summary.boundaries_detected === null) return null;
  const total = summary.boundaries_detected ?? 0;
  return {
    total,
    // No names: the detected order is known only to the run that swept for them, and
    // inventing labels here would be presenting a guess as evidence.
    boundaries: [],
    verdicts: Array.from({ length: total }, () => null),
    judged: summary.boundaries_reviewed,
    // Which of the two set-wide calls is running is not in the counts — the record knows
    // only that every verdict has landed. It is reported as the one this pass will make,
    // which the row does know: a run that names the pass it answers concludes, and one that
    // does not asks.
    eliciting: total > 0 && summary.boundaries_reviewed >= total && !summary.elicited_from,
    summarising:
      total > 0 && summary.boundaries_reviewed >= total && Boolean(summary.elicited_from),
  };
}

/** Whichever source knows more about the same run. */
export function watchedProgress(
  live: RunState | undefined,
  summary: BoundaryReviewSummary | undefined,
): RunState {
  if (live) return live;
  return progressFromSummary(summary);
}

export function ReviewInProgress({
  review,
  summary,
  live,
  watching,
  title,
}: {
  review: BoundaryReview;
  summary: BoundaryReviewSummary | undefined;
  live: RunState | undefined;
  watching: boolean;
  title: string | null;
}) {
  const client = useQueryClient();
  // Generated as optional because the server fills it in, but a review that has been
  // begun always carries one — this page was reached by that identifier.
  const reviewId = review.review_id ?? "";
  const cancel = useMutation({
    mutationFn: () => api.cancelReview(reviewId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["review", reviewId] }),
        client.invalidateQueries({ queryKey: ["reviews"] }),
      ]);
    },
  });
  const progress = watchedProgress(live, summary);

  return (
    <div className="page page--review">
      <header className="review-head">
        <span className="eyebrow">Boundary review · in progress</span>
        <h1>{title || <code>{shortId(reviewId)}</code>}</h1>
        <p className="review-head__meta">
          Started {formatDate(review.created_at)} · case revision{" "}
          <strong>{review.case_revision}</strong> · one model call per boundary
        </p>
        {/* Printed while it runs, not only afterwards: what a verdict was reached against
            is as much part of a running review as of a finished one, and a reader deciding
            whether to let it finish is exactly who needs it. */}
        <dl className="provenance">
          <div>
            <dt>Model</dt>
            <dd title={review.prompt_identity}>{review.reasoning_model}</dd>
          </div>
          <div>
            <dt>Atlas version</dt>
            <dd title={review.atlas_version_id}>{shortId(review.atlas_version_id)}</dd>
          </div>
          <div>
            <dt>Watching</dt>
            <dd>{watching ? "live, from this tab" : "the run's own record"}</dd>
          </div>
        </dl>
      </header>

      <div className="in-progress">
        <RunProgress
          progress={progress}
          pass={review.elicited_from ? 2 : 1}
          heading={
            watching ? (
              <>
                This tab is running it. Leaving the page does not stop the run — it carries
                on and this page shows where it got to.
              </>
            ) : (
              <>
                Started elsewhere, so this page follows the run's own record: how far it has
                got, but not the boundary names, which are known to whoever started it.
              </>
            )
          }
        />

        <div className="in-progress__actions">
          <button
            type="button"
            className="button button--stop"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            <Square size={13} aria-hidden fill="currentColor" />
            {cancel.isPending ? "Stopping…" : "Cancel this review"}
          </button>
          <p>
            It stops after the boundary being judged right now, so up to one model call from
            here. The verdicts already reached are not kept: a review is every boundary or
            none. <Link to="/reviews">All reviews</Link>
          </p>
        </div>
        {cancel.isError ? <ErrorPanel error={cancel.error} /> : null}
      </div>
    </div>
  );
}
