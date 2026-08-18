import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { coreApi } from "../api";
import { Button, Empty, ErrorNotice, Input, Loading, PageTitle, StatusBadge, buttonClass, cn } from "../components/ui";

export function ReviewsPage() {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: coreApi.reviews });
  const remove = useMutation({ mutationFn: coreApi.deleteReview, onSuccess: async () => { setPendingDelete(null); await client.invalidateQueries({ queryKey: ["reviews"] }); } });
  if (reviews.isLoading) return <Loading label="Opening review history…" />;
  if (reviews.error) return <ErrorNotice error={reviews.error} />;
  const visible = (reviews.data || []).filter((review) => {
    const matchesStatus = status === "all" || review.status === status;
    const haystack = `${review.case.goal} ${review.repository.path} ${review.repository.branch || ""}`.toLowerCase();
    return matchesStatus && haystack.includes(query.toLowerCase());
  });

  return <div>
    <PageTitle eyebrow="Immutable history" title="Review revisions" description="Inspect outcomes over time, resume clarifications, and trace every judgment back to its repository and case revision."><Link to="/start" className={buttonClass()}>New review</Link></PageTitle>
    {(reviews.data || []).length ? <div className="mb-5 flex flex-col gap-3 rounded-2xl border border-rule bg-surface p-3 shadow-sm sm:flex-row"><Input aria-label="Search reviews" value={query} onChange={(event) => setQuery(event.target.value)} className="sm:max-w-sm" placeholder="Search goal, repository, or branch…" /><div className="scrollbar-none flex gap-1 overflow-x-auto" aria-label="Filter review status">{["all", "completed", "awaiting_answers", "failed", "cancelled"].map((item) => <button key={item} onClick={() => setStatus(item)} className={cn("shrink-0 rounded-lg px-3 py-2 text-xs font-semibold capitalize", status === item ? "bg-primary-soft text-primary" : "text-ink-3 hover:bg-canvas-strong")}>{item.replaceAll("_", " ")}</button>)}</div></div> : null}
    {!visible.length ? <Empty title={reviews.data?.length ? "No matching reviews" : "No reviews yet"}>{reviews.data?.length ? "Adjust the search or status filter." : "Run your first repository review to establish an immutable architecture record."}</Empty> : <div className="grid gap-3">{visible.map((review) => <article key={review.id} className="group rounded-2xl border border-rule bg-surface p-5 shadow-card transition hover:border-primary/30 sm:p-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><Link to={`/reviews/${review.id}`} className="min-w-0 flex-1 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary/30"><div className="flex flex-wrap items-center gap-3"><h2 className="font-display text-xl font-semibold tracking-tight">{review.case.goal || review.repository.path.split("/").pop() || "Architecture review"}</h2><StatusBadge status={review.status} /></div><p className="mt-3 text-sm text-ink-2">Review {review.sequence} · Case revision {review.case.revision} · {review.findings.length} findings</p><p className="mt-2 truncate font-mono text-xs text-ink-3">{review.repository.path}</p><div className="mt-4 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-primary-soft px-2.5 py-1 text-primary">{review.delta.new.length} new</span><span className="rounded-full bg-canvas-strong px-2.5 py-1 text-ink-2">{review.delta.changed.length} changed</span><span className="rounded-full bg-success-soft px-2.5 py-1 text-success">{review.delta.addressed.length} addressed</span></div></Link><div className="shrink-0">{pendingDelete === review.id ? <div className="flex items-center gap-2"><span className="text-xs text-ink-3">Delete?</span><Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(review.id)}>Confirm</Button><Button size="sm" variant="ghost" onClick={() => setPendingDelete(null)}>Keep</Button></div> : <Button size="sm" variant="ghost" onClick={() => setPendingDelete(review.id)}>Delete</Button>}</div></div></article>)}</div>}
    {remove.error ? <div className="mt-4"><ErrorNotice error={remove.error} /></div> : null}
  </div>;
}
