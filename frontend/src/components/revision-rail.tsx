import { Link } from "react-router-dom";

import type { Review } from "../api";
import { StatusBadge } from "./ui";

export function RevisionRail({ current, reviews }: { current: Review; reviews: Review[] }) {
  const lineage = reviews
    .filter((item) => item.repository.branch_id === current.repository.branch_id && item.case.id === current.case.id)
    .sort((left, right) => left.sequence - right.sequence);
  return (
    <aside className="rounded-xl border border-rule bg-surface p-4">
      <div className="text-xs font-semibold uppercase tracking-[0.15em] text-ink-3">Review lineage</div>
      <div className="mt-4 grid gap-1">
        {lineage.map((review) => (
          <Link key={review.id} to={`/reviews/${review.id}`} className={`flex items-center justify-between gap-3 rounded-lg p-3 ${review.id === current.id ? "bg-primary/10 ring-1 ring-primary/30" : "hover:bg-canvas"}`}>
            <div><div className="text-sm font-medium">Review {review.sequence}</div><div className="mt-1 text-xs text-ink-3">Case rev {review.case.revision}</div></div>
            <StatusBadge status={review.status} />
          </Link>
        ))}
      </div>
    </aside>
  );
}
