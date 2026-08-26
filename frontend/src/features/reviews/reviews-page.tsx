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
import { awaitsAnswers, needsAttention } from "../review/docket-rules";
import { StatusBadge } from "../../ui/badge";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { GitBranchIcon } from "../../ui/icons";
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
 * What still wants a person in this review, counted the way the review's own head counts it.
 *
 * This page used to answer "what wants me now" as a section of its own above the history: a
 * list of every open candidate across every lineage, each row opening into the review that
 * held it. It was the right question and the wrong place for the answer. The rows repeated
 * what the review below them already said, the section pushed the history it belonged to off
 * the fold, and reading a claim out of context — a candidate's summary with no verdict spread
 * and no revision around it — is the work, which is what opening the review is for.
 *
 * So the fact stays and the list goes. A review's row says how much of it wants a person, in
 * the same words the review's own head uses, and the claims are read where they can be acted
 * on. Two totals of the same list that disagree on two screens are worse than one, so this
 * counts exactly what `ReviewCounts` counts: candidates `needsAttention` still holds open,
 * plus the questions of a round that is still answerable.
 */
function wantsOf(review: Review, decisions: Map<string, Decision>): number {
  const outstanding = review.findings.filter((finding: Finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  ).length;
  return outstanding + (awaitsAnswers(review) ? review.questions.length : 0);
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
  wants,
  onDelete,
  deleting,
}: {
  review: Review;
  /** The run rejudging this very snapshot, where there is one. */
  run: ReviewRun | null;
  /**
   * How much of this revision still wants a person, or `null` where that is not known.
   *
   * `null` covers three cases on purpose, and all three are the same instruction: say
   * nothing. The branch's standing decisions have not arrived yet; they could not be read,
   * and a count taken without them names candidates the team settled weeks ago; or this is
   * not the newest revision of its lineage, where an outstanding candidate was either
   * carried into the revision above — which counts it — or went away.
   */
  wants: number | null;
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
        {/* The one thing on this row that means act, in the words the review's own head
            uses for it. A zero is not drawn: a history is mostly settled revisions, and
            "nothing waiting on you" repeated down forty rows is forty lines spent saying
            that nothing happened. */}
        {wants ? (
          <span className="text-[12.5px] font-semibold text-ink">
            {plural(wants, "thing")} want{wants === 1 ? "s" : ""} you
          </span>
        ) : null}
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
  wants,
  onDelete,
  deleting,
}: {
  lineage: Lineage;
  /** How much still wants a person, by review id, for the revisions that know. */
  wants: Map<string, number>;
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
            wants={wants.get(review.id) ?? null}
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
   * A row says how much of its revision still wants a person, and that is `needsAttention`
   * asked of every finding inside it — a summary carries verdict counts in their place, and
   * a verdict count cannot tell a candidate the team has already decided about from one
   * nobody has looked at. Everything else on this page would be happy with
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
  // every `useMemo` beneath them — including the one guarding the counts, which walk the
  // findings of every lineage on the page.
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
   * Which revision is the newest one is a fact about the line of work, not about what the
   * search box says, so it is read off the whole history. Read off the filtered list instead,
   * pressing **Completed** would promote the newest *completed* revision to newest — and a
   * superseded snapshot would then be the row claiming the branch's open work, while the
   * revision that actually carries it sits filtered out. A filtered-out newest simply leaves
   * the rows below it saying nothing, which is the honest answer.
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
   * `useMemo` that never hits, and every count below it would be recomputed on every
   * keystroke in the search box. `combine` is React Query's answer to exactly that, and it
   * has to be a stable reference for the same reason.
   *
   * Only a branch that actually answered is in the map. `needsAttention(finding, undefined)`
   * is true for anything not cleared, so a count taken before the decisions land — or after a
   * request for them failed — names everything the team settled weeks ago. `docket-rules.ts`
   * names that hazard on the hook the docket uses; this page was the second caller and had
   * not read it. A row with no entry here says nothing at all, which is the only honest
   * thing a number with nowhere to explain itself can do.
   */
  const combine = useCallback(
    (results: Array<UseQueryResult<Awaited<ReturnType<typeof api.decisions>>>>) =>
      new Map(
        results.flatMap((result, index) =>
          result.isSuccess
            ? ([
                [
                  branchIds[index],
                  new Map(result.data.decisions.map((item) => [item.candidate_id, item])),
                ],
              ] as Array<[string, Map<string, Decision>]>)
            : [],
        ),
      ),
    [branchIds],
  );
  const branches = useQueries({
    queries: branchIds.map((branchId) => ({
      queryKey: ["decisions", branchId],
      queryFn: () => api.decisions(branchId),
    })),
    combine,
  });

  /**
   * How much still wants a person, by review id — and only for the newest revision of each
   * line of work.
   *
   * An outstanding candidate in review 3 was either carried into review 4, where it is
   * counted, or it went away. Counting both would say the same open item twice down one
   * lineage, which is how a history comes to look like twice the work it is.
   */
  const wants = useMemo(() => {
    const counts = new Map<string, number>();
    for (const review of newest) {
      const decisions = branches.get(review.repository.branch_id ?? "");
      if (decisions) counts.set(review.id, wantsOf(review, decisions));
    }
    return counts;
  }, [newest, branches]);

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
                  wants={wants}
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
