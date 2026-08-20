import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type Review, type ReviewRun } from "../../api";
import { humanise, relativeTime, repositoryName, shortId } from "../../lib/format";
import { StatusBadge, Tag } from "../../ui/badge";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { MetaLine, Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";

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
              {repositoryName(review.repository.path)}
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
          {/* How much moved since the review before, as three counts. Not three hues: the
              card already carries the review's status in the one palette that means
              something, and "changed" painted amber claimed a held judgement nothing had
              made. The numbers are what is being compared, so the numbers carry the weight. */}
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            {(
              [
                [review.delta.new.length, "new"],
                [review.delta.changed.length, "changed"],
                [review.delta.addressed.length, "addressed"],
              ] as const
            ).map(([count, label]) => (
              <span
                key={label}
                className="rounded-xs border border-rule bg-sunken px-2 py-0.5 text-ink-3"
              >
                <strong className="font-semibold tabular-nums text-ink">{count}</strong> {label}
              </span>
            ))}
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

/**
 * A review that is still being produced.
 *
 * Sits at the top of the same list as the finished ones, because it is the same thing seen
 * earlier — and because until it was here a run was only reachable by an id somebody was
 * already holding. Starting a review and then looking at anything else lost it, which is
 * the ordinary way to use a page whose work takes as long as a batch takes.
 *
 * Not styled as a review card. It has no verdicts, no delta and no sequence yet, and a card
 * with those spaces left blank would read as a review that came back empty.
 */
function RunRow({ run }: { run: ReviewRun }) {
  return (
    <article className="rounded-lg border border-accent/30 bg-accent-soft/40 p-4 transition hover:border-accent/50 sm:p-5">
      <Link to={`/runs/${run.run_id}`} className="block min-w-0 rounded-md">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
            {run.repository_name}
          </h2>
          <span className="inline-flex items-center gap-1.5 rounded-sm border border-accent/30 px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-accent">
            <Spinner /> In progress
          </span>
        </div>
        <MetaLine
          className="mt-2"
          items={[
            run.stage ? humanise(run.stage) : "starting",
            `${run.stages.length} ${run.stages.length === 1 ? "stage" : "stages"} so far`,
            run.branch_name || null,
          ]}
        />
        <Mono className="mt-2.5 block truncate text-[11px] text-ink-3">{run.repository_root}</Mono>
      </Link>
    </article>
  );
}

export function ReviewsPage() {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  // Polled while anything is in flight, and only then: this is the page a reader comes back
  // to, so a run that finished while they were away has to become a review without a reload.
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => (query.state.data?.length ? 4000 : false),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteReview(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  if (reviews.isLoading) return <LoadingPanel label="Opening review history…" rows={4} />;
  if (reviews.error) return <ErrorNotice error={reviews.error} />;

  const inFlight = runs.data ?? [];
  const all = reviews.data ?? [];
  const visible = all.filter((review) => {
    const matchesStatus = status === "all" || review.status === status;
    const haystack =
      `${review.repository.path} ${review.repository.branch ?? ""}`.toLowerCase();
    return matchesStatus && haystack.includes(query.toLowerCase());
  });

  return (
    <div>
      <PageHeader
        eyebrow="Immutable history"
        title="Reviews"
        description="Every review is a recorded revision: the repository snapshot it read, the case revision it judged against, and the findings it composed."
      />

      {inFlight.length ? (
        <div className="mb-2.5 grid gap-2.5">
          {inFlight.map((run) => (
            <RunRow key={run.run_id} run={run} />
          ))}
        </div>
      ) : null}

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

      {!visible.length && !inFlight.length ? (
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
