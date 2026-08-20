import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type Review, type ReviewRun } from "../../api";
import { humanise, relativeTime, repositoryName, shortId } from "../../lib/format";
import { StatusBadge } from "../../ui/badge";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { GitBranchIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Panel } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";
import { stageLabel } from "../start/run-progress";

const STATUS_FILTERS = ["all", "completed", "awaiting_answers", "failed", "cancelled"] as const;

/**
 * One line of work: the same repository, the same branch, the same case.
 *
 * Reviews are immutable and sequenced under exactly these three things — that is the
 * charter's third commitment and the reason a delta can exist at all. This page used to
 * render them as a flat list of identical cards, each titled with the repository folder, so
 * eight revisions of one branch read as eight unrelated peers and the sequence was a line of
 * small grey text. What makes review 4 worth keeping is that it succeeded review 3.
 */
type Lineage = {
  key: string;
  path: string;
  branch: string | null;
  reviews: Review[];
  run: ReviewRun | null;
};

function lineagesOf(reviews: Review[], runs: ReviewRun[]): Lineage[] {
  const groups = new Map<string, Lineage>();
  for (const review of reviews) {
    const key = `${review.repository.path}::${review.repository.branch_id}::${review.case.id}`;
    const existing = groups.get(key);
    if (existing) existing.reviews.push(review);
    else {
      groups.set(key, {
        key,
        path: review.repository.path,
        branch: review.repository.branch,
        reviews: [review],
        run: null,
      });
    }
  }
  // A run in flight is the next revision of a lineage, not a separate kind of thing sitting
  // in its own list above everything. It only becomes one when its lineage has no reviews.
  for (const run of runs) {
    const key = `${run.repository_root ?? ""}::${run.branch_id}::${run.case_id}`;
    const existing = groups.get(key);
    if (existing) existing.run = run;
    else {
      groups.set(key, {
        key,
        path: run.repository_root ?? run.repository_name ?? "",
        branch: run.branch_name ?? null,
        reviews: [],
        run,
      });
    }
  }
  return [...groups.values()]
    .map((lineage) => ({
      ...lineage,
      reviews: [...lineage.reviews].sort((left, right) => right.sequence - left.sequence),
    }))
    .sort((left, right) => Date.parse(latestAt(right)) - Date.parse(latestAt(left)));
}

function latestAt(lineage: Lineage): string {
  if (lineage.run) return new Date().toISOString();
  return lineage.reviews[0]?.started_at ?? "1970-01-01T00:00:00Z";
}

function RevisionRow({
  review,
  onDelete,
  deleting,
}: {
  review: Review;
  onDelete: () => void;
  deleting: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const outstanding = review.findings.filter((finding) => finding.verdict !== "cleared").length;
  const moved = review.delta.new.length + review.delta.changed.length;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule px-4 py-3 transition hover:bg-sunken/50 sm:px-5">
      <Link to={`/reviews/${review.id}`} className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-[13px] font-medium tabular-nums text-ink">
          Review {review.sequence}
        </span>
        <StatusBadge status={review.status} />
        <span className="text-[11.5px] text-ink-3">
          case revision {review.case.revision}
          {review.repository.commit ? (
            <> · {shortId(review.repository.commit, 8)}</>
          ) : null}{" "}
          · {relativeTime(review.started_at)}
        </span>
        <span className="min-w-0 flex-1 text-right text-[11.5px] tabular-nums text-ink-3">
          <span className="text-ink-2">{review.findings.length}</span> judged ·{" "}
          <span className="text-ink-2">{outstanding}</span> not cleared
          {review.previous_review_id ? (
            <>
              {" · "}
              <span className="text-ink-2">{moved}</span> moved
            </>
          ) : null}
        </span>
      </Link>

      <span className="flex shrink-0 items-center gap-2">
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
      </span>
    </li>
  );
}

/**
 * The revision being made, in the lineage it will belong to.
 *
 * Every identifier a review is filed under is known before the review exists, so the next
 * revision can be listed and opened while it is still being made — at the top of its own
 * line of work rather than in a separate list of jobs above the history.
 */
function PendingRow({ run, sequence }: { run: ReviewRun; sequence: number }) {
  return (
    <li className="border-t border-rule bg-sunken/40">
      <Link
        to={`/runs/${run.run_id}`}
        className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 transition hover:bg-sunken sm:px-5"
      >
        <span className="font-mono text-[13px] font-medium tabular-nums text-ink">
          Review {run.sequence ?? sequence}
        </span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-ink-3">
          <Spinner /> In progress
        </span>
        <span className="text-[11.5px] text-ink-3">
          {run.stage ? stageLabel(run.stage) : "starting"}
        </span>
      </Link>
    </li>
  );
}

function LineageBlock({
  lineage,
  onDelete,
  deleting,
}: {
  lineage: Lineage;
  onDelete: (id: string) => void;
  deleting: boolean;
}) {
  const newest = lineage.reviews[0];
  return (
    <Panel as="article">
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[15px] leading-tight text-ink-3">
            <span className="font-medium text-ink [overflow-wrap:anywhere]">
              {repositoryName(lineage.path)}
            </span>
            {lineage.branch ? (
              <>
                <GitBranchIcon className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="sr-only">branch</span>
                <span className="[overflow-wrap:anywhere]">{lineage.branch}</span>
              </>
            ) : null}
          </h2>
          <Mono className="mt-1 block truncate text-[11px] text-ink-3">{lineage.path}</Mono>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.09em] text-ink-3">
            {lineage.reviews.length === 1
              ? "1 revision"
              : `${lineage.reviews.length} revisions`}
          </span>
          {/* Only where it summarises. With one revision the row beneath says the same
              thing three centimetres away. */}
          {newest && lineage.reviews.length > 1 ? (
            <StatusBadge status={newest.status} />
          ) : null}
        </div>
      </header>

      <ul>
        {lineage.run ? (
          <PendingRow run={lineage.run} sequence={lineage.reviews.length + 1} />
        ) : null}
        {lineage.reviews.map((review) => (
          <RevisionRow
            key={review.id}
            review={review}
            deleting={deleting}
            onDelete={() => onDelete(review.id)}
          />
        ))}
      </ul>
    </Panel>
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

  const all = reviews.data ?? [];
  const visible = all.filter((review) => {
    const matchesStatus = status === "all" || review.status === status;
    const haystack =
      `${review.repository.path} ${review.repository.branch ?? ""}`.toLowerCase();
    return matchesStatus && haystack.includes(query.toLowerCase());
  });
  const lineages = lineagesOf(visible, runs.data ?? []);

  return (
    <div>
      <PageHeader
        eyebrow="Immutable history"
        title="Reviews"
        description="Reviews are sequenced per branch and case. Each one records the repository snapshot it read, the case revision it judged against, and the findings it composed — and each is readable exactly as it was recorded."
      />

      {all.length ? (
        <div className="mb-4 flex flex-col gap-2 rounded-lg border border-rule bg-surface p-2 sm:flex-row sm:items-center">
          <SearchInput
            label="Search reviews"
            value={query}
            onValueChange={setQuery}
            placeholder="Repository or branch"
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

      {!lineages.length ? (
        <EmptyState
          title={all.length ? "No review matches that" : "No reviews yet"}
          action={all.length ? undefined : <ButtonLink to="/start">Review a repository</ButtonLink>}
        >
          {all.length
            ? "Adjust the search or the status filter."
            : "Point ArchCompass at a repository to record the first architecture review."}
        </EmptyState>
      ) : (
        <div className="grid gap-3">
          {lineages.map((lineage) => (
            <LineageBlock
              key={lineage.key}
              lineage={lineage}
              deleting={remove.isPending}
              onDelete={(id) => remove.mutate(id)}
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
