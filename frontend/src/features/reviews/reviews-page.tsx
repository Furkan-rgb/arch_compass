import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, type Decision, type Finding, type Review, type ReviewRun } from "../../api";
import { cn } from "../../lib/cn";
import { runPollInterval, useRunsBecomeReviews } from "../../lib/runs";
import {
  humanise,
  plural,
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
import { PathRef, TONE_TEXT } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Notice, Spinner } from "../../ui/states";
import { stageLabel } from "../start/run-progress";

const STATUS_FILTERS = ["all", "completed", "awaiting_answers", "failed", "cancelled"] as const;

/**
 * How many revisions `/api/reviews` answers with unless somebody asks for more.
 *
 * The route's `limit` defaults to 100, and this page does not raise it. A full array is
 * therefore a page rather than a total, and the header used to report it as one — "100
 * revisions kept" while review 101 sat unlisted and unmentioned.
 */
const REVIEW_PAGE_SIZE = 100;

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

/** The three things a review is sequenced under, as one key. */
function lineageKeyOf(review: Review): string {
  return `${review.repository.path}::${review.repository.branch_id}::${review.case.id}`;
}

function lineagesOf(reviews: Review[], runs: ReviewRun[], now = Date.now()): Lineage[] {
  const groups = new Map<string, Lineage>();
  for (const review of reviews) {
    const key = lineageKeyOf(review);
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
    .sort((left, right) => latestAt(right, now) - latestAt(left, now));
}

/**
 * When this lineage last did anything.
 *
 * A run counts, because a lineage being worked on right now is the one somebody came here
 * to look at. It counts from its own `started_at`, which the run carries on the wire: this
 * read `Date.now()` inside the comparator before, and a comparator that answers differently
 * every time it is asked is not an ordering.
 */
function latestAt(lineage: Lineage, now: number): number {
  const started = lineage.run ? Date.parse(lineage.run.started_at ?? "") : Number.NaN;
  const run = lineage.run ? (Number.isNaN(started) ? now : started) : Number.NEGATIVE_INFINITY;
  const newest = Date.parse(lineage.reviews[0]?.started_at ?? "");
  return Math.max(run, Number.isNaN(newest) ? Number.NEGATIVE_INFINITY : newest);
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
 * The rail, said as a sentence, for anybody who is not looking at it.
 *
 * "Nothing on the page showed that review 4 succeeded review 3" is the fault this page was
 * redesigned to fix, and the rail is the whole of the fix — so a rail carrying
 * `aria-hidden` handed a screen reader a list of reviews with the relationship between them
 * removed. The marks themselves stay hidden: a row of glyphs and bare numbers announces
 * nothing useful. What replaces them is what they draw.
 */
function trajectorySentence(ordered: Review[]): string {
  const clauses = ordered.map((review, index) => {
    const moved = review.delta.new.length + review.delta.changed.length;
    const gone = review.delta.addressed.length;
    const changes = [moved ? `${moved} raised` : null, gone ? `${gone} addressed` : null]
      .filter(Boolean)
      .join(" and ");
    // The delta belongs to the step *into* a revision, which is where the rail draws it, so
    // the first revision on the rail has none to state.
    const revision = `review ${review.sequence}`;
    return index && changes ? `${revision} with ${changes}` : revision;
  });
  const sentence = clauses.map((clause, index) => (index ? `then ${clause}` : clause)).join(", ");
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
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
    <>
      <p className="sr-only">{trajectorySentence(ordered)}</p>
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
    </>
  );
}

function RevisionRow({
  review,
  run,
  onDelete,
  deleting,
}: {
  review: Review;
  /** The run rejudging this very snapshot, where there is one. */
  run: ReviewRun | null;
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
        {run ? (
          <Label className="inline-flex items-center gap-1.5 text-ink-2">
            <Spinner label="" /> Rejudging · {run.stage ? stageLabel(run.stage) : "starting"}
          </Label>
        ) : null}
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
        {run ? (
          // Nothing is deleted while it is being rejudged, and the thing a person wants from
          // this row while that is happening is the run.
          <ButtonLink size="sm" variant="ghost" to={`/runs/${run.run_id}`}>
            Watch
          </ButtonLink>
        ) : confirming ? (
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
        <Label className="inline-flex items-center gap-1.5">
          <Spinner label="" /> In progress
        </Label>
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
  /**
   * A listed run may name a review it is already attached to.
   *
   * Answering a clarification round rejudges the snapshot that asked the questions, and the
   * run reports until it is genuinely done — so for the length of that rejudgement the run
   * list and the review list both describe revision N. Drawn as they arrive that is two rows
   * for one revision, one of them claiming to be the next one. The run is keyed on its
   * `review_id` instead and drawn on the row it belongs to.
   */
  const rejudging = lineage.run?.review_id ?? null;
  const pending = lineage.run && !lineage.reviews.some((review) => review.id === rejudging);
  // Only the newest revision spells itself out. The ones before it are on the rail, and are
  // one press away — a history is scanned far more often than it is read. The exception is a
  // revision being rejudged: something happening now is not something to go looking for.
  const shown = expanded
    ? lineage.reviews
    : lineage.reviews.filter((review, index) => index === 0 || review.id === rejudging);
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
          <PathRef path={lineage.path} className="mt-1" />
        </div>
        <TrajectoryRail lineage={lineage} />
      </header>

      <ul>
        {pending && lineage.run ? (
          <PendingRow run={lineage.run} sequence={lineage.reviews.length + 1} />
        ) : null}
        {shown.map((review) => (
          <RevisionRow
            key={review.id}
            review={review}
            run={review.id === rejudging ? lineage.run : null}
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
  /**
   * The whole reviews, not the summaries, and this is the one listing that cannot move.
   *
   * "Waiting on you" asks `needsAttention` of every finding in the newest revision of every
   * lineage, and that is a fact about the findings inside a review — a summary carries
   * counts in their place. Everything else on this page would be happy with
   * `api.reviewSummaries()`; asking for both would fetch the same rows twice.
   */
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  // Polled while anything is in flight, and only then: this is the page a reader comes back
  // to, so a run that finished while they were away has to become a review without a reload.
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => runPollInterval(query.state.data),
  });
  useRunsBecomeReviews(runs.data);
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteReview(id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  // Every derived list below is memoised, and the reason is the search box. `visible` and
  // `lineages` were rebuilt with fresh array identity on every keystroke, which defeated
  // every `useMemo` beneath them — including the one guarding `wantingOf`, which sorts the
  // findings of every lineage it is handed.
  const all = useMemo(() => reviews.data ?? [], [reviews.data]);
  const visible = useMemo(
    () =>
      all.filter((review) => {
        const matchesStatus = status === "all" || review.status === status;
        const haystack =
          `${review.repository.path} ${review.repository.branch ?? ""}`.toLowerCase();
        return matchesStatus && haystack.includes(query.toLowerCase());
      }),
    [all, status, query],
  );
  const lineages = useMemo(() => lineagesOf(visible, runs.data ?? []), [visible, runs.data]);

  /**
   * The newest revision of every line of work, whatever the filters above are set to.
   *
   * This used to be read off the filtered list, which made the status filter change what
   * "Waiting on you" said. Pressing **Completed** removed every review awaiting answers —
   * and with them every open clarification question, out of the one section on the page that
   * exists to surface them, with the control that did it sitting *below* the section it
   * emptied. The filter belongs to "Lines of work" and to nothing else.
   */
  const newest = useMemo(() => {
    const byLineage = new Map<string, Review>();
    for (const review of all) {
      const key = lineageKeyOf(review);
      const held = byLineage.get(key);
      if (!held || review.sequence > held.sequence) byLineage.set(key, review);
    }
    return [...byLineage.values()];
  }, [all]);

  // What still wants a person needs the branch's standing decisions, and a decision belongs
  // to a branch rather than to a review — so one query per branch, through the same key the
  // workbench writes through, which means opening a review after this costs nothing.
  const branchIds = useMemo(
    () => [...new Set(newest.map((review) => review.repository.branch_id).filter(Boolean))],
    [newest],
  );
  /**
   * `combine` rather than a `useMemo` over the results.
   *
   * `useQueries` hands back a fresh array on every render, so a `useMemo` keyed on it is a
   * `useMemo` that never hits — which is how the sort inside `wantingOf` came to run on
   * every keystroke. `combine` is React Query's answer to exactly that, and it has to be a
   * stable reference for the same reason.
   */
  const combine = useCallback(
    (results: Array<UseQueryResult<Awaited<ReturnType<typeof api.decisions>>>>) => ({
      byBranch: new Map(
        results.map((result, index) => [
          branchIds[index],
          new Map((result.data?.decisions ?? []).map((item) => [item.candidate_id, item])),
        ]),
      ),
      /**
       * Whether every branch has actually answered.
       *
       * `needsAttention(finding, undefined)` is true for anything not cleared, so a page
       * that groups before the decisions land lists everything the team settled weeks ago
       * and then shrinks as the answers arrive. `docket-rules.ts` names this hazard on the
       * hook the docket uses; this was the second caller and it had not read it.
       */
      ready: results.every((result) => result.isSuccess || result.isError),
      /** A branch whose decisions could not be read can only make this list too long. */
      failed: results.some((result) => result.isError),
    }),
    [branchIds],
  );
  const branches = useQueries({
    queries: branchIds.map((branchId) => ({
      queryKey: ["decisions", branchId],
      queryFn: () => api.decisions(branchId),
    })),
    combine,
  });

  const wanting = useMemo(
    () => (branches.ready ? wantingOf(newest, branches.byBranch) : []),
    [newest, branches],
  );
  // Where everything outstanding is in one review, the review is said once above the list
  // instead of on every row — the same hoisting the queue does to a run of rows that repeat
  // each other. `detail` is the whole of what a row would repeat, so comparing it is enough.
  const openReviews = new Set(wanting.map((item) => item.review.id)).size;
  const shared = openReviews === 1 ? wanting[0]?.detail : null;
  // Nothing is claimed until the branches have answered, and the section stays on screen
  // while they do rather than appearing at whatever size the answer turns out to be.
  const showWanting = Boolean(newest.length) && (!branches.ready || wanting.length > 0);

  return (
    <div>
      <PageHeader
        eyebrow="Immutable history"
        title="Reviews"
        description="Sequenced per branch and case, and readable exactly as recorded."
      />

      {reviews.isPending ? (
        <LoadingPanel label="Opening review history…" rows={4} />
      ) : !reviews.data ? (
        // The header stays. A page that replaces itself with its own error message takes
        // away the one thing left to do about it, which is go somewhere else.
        <ErrorNotice
          error={reviews.error}
          action={
            <Button size="sm" variant="secondary" onClick={() => void reviews.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          {reviews.isError ? (
            <Notice tone="working" className="mb-6">
              Lost contact with the workspace. This history may be out of date.
            </Notice>
          ) : null}

          {/* ── The work, before the archive ──────────────────────────────────
              A returning reviewer is not asking which reviews exist. They are asking what
              wants them now, which is a fact about the candidates inside those reviews and
              not about the reviews themselves — so it is answered here, once, across every
              line of work, each row opening straight into the review that holds it. */}
          {showWanting ? (
            <section aria-labelledby="wanting" className="mb-8">
              <div className="mb-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <Label as="h2" id="wanting" className="text-ink">
                  Waiting on you
                </Label>
                {branches.ready ? (
                  <span className="font-mono text-[11px] text-ink-3">
                    {shared
                      ? `${wanting.length} in ${shared}`
                      : `${wanting.length} across ${plural(openReviews, "review")}`}
                  </span>
                ) : null}
              </div>
              <Panel>
                {branches.ready ? (
                  <ul>
                    {wanting.slice(0, 8).map((item) => (
                      <WantingRow key={item.key} item={item} hoisted={Boolean(shared)} />
                    ))}
                  </ul>
                ) : (
                  <p className="flex min-h-11 items-center gap-2.5 px-4 py-2.5 text-[13px] text-ink-3 sm:px-5">
                    <Spinner label="" /> Reading what these branches have already settled…
                  </p>
                )}
              </Panel>
              {branches.failed ? (
                <p className="mt-2 text-[12px] text-ink-3">
                  Some standing decisions could not be read, so this list may name candidates the
                  team has already settled.
                </p>
              ) : null}
              {wanting.length > 8 ? (
                <p className="mt-2 text-[12px] text-ink-3">
                  {wanting.length - 8} more, listed inside the reviews below.
                </p>
              ) : null}
            </section>
          ) : null}

          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex items-baseline gap-3">
              <Label as="h2" className="text-ink">
                Lines of work
              </Label>
              <span className="font-mono text-[11px] text-ink-3">
                {plural(lineages.length, "branch", "branches")} ·{" "}
                {all.length >= REVIEW_PAGE_SIZE
                  ? `showing the newest ${REVIEW_PAGE_SIZE}`
                  : `${plural(all.length, "revision")} kept`}
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
                    <ToggleButton
                      key={item}
                      pressed={status === item}
                      onClick={() => setStatus(item)}
                    >
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
              action={
                all.length ? undefined : <ButtonLink to="/start">Review a repository</ButtonLink>
              }
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
          {/* A delete that failed is reported by the toast `main.tsx` puts under every
              mutation. It used to paint an `ErrorNotice` at the foot of the page, a screen
              away from the row the button was on. */}
        </>
      )}
    </div>
  );
}
