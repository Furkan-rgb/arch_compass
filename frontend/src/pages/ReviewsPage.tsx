import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CircleCheck, Compass, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
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
} from "../components";
import type { BoundaryReviewSummary } from "../types";

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
}: {
  caseId: string;
  title: string | null;
  reviews: BoundaryReviewSummary[];
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
          <li key={review.review_id}>
            <Link to={`/reviews/${review.review_id}`} className="review-row">
              <span className="review-row__when">
                {formatDate(review.created_at)}
                {/* Which revision was judged is the fact that separates two reviews of one
                    case. Without it the rows differ only by timestamp, and the reader
                    cannot tell a re-run from a review of a changed case. */}
                <small>case rev {review.case_revision}</small>
              </span>
              <span className="review-row__verdict">
                {review.boundaries_material > 0 ? (
                  <Badge tone="warning">
                    <TriangleAlert size={13} aria-hidden />
                    {review.boundaries_material} of {review.boundaries_reviewed} should
                    change
                  </Badge>
                ) : (
                  <Badge tone="success">
                    <CircleCheck size={13} aria-hidden />
                    all {review.boundaries_reviewed} earning their place
                  </Badge>
                )}
              </span>
              {index === 0 && reviews.length > 1 ? (
                <span className="review-row__latest">latest</span>
              ) : (
                <span />
              )}
              <ArrowRight size={15} aria-hidden className="review-row__go" />
            </Link>
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
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const grouped = useMemo(() => groupByCase(reviews.data || []), [reviews.data]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Everything this workspace has judged"
        title="Reviews"
        description="Each one is immutable and pinned to the case revision and atlas version it judged, so an older review keeps saying what it said."
      />

      {reviews.isLoading ? <Loading label="Reading reviews…" /> : null}
      {reviews.isError ? <ErrorPanel error={reviews.error} /> : null}
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
        />
      ))}
    </div>
  );
}
