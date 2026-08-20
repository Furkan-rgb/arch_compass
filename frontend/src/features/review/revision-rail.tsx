import { Link } from "react-router-dom";

import type { Review, ReviewRunSummary } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, relativeTime, statusOf } from "../../lib/format";
import { TONE_TEXT } from "../../ui/meta";
import { Spinner } from "../../ui/states";
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
  pending,
  pendingSelected = false,
  onSelectPending,
  className,
}: {
  current: Review;
  reviews: Review[];
  /** A run for this same branch and case, still being made. The next entry, before it exists. */
  pending?: ReviewRunSummary | null;
  pendingSelected?: boolean;
  onSelectPending?: () => void;
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
        {pending ? ", and one being made" : ""}
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
                      status.tone === "neutral" ? "text-ink-3" : TONE_TEXT[status.tone],
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

        {/* The revision being made right now, in the same rail as the ones that exist. It
            has no id, no sequence and no findings yet — the atlas it will be composed from
            is still being built — so it is a button rather than a link, and it says what it
            is instead of borrowing the shape of a finished review. */}
        {pending ? (
          <TimelineItem current={pendingSelected}>
            <button
              type="button"
              onClick={onSelectPending}
              aria-current={pendingSelected ? "true" : undefined}
              className={cn(
                "block w-full rounded-md px-2.5 py-2 text-left transition",
                pendingSelected ? "bg-accent-soft" : "hover:bg-sunken",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={cn(
                    "text-[13px] font-semibold",
                    pendingSelected ? "text-accent" : "text-ink",
                  )}
                >
                  Review {entries[entries.length - 1].sequence + 1}
                </span>
                <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-accent">
                  <Spinner /> In progress
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-ink-3">
                {pending.stage ? humanise(pending.stage) : "starting"}
              </div>
            </button>
          </TimelineItem>
        ) : null}
      </Timeline>
    </div>
  );
}
