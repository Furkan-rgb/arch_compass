import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, type Decision, type Finding, type Review, type ReviewRun } from "../../api";
import { cn } from "../../lib/cn";
import {
  humanise,
  relativeTime,
  repositoryName,
  shortId,
  statusOf,
  verdictOf,
} from "../../lib/format";
import { needsAttention, orderedFindings } from "../review/docket-rules";
import { StatusBadge } from "../../ui/badge";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { ArrowRight, GitBranchIcon } from "../../ui/icons";
import { Mark } from "../../ui/mark";
import { Mono, TONE_TEXT } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Panel } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";
import { stageLabel } from "../start/run-progress";

const STATUS_FILTERS = ["all", "completed", "awaiting_answers", "failed", "cancelled"] as const;

/**
 * One line of work: the same repository, the same branch, the same case.
 *
 * Reviews are immutable and sequenced under exactly these three things — that is the
 * charter's third commitment and the reason a delta can exist at all. What makes review 4
 * worth keeping is that it succeeded review 3, so a lineage is drawn as a trajectory rather
 * than as four rows repeating the same six fields.
 */
type Lineage = {
  key: string;
  path: string;
  branch: string | null;
  branchId: string | null;
  /** Newest first, which is the order they are listed in. */
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
        branchId: review.repository.branch_id,
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
        branchId: run.branch_id ?? null,
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

/**
 * Everything on this page that still wants a person, wherever it lives.
 *
 * This is the section the page was missing. A review history answers a librarian's question —
 * what reviews exist — and the question a returning reviewer actually has is "what wants me
 * now", which no amount of sorting a list of reviews by date will answer: it is a fact about
 * the candidates inside them.
 *
 * Only the newest revision of each lineage is consulted. An outstanding candidate in review 3
 * was either carried into review 4, where it is counted, or it went away, and listing both
 * would double every open item on the branch.
 */
type Wanting = {
  key: string;
  review: Review;
  to: string;
  title: string;
  /** What the candidate claims. The reason this list can be read rather than only counted. */
  claim: string | null;
  detail: string;
  glyph: Parameters<typeof Mark>[0]["shape"];
  tone: ReturnType<typeof verdictOf>["tone"];
};

function wantingOf(reviews: Review[], decisions: Map<string, Map<string, Decision>>): Wanting[] {
  return reviews.flatMap((review) => {
    const branch = decisions.get(review.repository.branch_id ?? "") ?? new Map();
    const where = `${repositoryName(review.repository.path)}${
      review.repository.branch ? ` · ${review.repository.branch}` : ""
    } · review ${review.sequence}`;
    const open: Wanting[] =
      review.status === "awaiting_answers" && review.questions.length
        ? [
            {
              key: `${review.id}:clarification`,
              review,
              to: `/reviews/${review.id}`,
              title:
                review.questions.length === 1
                  ? "1 question wants an answer"
                  : `${review.questions.length} questions want an answer`,
              claim: review.questions[0]?.text ?? null,
              detail: where,
              glyph: "pause" as const,
              tone: "held" as const,
            },
          ]
        : [];
    const candidates = orderedFindings(review)
      .filter((finding: Finding) => needsAttention(finding, branch.get(finding.candidate.id)))
      .map((finding) => {
        const descriptor = verdictOf(finding.verdict);
        return {
          key: `${review.id}:${finding.candidate.id}`,
          review,
          to: `/reviews/${review.id}`,
          title: finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary,
          claim: finding.candidate.summary,
          detail: where,
          glyph: descriptor.glyph,
          tone: descriptor.tone,
        };
      });
    return [...open, ...candidates];
  });
}

/**
 * One thing that wants a person, carrying what the section above it did not already say.
 *
 * The name and then the claim, which is the docket's rule applied one page up and for the
 * same reason: a column of `ports.Clock`, `ports.ConfigLoader`, `ports.IdGenerator` can be
 * counted but not read, so nothing on it tells you which of seven to open first. The claim
 * is one line here rather than the docket's two — this list is a way in, not the work.
 *
 * `hoisted` is the other half of that rule: where every row names the same review, the row
 * stops naming it and the header says it once. Seven rows all reading "payments-platform ·
 * review 4" is seven copies of a fact and no way to see the one thing that differs.
 */
function WantingRow({ item, hoisted }: { item: Wanting; hoisted: boolean }) {
  return (
    <li>
      <Link
        to={item.to}
        className="flex min-h-11 items-start gap-3 border-b border-rule px-4 py-2.5 transition last:border-b-0 hover:bg-surface-2 sm:px-5"
      >
        <Mark
          shape={item.glyph}
          className={cn("mt-[3px] size-[15px] shrink-0", TONE_TEXT[item.tone])}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[13px] font-medium text-ink">
            {item.title}
          </span>
          {item.claim ? (
            <span className="mt-0.5 block truncate text-[12.5px] leading-5 text-ink-2">
              {item.claim}
            </span>
          ) : null}
        </span>
        {hoisted ? (
          <span className="sr-only">{item.detail}</span>
        ) : (
          <span className="hidden min-w-0 shrink-0 truncate pt-0.5 font-mono text-[11px] text-ink-3 sm:block">
            {item.detail}
          </span>
        )}
        <ArrowRight className="mt-1 size-4 shrink-0 text-ink-3" aria-hidden="true" />
      </Link>
    </li>
  );
}

/**
 * The lineage as a trajectory: one node per revision, the delta drawn on the segment between.
 *
 * `+2 −1` between two nodes is what that revision actually did — two candidates raised, one
 * addressed — which is the only reason to keep review 3 once review 4 exists. Hues come from
 * the status table rather than being chosen here.
 */
function TrajectoryRail({ lineage }: { lineage: Lineage }) {
  const ordered = [...lineage.reviews].reverse();
  if (ordered.length < 2) return null;
  return (
    <ol
      aria-hidden="true"
      className="scrollbar-none -mx-1 flex items-start overflow-x-auto px-1 pb-0.5"
    >
      {ordered.map((review, index) => {
        const descriptor = statusOf(review.status);
        const moved = review.delta.new.length + review.delta.changed.length;
        const gone = review.delta.addressed.length;
        return (
          <li key={review.id} className="flex shrink-0 items-start">
            {index ? (
              <span className="flex w-16 flex-col items-center gap-1 pt-2">
                <span className="block h-px w-full bg-rule-strong" />
                <span className="font-mono text-[10px] leading-none text-ink-3">
                  {moved ? `+${moved}` : null}
                  {moved && gone ? " " : null}
                  {gone ? `−${gone}` : null}
                  {!moved && !gone ? "·" : null}
                </span>
              </span>
            ) : null}
            <span className="flex w-9 flex-col items-center gap-1">
              <Mark
                shape={descriptor.glyph}
                className={cn("size-[14px]", TONE_TEXT[descriptor.tone])}
              />
              <span className="font-mono text-[10px] leading-none tabular-nums text-ink-3">
                {review.sequence}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
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
  const counts = ["material", "held", "cleared"].map((verdict) => ({
    descriptor: verdictOf(verdict),
    count: review.findings.filter((finding) => finding.verdict === verdict).length,
  }));
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule px-4 py-2.5 transition hover:bg-surface-2 sm:px-5">
      <Link
        to={`/reviews/${review.id}`}
        className="flex min-h-9 min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1"
      >
        <span className="font-mono text-[13px] font-medium tabular-nums text-ink">
          Review {review.sequence}
        </span>
        <StatusBadge status={review.status} />
        <span className="font-mono text-[11px] text-ink-3">
          case rev {review.case.revision}
          {review.repository.commit ? <> · {shortId(review.repository.commit, 8)}</> : null} ·{" "}
          {relativeTime(review.started_at)}
        </span>
        {/* The verdict spread, in glyphs rather than in prose. "8 judged · 2 not cleared"
            made a reader subtract to learn the one thing they wanted. */}
        <span className="ml-auto flex shrink-0 items-center gap-2.5 font-mono text-[11.5px] tabular-nums">
          {counts.map(({ descriptor, count }) => (
            <span
              key={descriptor.label}
              className={cn("inline-flex items-center gap-1", count ? "text-ink-2" : "text-ink-3")}
            >
              <Mark
                shape={descriptor.glyph}
                className={cn("size-[13px]", count ? TONE_TEXT[descriptor.tone] : "text-ink-3")}
              />
              {count}
            </span>
          ))}
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
 * revision can be listed and opened while it is still being made.
 */
function PendingRow({ run, sequence }: { run: ReviewRun; sequence: number }) {
  return (
    <li className="border-t border-rule bg-surface-2">
      <Link
        to={`/runs/${run.run_id}`}
        className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 transition hover:bg-sunken sm:px-5"
      >
        <span className="font-mono text-[13px] font-medium tabular-nums text-ink">
          Review {run.sequence ?? sequence}
        </span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.13em] text-ink-3">
          <Spinner /> In progress
        </span>
        <span className="font-mono text-[11px] text-ink-3">
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
  const [expanded, setExpanded] = useState(false);
  // Only the newest revision spells itself out. The ones before it are on the rail, and are
  // one press away — a history is scanned far more often than it is read.
  const shown = expanded ? lineage.reviews : lineage.reviews.slice(0, 1);
  const hidden = lineage.reviews.length - shown.length;
  return (
    <Panel as="article">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[14px] leading-tight text-ink-3">
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
        <TrajectoryRail lineage={lineage} />
      </header>

      <ul>
        {lineage.run ? (
          <PendingRow run={lineage.run} sequence={lineage.reviews.length + 1} />
        ) : null}
        {shown.map((review) => (
          <RevisionRow
            key={review.id}
            review={review}
            deleting={deleting}
            onDelete={() => onDelete(review.id)}
          />
        ))}
      </ul>
      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex min-h-11 w-full items-center border-t border-rule px-4 text-[13px] font-semibold text-ink-2 transition hover:bg-surface-2 sm:px-5"
        >
          Show {hidden} older {hidden === 1 ? "revision" : "revisions"}
        </button>
      ) : null}
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

  const all = reviews.data ?? [];
  const visible = all.filter((review) => {
    const matchesStatus = status === "all" || review.status === status;
    const haystack = `${review.repository.path} ${review.repository.branch ?? ""}`.toLowerCase();
    return matchesStatus && haystack.includes(query.toLowerCase());
  });
  const lineages = lineagesOf(visible, runs.data ?? []);

  // What still wants a person needs the branch's standing decisions, and a decision belongs
  // to a branch rather than to a review — so one query per branch, through the same key the
  // workbench writes through, which means opening a review after this costs nothing.
  const branchIds = useMemo(
    () =>
      [
        ...new Set(
          lineages
            .map((lineage) => lineage.reviews[0]?.repository.branch_id)
            .filter(Boolean) as string[],
        ),
      ],
    [lineages],
  );
  const decisionQueries = useQueries({
    queries: branchIds.map((branchId) => ({
      queryKey: ["decisions", branchId],
      queryFn: () => api.decisions(branchId),
      retry: false,
    })),
  });
  const decisions = useMemo(() => {
    const byBranch = new Map<string, Map<string, Decision>>();
    decisionQueries.forEach((result, index) => {
      byBranch.set(
        branchIds[index],
        new Map((result.data?.decisions ?? []).map((item) => [item.candidate_id, item])),
      );
    });
    return byBranch;
  }, [decisionQueries, branchIds]);

  const wanting = useMemo(
    () => wantingOf(lineages.map((lineage) => lineage.reviews[0]).filter(Boolean), decisions),
    [lineages, decisions],
  );
  // Where everything outstanding is in one review, the review is said once above the list
  // instead of on every row — the same hoisting the queue does to a run of rows that repeat
  // each other. `detail` is the whole of what a row would repeat, so comparing it is enough.
  const openReviews = new Set(wanting.map((item) => item.review.id)).size;
  const shared = openReviews === 1 ? wanting[0]?.detail : null;

  if (reviews.isLoading) return <LoadingPanel label="Opening review history…" rows={4} />;
  if (reviews.error) return <ErrorNotice error={reviews.error} />;

  return (
    <div>
      <PageHeader
        eyebrow="Immutable history"
        title="Reviews"
        description="Reviews are sequenced per branch and case. Each one records the repository snapshot it read, the case revision it judged against, and the findings it composed — and each is readable exactly as it was recorded."
      />

      {/* ── The work, before the archive ────────────────────────────────────────────
          A returning reviewer is not asking which reviews exist. They are asking what wants
          them now, which is a fact about the candidates inside those reviews and not about
          the reviews themselves — so it is answered here, once, across every line of work,
          each row opening straight into the review that holds it. */}
      {wanting.length ? (
        <section aria-labelledby="wanting" className="mb-8">
          <div className="mb-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 id="wanting" className="text-[10px] font-bold uppercase tracking-[0.13em] text-ink">
              Waiting on you
            </h2>
            <span className="font-mono text-[11px] text-ink-3">
              {shared
                ? `${wanting.length} in ${shared}`
                : `${wanting.length} across ${openReviews} reviews`}
            </span>
          </div>
          <Panel>
            <ul>
              {wanting.slice(0, 8).map((item) => (
                <WantingRow key={item.key} item={item} hoisted={Boolean(shared)} />
              ))}
            </ul>
          </Panel>
          {wanting.length > 8 ? (
            <p className="mt-2 text-[12px] text-ink-3">
              {wanting.length - 8} more, listed inside the reviews below.
            </p>
          ) : null}
        </section>
      ) : null}

      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[10px] font-bold uppercase tracking-[0.13em] text-ink">
            Lines of work
          </h2>
          <span className="font-mono text-[11px] text-ink-3">
            {lineages.length === 1 ? "1 branch" : `${lineages.length} branches`} ·{" "}
            {all.length === 1 ? "1 revision" : `${all.length} revisions`} kept
          </span>
        </div>
        {all.length ? (
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput
              label="Search reviews"
              value={query}
              onValueChange={setQuery}
              placeholder="Repository or branch"
              className="w-full sm:w-64"
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
      </div>

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
