import { Link } from "react-router-dom";

import type { Review } from "../../api";
import { cn } from "../../lib/cn";
import { relativeTime, statusOf } from "../../lib/format";
import { Timeline, TimelineItem } from "../../ui/timeline";

/**
 * The lineage this review belongs to: same repository branch, same case, in sequence.
 *
 * Reviews are immutable, so this is history rather than navigation between drafts — every
 * entry is still readable exactly as it was recorded.
 */
export function RevisionRail({
  current,
  reviews,
  className,
}: {
  current: Review;
  reviews: Review[];
  className?: string;
}) {
  const lineage = reviews
    .filter(
      (item) =>
        item.repository.branch_id === current.repository.branch_id &&
        item.case.id === current.case.id,
    )
    .sort((left, right) => left.sequence - right.sequence);
  const entries = lineage.length ? lineage : [current];

  return (
    <div className={cn("px-3 py-3", className)}>
      <h2 className="font-display text-sm font-semibold tracking-tight text-ink">Review lineage</h2>
      <p className="mb-3 mt-0.5 text-xs text-ink-3">
        {entries.length === 1
          ? "The first review of this case"
          : `${entries.length} immutable revisions`}
      </p>
      <Timeline>
        {entries.map((review) => {
          const active = review.id === current.id;
          const status = statusOf(review.status);
          return (
            <TimelineItem key={review.id} current={active}>
              <Link
                to={`/reviews/${review.id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-md px-2.5 py-2 transition",
                  active ? "bg-accent-soft" : "hover:bg-sunken",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={cn("text-[13px] font-semibold", active ? "text-accent" : "text-ink")}>
                    Review {review.sequence}
                  </span>
                  <span
                    className={cn(
                      "text-[10px] font-bold uppercase tracking-[0.08em]",
                      status.tone === "cleared" && "text-cleared",
                      status.tone === "held" && "text-held",
                      status.tone === "material" && "text-material",
                      status.tone === "neutral" && "text-ink-3",
                      status.tone === "accent" && "text-accent",
                    )}
                  >
                    <span aria-hidden="true" className="mr-1">
                      {status.glyph}
                    </span>
                    {status.label}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] text-ink-3">
                  Case rev {review.case.revision} · {relativeTime(review.started_at)}
                </div>
              </Link>
            </TimelineItem>
          );
        })}
      </Timeline>
    </div>
  );
}
