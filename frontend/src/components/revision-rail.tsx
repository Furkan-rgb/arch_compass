import { Link } from "react-router-dom";

import type { Review } from "../api";
import { Card, StatusBadge, cn } from "./ui";

export function RevisionRail({ current, reviews }: { current: Review; reviews: Review[] }) {
  const lineage = reviews
    .filter((item) => item.repository.branch_id === current.repository.branch_id && item.case.id === current.case.id)
    .sort((left, right) => left.sequence - right.sequence);
  return (
    <Card className="p-3 sm:p-3">
      <div className="px-2 pt-1 text-[10px] font-bold uppercase tracking-[0.15em] text-ink-3">Review lineage</div>
      <div className="mt-3 grid gap-1">
        {lineage.map((review) => (
          <Link key={review.id} to={`/reviews/${review.id}`} aria-current={review.id === current.id ? "page" : undefined} className={cn("flex items-center justify-between gap-3 rounded-xl p-3 transition", review.id === current.id ? "bg-primary-soft ring-1 ring-primary/25" : "hover:bg-canvas-strong")}>
            <div><div className="text-sm font-medium">Review {review.sequence}</div><div className="mt-1 text-xs text-ink-3">Case rev {review.case.revision}</div></div>
            <StatusBadge status={review.status} />
          </Link>
        ))}
      </div>
    </Card>
  );
}
