/**
 * The review page with no verdicts to show: the run ended without one, or the review itself
 * is gone. Two screens rather than one because their recoveries differ, kept together
 * because they are the same page drawn around an absence — and they say so in the same voice.
 */

import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { ApiError } from "../../api";
import { ErrorPanel, PageHeader, formatDate, page, sheet, shortId } from "../../components";
import type { BoundaryReview } from "../../types";

const unfinishedNote = "m-0 text-body leading-[1.6] text-ink-2";

/**
 * A review that ended without a judgement: cancelled, or failed.
 *
 * Not an error page. The row exists from the moment the run starts, so this is what a review
 * page looks like when the run ended and no subject ever will exist. A run still going is a
 * different thing entirely and has its own state; this one is the aftermath.
 */
export function ReviewUnfinished({ review }: { review: BoundaryReview }) {
  const cancelled = review.status === "cancelled";
  return (
    <div data-slot="review-page" className={cn(page, "pb-6")}>
      <PageHeader
        title={cancelled ? "This review was cancelled" : "This review did not finish"}
        parent={{ to: "/reviews", label: "Reviews" }}
        meta={<Badge>case rev {review.case_revision}</Badge>}
      />
      <div className={cn(sheet, "grid max-w-[76ch] gap-3.5 p-[var(--card-pad)]")}>
        {/* Cancelling records no reason, because there is none to record beyond the choice
            itself. Only what ArchCompass wrote for a person to read reaches this list; an
            unexpected failure is recorded without its text. */}
        {cancelled ? (
          <p className={unfinishedNote}>
            It stopped after the boundary it was judging at the time. The verdicts it had
            already reached were not kept: a review is every boundary or none, and half of
            one would read as a complete answer.
          </p>
        ) : (
          <ul className="m-0 grid gap-2 rounded-panel border border-danger-rule bg-danger-soft py-4 pr-4 pl-8 text-body leading-[1.55] text-danger">
            {(review.sanitized_errors || []).map((message) => (
              <li key={message}>{message}</li>
            ))}
            {(review.sanitized_errors || []).length === 0 ? (
              <li>No reason was recorded.</li>
            ) : null}
          </ul>
        )}
        <p className={unfinishedNote}>
          Nothing was written to the case or the atlas. A review is derived from both, so
          running it again is the whole of the fix. Started {formatDate(review.created_at)} ·
          case <code>{shortId(review.case_id)}</code> · <Link to="/start">Start a review</Link> ·{" "}
          <Link to="/reviews">All reviews</Link>
        </p>
      </div>
    </div>
  );
}

/**
 * The page with its subject missing: deleted, or unreadable.
 *
 * It exists because a review can go while someone is reading it — deleting one from the
 * reviews list in another tab is the ordinary way that happens — and what this page did then
 * was put a red strip on an empty canvas, with no header, no column and no link anywhere. A
 * reader who had followed a link into a review they no longer had was left with the back
 * button as the only way on.
 *
 * The two cases are told apart because their recoveries are opposites. A 404 is settled: the
 * record is gone, asking again asks for the same nothing, and the only useful thing left to
 * offer is the list it came out of. Anything else might be the network, so it gets the second
 * attempt and keeps the reader where they are.
 *
 * Neither is dressed up. The server's own words stay in the strip; the sentence under it says
 * what is known and nothing more — in particular it does not claim the review "may have been
 * deleted" when the reason is a timeout, or promise anything about getting it back.
 */
export function ReviewUnavailable({
  reviewId,
  error,
  onRetry,
  retrying,
}: {
  reviewId: string;
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const gone = error instanceof ApiError && error.status === 404;
  return (
    <div data-slot="review-page" className={cn(page, "pb-6")}>
      <PageHeader
        title={gone ? "This review is no longer here" : "This review could not be read"}
        parent={{ to: "/reviews", label: "Reviews" }}
      />
      <div className={cn(sheet, "grid max-w-[76ch] gap-3.5 p-[var(--card-pad)]")}>
        {/* Nothing to retry on a review that has been deleted: the request would succeed at
            fetching the same absence, and a control that cannot change its own outcome is
            worse than no control. */}
        <ErrorPanel
          error={error}
          onRetry={gone ? undefined : onRetry}
          retrying={retrying}
          retryLabel="Read it again"
        />
        <p className={unfinishedNote}>
          {gone ? (
            <>
              Reviews are deleted from the reviews list, and deleting one is permanent — it
              may have gone from another tab while this page was open. Nothing else was
              affected: the case it judged and the atlas it ran against are both untouched,
              and every other review is where it was.
            </>
          ) : (
            <>
              Nothing has been changed by this — reading a review only reads. If it keeps
              failing, the review may still be readable from the list.
            </>
          )}
        </p>
        <p className={unfinishedNote}>
          <Link to="/reviews">All reviews</Link> · <Link to="/start">Start a review</Link> ·{" "}
          <code>{shortId(reviewId)}</code>
        </p>
      </div>
    </div>
  );
}
