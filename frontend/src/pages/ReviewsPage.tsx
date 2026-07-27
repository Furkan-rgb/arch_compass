import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CircleCheck,
  CircleSlash,
  Compass,
  Loader,
  MoreVertical,
  Square,
  Trash2,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  formatDate,
  shortId,
  useDialogFocus,
} from "../components";
import type { BoundaryReviewSummary } from "../types";

/** True while any listed review is still being produced. */
export function anyRunning(reviews: BoundaryReviewSummary[]) {
  return reviews.some((review) => review.status === "running");
}

/**
 * What a row amounts to: the verdict split, or how far a run has got.
 *
 * A running review has no verdict to report, so it reports its position instead. Before
 * detection finishes it cannot even do that — the length is genuinely unknown, and a "0 of
 * 0" would read as a sweep that found nothing rather than one that has not finished.
 */
export function Outcome({ review }: { review: BoundaryReviewSummary }) {
  if (review.status === "running") {
    return (
      <Badge tone="teal">
        <Loader size={13} aria-hidden className="spin" />
        {review.boundaries_detected === null || review.boundaries_detected === undefined
          ? "sweeping the atlas"
          : `judging ${Math.min(
              review.boundaries_reviewed + 1,
              review.boundaries_detected,
            )} of ${review.boundaries_detected}`}
      </Badge>
    );
  }
  if (review.status === "cancelled") {
    // Not shown as a failure. A review nobody wanted any more is not a review that broke,
    // and colouring them alike would have the reader looking for a problem.
    return (
      <Badge tone="neutral">
        <CircleSlash size={13} aria-hidden /> cancelled
      </Badge>
    );
  }
  if (review.status === "failed") {
    return (
      <Badge tone="danger">
        <XCircle size={13} aria-hidden /> failed, nothing judged
      </Badge>
    );
  }
  if (review.boundaries_material > 0) {
    return (
      <Badge tone="warning">
        <TriangleAlert size={13} aria-hidden />
        {review.boundaries_material} of {review.boundaries_reviewed} should change
      </Badge>
    );
  }
  return (
    <Badge tone="success">
      <CircleCheck size={13} aria-hidden />
      {review.boundaries_reviewed === 0
        ? "no boundaries to examine"
        : `all ${review.boundaries_reviewed} left as they are`}
    </Badge>
  );
}

/**
 * What can be done to one row: stop it, or remove it.
 *
 * Outside the row's link rather than inside it. A button nested in an anchor is neither
 * reliably clickable nor announced as its own control, and "delete" is the last action that
 * should depend on a click landing where the reader meant it.
 */
function RowActions({
  review,
  onCancel,
  onDelete,
  busy,
}: {
  review: BoundaryReviewSummary;
  onCancel: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const close = () => {
    setOpen(false);
    setConfirming(false);
  };
  const menu = useDialogFocus(close, open);
  const running = review.status === "running";

  return (
    <span className="row-actions">
      {running ? (
        <button
          type="button"
          className="button button--stop"
          disabled={busy}
          onClick={onCancel}
        >
          <Square size={13} aria-hidden fill="currentColor" /> Cancel
        </button>
      ) : null}
      <span className="row-actions__menu">
        <button
          type="button"
          className="icon-button"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`More actions for the review of ${
            review.case_title || review.review_id
          }`}
          onClick={() => (open ? close() : setOpen(true))}
        >
          <MoreVertical size={16} aria-hidden />
        </button>
        {open ? (
          <span className="row-menu" role="menu" ref={menu as React.Ref<HTMLSpanElement>}>
            {confirming ? (
              <>
                {/* Confirmed in place rather than by a browser dialog: the row being
                    deleted stays visible behind the question, which is the one detail that
                    makes the answer meaningful. */}
                <span className="row-menu__ask">
                  Delete this review? Its question threads go with it.
                </span>
                <button
                  type="button"
                  role="menuitem"
                  className="row-menu__item row-menu__item--danger"
                  disabled={busy}
                  onClick={() => {
                    close();
                    onDelete();
                  }}
                >
                  <Trash2 size={14} aria-hidden /> Delete permanently
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="row-menu__item"
                  onClick={close}
                >
                  Keep it
                </button>
              </>
            ) : (
              <button
                type="button"
                role="menuitem"
                className="row-menu__item row-menu__item--danger"
                onClick={() => setConfirming(true)}
              >
                <Trash2 size={14} aria-hidden /> Delete
              </button>
            )}
          </span>
        ) : null}
      </span>
    </span>
  );
}

/**
 * Every review this workspace has run, kept off the start step.
 *
 * Grouped by case rather than listed flat. Revising a case and reviewing again is the loop
 * this tool is built around, so successive runs of one case are one history: read as a
 * flat list they look like unrelated results, and the reader has to reconstruct which of
 * two reviews came after which revision.
 */
export function CaseHistory({
  caseId,
  title,
  reviews,
  onCancel,
  onDelete,
  busy,
}: {
  caseId: string;
  title: string | null;
  reviews: BoundaryReviewSummary[];
  onCancel: (reviewId: string) => void;
  onDelete: (reviewId: string) => void;
  busy: boolean;
}) {
  return (
    <section className="review-history">
      <header className="review-history__head">
        <h2>{title || <code>{shortId(caseId)}</code>}</h2>
        <span>
          {reviews.length} {reviews.length === 1 ? "review" : "reviews"}
        </span>
      </header>
      <ol className="review-history__rows">
        {reviews.map((review, index) => (
          <li key={review.review_id} className="review-row">
            <Link to={`/reviews/${review.review_id}`} className="review-row__open">
              <span className="review-row__when">
                {formatDate(review.created_at)}
                {/* Which revision was judged is the fact that separates two reviews of one
                    case. Without it the rows differ only by timestamp, and the reader
                    cannot tell a re-run from a review of a changed case. */}
                <small>case rev {review.case_revision}</small>
              </span>
              <span className="review-row__verdict">
                <Outcome review={review} />
              </span>
              {index === 0 && reviews.length > 1 ? (
                <span className="review-row__latest">latest</span>
              ) : (
                <span />
              )}
              <ArrowRight size={15} aria-hidden className="review-row__go" />
            </Link>
            <RowActions
              review={review}
              busy={busy}
              onCancel={() => onCancel(review.review_id)}
              onDelete={() => onDelete(review.review_id)}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Newest first within a case, and cases ordered by their most recent review. */
export function groupByCase(reviews: BoundaryReviewSummary[]) {
  const groups = new Map<string, BoundaryReviewSummary[]>();
  // The listing already arrives newest first, so insertion order is both the order of the
  // rows inside a group and the order of the groups themselves.
  for (const review of reviews) {
    groups.set(review.case_id, [...(groups.get(review.case_id) || []), review]);
  }
  return [...groups.entries()].map(([caseId, items]) => ({
    caseId,
    // The title comes from the review that recorded it. A review that failed before
    // composing a report has none, and an older row is a better answer than a placeholder.
    title: items.find((item) => item.case_title)?.case_title || null,
    reviews: items,
  }));
}

export function ReviewsPage() {
  const client = useQueryClient();
  const reviews = useQuery({
    queryKey: ["reviews"],
    queryFn: () => api.reviews(),
    // Polled only while something is actually running, and stopped the moment nothing is.
    // A run reports through its own request's stream; this page is a second reader with no
    // stream of its own, and one that polled for ever would keep a local model's machine
    // busy answering a question whose answer cannot change.
    refetchInterval: (query) => (anyRunning(query.state.data || []) ? 2000 : false),
  });
  const grouped = useMemo(() => groupByCase(reviews.data || []), [reviews.data]);

  const refresh = () => client.invalidateQueries({ queryKey: ["reviews"] });
  const cancel = useMutation({ mutationFn: api.cancelReview, onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.deleteReview, onSuccess: refresh });
  const busy = cancel.isPending || remove.isPending;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Everything this workspace has judged"
        title="Reviews"
        description="Each one is immutable and pinned to the case revision and atlas version it judged, so an older review keeps saying what it said."
      />

      {reviews.isLoading ? <Loading label="Reading reviews…" /> : null}
      {reviews.isError ? <ErrorPanel error={reviews.error} /> : null}
      {/* The server's own words. Cancelling a review that has just finished, or deleting
          one still running, are both refusals worth reading rather than paraphrasing. */}
      {cancel.isError ? <ErrorPanel error={cancel.error} /> : null}
      {remove.isError ? <ErrorPanel error={remove.error} /> : null}
      {reviews.data && reviews.data.length === 0 ? (
        <EmptyState
          icon={<Compass size={30} />}
          title="No reviews yet"
          description="Pick a repository and a case on the start step, then run the review."
          action={
            <Link className="button button--primary" to="/">
              Start a review <ArrowRight size={15} aria-hidden />
            </Link>
          }
        />
      ) : null}

      {grouped.map((group) => (
        <CaseHistory
          key={group.caseId}
          caseId={group.caseId}
          title={group.title}
          reviews={group.reviews}
          busy={busy}
          onCancel={(reviewId) => cancel.mutate(reviewId)}
          onDelete={(reviewId) => remove.mutate(reviewId)}
        />
      ))}
    </div>
  );
}
