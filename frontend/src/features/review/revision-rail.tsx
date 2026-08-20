import { Link } from "react-router-dom";

import type { Review, ReviewRun } from "../../api";
import { cn } from "../../lib/cn";
import { relativeTime, statusOf } from "../../lib/format";
import { stageLabel } from "../start/run-progress";
import { TONE_TEXT } from "../../ui/meta";
import { Spinner } from "../../ui/states";
import { Timeline, TimelineItem } from "../../ui/timeline";

/**
 * The lineage a review belongs to: same repository branch, same case, in sequence.
 *
 * Reviews are immutable, so this is history rather than navigation between drafts — every
 * entry is still readable exactly as it was recorded.
 *
 * A run in flight is one of the entries. Every identifier a review is filed under is known
 * before the review exists — the repository, the branch, the case, and the sequence it will
 * take — so the next revision can be listed and opened while it is still being made. What
 * it does not have is a composed review, which is why its entry links to the run rather
 * than to a review id that does not exist.
 */
export function RevisionRail({
  reviews,
  currentReviewId,
  pending,
  pendingCurrent = false,
  className,
}: {
  /** The lineage, already narrowed to one branch and case, in sequence order. */
  reviews: Review[];
  currentReviewId?: string;
  /** The revision being made right now, if there is one. */
  pending?: ReviewRun | null;
  /** Whether the pending entry is the one being read. */
  pendingCurrent?: boolean;
  className?: string;
}) {
  const entries = [...reviews].sort((left, right) => left.sequence - right.sequence);
  const total = entries.length + (pending ? 1 : 0);

  return (
    <div className={cn("px-3 py-3", className)}>
      <h2 className="font-display text-sm font-semibold tracking-tight text-ink">Review lineage</h2>
      <p className="mb-3 mt-0.5 text-xs text-ink-3">
        {entries.length === 0
          ? "The first review of this case"
          : entries.length === 1
            ? "One immutable revision"
            : `${entries.length} immutable revisions`}
        {pending ? (total === 1 ? ", being made now" : ", and one being made") : ""}
      </p>
      <Timeline>
        {entries.map((review) => {
          const active = review.id === currentReviewId;
          const status = statusOf(review.status);
          return (
            <TimelineItem key={review.id} current={active}>
              <RailEntry
                to={`/reviews/${review.id}`}
                active={active}
                sequence={review.sequence}
                detail={`Case rev ${review.case.revision} · ${relativeTime(review.started_at)}`}
                badge={
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
                }
              />
            </TimelineItem>
          );
        })}

        {pending ? (
          <TimelineItem current={pendingCurrent}>
            <RailEntry
              to={`/runs/${pending.run_id}`}
              active={pendingCurrent}
              sequence={pending.sequence ?? entries.length + 1}
              detail={pending.stage ? stageLabel(pending.stage) : "starting"}
              badge={
                <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-ink-3">
                  <Spinner /> In progress
                </span>
              }
            />
          </TimelineItem>
        ) : null}
      </Timeline>
    </div>
  );
}

function RailEntry({
  to,
  active,
  sequence,
  detail,
  badge,
}: {
  to: string;
  active: boolean;
  sequence: number;
  detail: string;
  badge: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "block rounded-md px-2.5 py-2 transition",
        active ? "bg-sunken" : "hover:bg-sunken",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn("text-[13px] font-semibold", active ? "text-ink" : "text-ink-2")}>
          Review {sequence}
        </span>
        {badge}
      </div>
      <div className="mt-0.5 text-[11px] text-ink-3">{detail}</div>
    </Link>
  );
}

/**
 * The reviews of one lineage: same branch, same case.
 *
 * Here rather than at each call site because the rail and the pages that feed it have to
 * agree on what "the same line of work" means, and a run knows its branch and case before
 * it knows anything else.
 */
export function lineageOf(
  reviews: Review[],
  branchId: string | null | undefined,
  caseId: string | null | undefined,
): Review[] {
  if (!branchId || !caseId) return [];
  return reviews.filter(
    (review) => review.repository.branch_id === branchId && review.case.id === caseId,
  );
}
