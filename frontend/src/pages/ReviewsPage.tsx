import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { coreApi } from "../api";
import { Empty, ErrorNotice, Loading, PageTitle, StatusBadge } from "../components/ui";

export function ReviewsPage() {
  const client = useQueryClient();
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: coreApi.reviews });
  const remove = useMutation({ mutationFn: coreApi.deleteReview, onSuccess: () => client.invalidateQueries({ queryKey: ["reviews"] }) });
  if (reviews.isLoading) return <Loading label="Opening review history…" />;
  if (reviews.error) return <ErrorNotice error={reviews.error} />;
  return (
    <div>
      <PageTitle eyebrow="Immutable history" title="Review revisions"><Link to="/start" className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent">New review</Link></PageTitle>
      {!reviews.data?.length ? <Empty>No reviews have been recorded yet.</Empty> : (
        <div className="grid gap-3">
          {reviews.data.map((review) => (
            <article key={review.id} className="group rounded-xl border border-rule bg-surface p-5 hover:border-primary/50">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <Link to={`/reviews/${review.id}`} className="min-w-0 flex-1">
                  <div className="flex items-center gap-3"><h2 className="truncate font-display text-lg font-semibold">{review.case.goal || review.repository.path.split("/").pop() || "Architecture review"}</h2><StatusBadge status={review.status} /></div>
                  <p className="mt-2 text-sm text-ink-2">Review {review.sequence} · Case rev {review.case.revision} · {review.findings.length} findings · {review.delta.new.length} new · {review.delta.changed.length} changed</p>
                  <p className="mt-1 truncate font-mono text-xs text-ink-3">{review.repository.path}</p>
                </Link>
                <button onClick={() => remove.mutate(review.id)} className="opacity-0 text-xs text-danger transition-opacity group-hover:opacity-100 focus:opacity-100">Delete</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
