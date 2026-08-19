import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { coreApi, type Review } from "../../api";
import { humanise, relativeTime, repositoryName, shortId } from "../../lib/format";
import { StatusBadge, Tag } from "../../ui/badge";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { EmptyState, ErrorNotice, LoadingPanel } from "../../ui/states";

const STATUS_FILTERS = ["all", "completed", "awaiting_answers", "failed", "cancelled"] as const;

function ReviewRow({
  review,
  onDelete,
  deleting,
}: {
  review: Review;
  onDelete: () => void;
  deleting: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const attention = review.findings.filter((finding) => finding.verdict !== "cleared").length;
  return (
    <article className="group rounded-lg border border-rule bg-surface p-4 shadow-panel transition hover:border-rule-strong sm:p-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <Link to={`/reviews/${review.id}`} className="min-w-0 flex-1 rounded-md">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              {review.case.goal || repositoryName(review.repository.path)}
            </h2>
            <StatusBadge status={review.status} />
          </div>
          <MetaLine
            className="mt-2"
            items={[
              `Review ${review.sequence}`,
              `Case revision ${review.case.revision}`,
              `${review.findings.length} candidates`,
              attention ? `${attention} need attention` : "nothing outstanding",
              relativeTime(review.started_at),
            ]}
          />
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <Mono className="truncate text-[11px] text-ink-3">{review.repository.path}</Mono>
            {review.repository.branch ? <Tag>{review.repository.branch}</Tag> : null}
            {review.repository.commit ? (
              <Tag>
                <Mono className="text-[11px]">{shortId(review.repository.commit, 8)}</Mono>
              </Tag>
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            <span className="rounded-xs border border-accent/20 bg-accent-soft px-2 py-0.5 text-accent">
              {review.delta.new.length} new
            </span>
            <span className="rounded-xs border border-held/25 bg-held-soft px-2 py-0.5 text-held">
              {review.delta.changed.length} changed
            </span>
            <span className="rounded-xs border border-cleared/20 bg-cleared-soft px-2 py-0.5 text-cleared">
              {review.delta.addressed.length} addressed
            </span>
          </div>
        </Link>

        <div className="flex shrink-0 items-center gap-2">
          {confirming ? (
            <>
              <span className="text-xs text-ink-3">Delete this review?</span>
              <Button size="sm" variant="danger" disabled={deleting} onClick={onDelete}>
                Confirm
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                Keep
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming(true)}
              aria-label={`Delete review ${review.sequence}`}
            >
              Delete
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}

export function ReviewsPage() {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: coreApi.reviews });
  const remove = useMutation({
    mutationFn: (id: string) => coreApi.deleteReview(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  if (reviews.isLoading) return <LoadingPanel label="Opening review history…" rows={4} />;
  if (reviews.error) return <ErrorNotice error={reviews.error} />;

  const all = reviews.data ?? [];
  const visible = all.filter((review) => {
    const matchesStatus = status === "all" || review.status === status;
    const haystack =
      `${review.case.goal} ${review.repository.path} ${review.repository.branch ?? ""}`.toLowerCase();
    return matchesStatus && haystack.includes(query.toLowerCase());
  });

  return (
    <div>
      <PageHeader
        eyebrow="Immutable history"
        title="Reviews"
        description="Every review is a recorded revision: the repository snapshot it read, the case revision it judged against, and the findings it composed."
      />

      {all.length ? (
        <div className="mb-4 flex flex-col gap-2 rounded-lg border border-rule bg-surface p-2 shadow-panel sm:flex-row sm:items-center">
          <SearchInput
            label="Search reviews"
            value={query}
            onValueChange={setQuery}
            placeholder="Search goal, repository or branch"
            className="sm:max-w-sm"
          />
          <div
            role="group"
            aria-label="Filter by status"
            className="scrollbar-none flex gap-1 overflow-x-auto"
          >
            {STATUS_FILTERS.map((item) => (
              <ToggleButton key={item} pressed={status === item} onClick={() => setStatus(item)}>
                {humanise(item)}
              </ToggleButton>
            ))}
          </div>
        </div>
      ) : null}

      {!visible.length ? (
        <EmptyState
          title={all.length ? "No review matches that" : "No reviews yet"}
          action={all.length ? undefined : <ButtonLink to="/start">Review a repository</ButtonLink>}
        >
          {all.length
            ? "Adjust the search or the status filter."
            : "Point ArchCompass at a repository to record the first architecture review."}
        </EmptyState>
      ) : (
        <div className="grid gap-2.5">
          {visible.map((review) => (
            <ReviewRow
              key={review.id}
              review={review}
              deleting={remove.isPending}
              onDelete={() => remove.mutate(review.id)}
            />
          ))}
        </div>
      )}

      {remove.error ? (
        <div className="mt-4">
          <ErrorNotice error={remove.error} />
        </div>
      ) : null}
    </div>
  );
}
