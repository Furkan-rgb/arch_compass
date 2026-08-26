import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, type Decision, type Finding, type Review, type ReviewRun } from "../../api";
import { cn } from "../../lib/cn";
import { runPollInterval, useRunsBecomeReviews } from "../../lib/runs";
import {
  VERDICT_ORDER,
  humanise,
  plural,
  relativeTime,
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
import { PathRef, TONE_EDGE, TONE_TEXT } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel } from "../../ui/panel";
import {
  EmptyState,
  ErrorNotice,
  LiveRegion,
  LoadingPanel,
  Notice,
  Spinner,
} from "../../ui/states";
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

/**
 * A checkout said as the segment that names it, under the segment above it.
 *
 * `repositoryName` keeps the last segment and nothing else, which is right on a page listing
 * repositories and wrong on a heading stacked over the full path. Two lineages under
 * `…/cases/boundary-review/repository` and `…/cases/layering-review/repository` both headed
 * *repository*, over a `PathRef` that elides from the head — so the one word the heading had
 * to itself was the one word the path beneath it already ended in, and the two lineages were
 * indistinguishable. The parent segment is the part that tells them apart, so it leads,
 * dimmed: it is where the thing is, and the name is what it is.
 */
function lineageIdentity(path: string): { parent: string | null; name: string } {
  const parts = path.split("/").filter(Boolean);
  return { parent: parts.length > 1 ? (parts.at(-2) ?? null) : null, name: parts.at(-1) || path };
}

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
 * How many steps of a lineage are drawn before the rail starts eliding.
 *
 * The same number, for the same reason, as `features/review/trajectory.tsx`: a branch
 * reviewed weekly for a quarter has a dozen revisions and the panel header has room for the
 * repository, the branch and about six nodes. This rail used to keep all of them and scroll,
 * with `scrollbar-none` on the scroller and macOS hiding overlay scrollbars anyway — so past
 * six revisions it ended mid-connector against the panel edge and read as a rendering fault.
 * Capping says out loud what scrolling hid, and the whole lineage is still in the sentence
 * below.
 */
const DRAWN_REVISIONS = 6;

/**
 * The lineage as a trajectory: one node per revision, the delta drawn on the segment between.
 *
 * `+2 −1` between two nodes is what that revision actually did — two candidates raised, one
 * addressed — which is the only reason to keep review 3 once review 4 exists. Hues come from
 * the status table rather than being chosen here, and the diff notation is drawn from
 * `ui/mark.tsx` rather than typed: `−` is U+2212, which the Plex Mono subset does not
 * promise, and a glyph that falls through to the system mono arrives at another optical size
 * on another baseline.
 */
function TrajectoryRail({ lineage }: { lineage: Lineage }) {
  const ordered = [...lineage.reviews].reverse();
  if (ordered.length < 2) return null;
  const drawn = ordered.slice(-DRAWN_REVISIONS);
  const elided = ordered.length - drawn.length;
  return (
    <>
      <p className="sr-only">{trajectorySentence(ordered)}</p>
      <ol aria-hidden="true" className="flex items-start pb-0.5">
        {elided ? (
          <li className="flex shrink-0 items-center self-stretch pr-2 font-mono text-[11px] tabular-nums text-ink-3">
            +{elided}
          </li>
        ) : null}
        {drawn.map((review, index) => {
          const descriptor = statusOf(review.status);
          const moved = review.delta.new.length + review.delta.changed.length;
          const gone = review.delta.addressed.length;
          return (
            <li key={review.id} className="flex shrink-0 items-start">
              {index || elided ? (
                <span className="flex w-12 flex-col items-center gap-1 pt-2 sm:w-16">
                  <span className="block h-px w-full bg-rule-strong" />
                  <span className="flex items-center gap-0.5 font-mono text-[10px] leading-none tabular-nums text-ink-3">
                    {moved ? (
                      <>
                        <Mark shape="plus" className="size-[12px]" />
                        {moved}
                      </>
                    ) : null}
                    {gone ? (
                      <>
                        <Mark shape="minus" className="size-[12px]" />
                        {gone}
                      </>
                    ) : null}
                    {!moved && !gone ? <Mark shape="equals" className="size-[12px]" /> : null}
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
  /**
   * Focus follows the swap, in both directions.
   *
   * Pressing Delete replaces the button that was pressed, so without this a keyboard user's
   * focus falls to `<body>` and reaching Confirm means tabbing from the top of the document —
   * on the one destructive action this page has. The first `button` inside the cell is
   * Confirm while the question is up and Delete once it is dismissed, so one query serves
   * both directions. `swapped` is what stops it stealing focus on the first render, where
   * `confirming` is false because nobody has done anything yet rather than because they
   * pressed Keep.
   */
  const controls = useRef<HTMLSpanElement>(null);
  const swapped = useRef(false);
  useEffect(() => {
    if (!confirming && !swapped.current) return;
    swapped.current = confirming;
    controls.current?.querySelector("button")?.focus();
  }, [confirming]);

  const descriptor = statusOf(review.status);
  const counts = VERDICT_ORDER.map((verdict) => ({
    descriptor: verdictOf(verdict),
    count: review.findings.filter((finding) => finding.verdict === verdict).length,
  }));
  return (
    <li
      className={cn(
        // The review's own state as a left edge, the device the docket row already uses for a
        // verdict — and a review's state is on the same register, graded rather than
        // described. It costs no horizontal space and is read without being looked at, which
        // is the question asked of a whole panel at once: which of these is still open. Only
        // `failed` is red; `awaiting_answers` is full ink and a completed revision recedes to
        // `--ink-3`, because held and cleared gave up their hues for weight.
        "group flex flex-wrap items-stretch border-t border-l-[3px] border-rule last:rounded-b-lg",
        TONE_EDGE[descriptor.tone],
      )}
    >
      {/*
        The padding, the hover and the 44px floor all live on the link rather than on the row.
        They were on the `<li>`, which meant the highlight ran under the Delete button and
        under the row's own dead space — a hover is a promise that pressing here goes
        somewhere, and two thirds of the lit area went nowhere. `--sunken` rather than
        `--surface-2` for the hover: white to `#fafafa` is five values out of 255, which is
        enough for a strip nobody is asked to notice and nothing at all for a state that has
        to appear under a pointer.
      */}
      <Link
        to={`/reviews/${review.id}`}
        className="flex min-h-11 min-w-0 flex-1 items-center gap-3 px-4 py-2.5 transition group-last:rounded-bl-lg hover:bg-sunken sm:px-5"
      >
        {/* The row's identity wraps; the verdict spread does not. `ml-auto` used to push the
            spread within whichever wrapped line it happened to land on, so three consecutive
            rows put their counts at three different heights and three different x-positions
            and never formed the column the treatment exists for. */}
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono text-[14px] font-medium tabular-nums text-ink">
            Review {review.sequence}
          </span>
          {/* The one thing on this row that means act, in the words the review's own head
              uses for it, and read before the state pill rather than after it: what a
              returning reader is looking for is how much work is left, not which of five
              statuses this revision is in. A zero is not drawn — a history is mostly settled
              revisions, and "nothing waiting on you" repeated down forty rows is forty lines
              spent saying that nothing happened. */}
          {wants ? (
            <span className="text-[13px] font-semibold text-ink">
              {plural(wants, "thing")} want{wants === 1 ? "s" : ""} you
            </span>
          ) : null}
          <StatusBadge status={review.status} />
          {run ? (
            <Label className="inline-flex items-center gap-1.5 text-ink-2">
              <Spinner label="" /> Rejudging · {run.stage ? stageLabel(run.stage) : "starting"}
            </Label>
          ) : null}
          <span className="font-mono text-[11px] text-ink-3">
            case rev {review.case.revision}
            {review.repository.commit ? (
              <> · {shortId(review.repository.commit, 8)}</>
            ) : null} · {relativeTime(review.started_at)}
          </span>
        </span>
        {/* The verdict spread, in glyphs rather than in prose. "8 judged · 2 not cleared"
            made a reader subtract to learn the one thing they wanted. The word is carried
            `sr-only` because `Mark` is `aria-hidden` — three bare digits in the middle of a
            link's accessible name name nothing — and a zero recedes on a laptop and goes
            below `sm`, which is the rule the review head applies to the same spread. */}
        <span className="flex shrink-0 items-center gap-2.5 font-mono text-xs tabular-nums">
          {counts.map(({ descriptor: verdict, count }) => (
            <span
              key={verdict.label}
              className={cn(
                "items-center gap-1",
                count ? "inline-flex text-ink-2" : "hidden text-ink-3 sm:inline-flex",
              )}
            >
              <Mark
                shape={verdict.glyph}
                className={cn("size-[13px]", count ? TONE_TEXT[verdict.tone] : "text-ink-3")}
              />
              {count}
              <span className="sr-only"> {verdict.label.toLowerCase()}</span>
            </span>
          ))}
        </span>
      </Link>

      {/* Its own line below `sm`, where the link wraps to four and a control left on the
          first flex line has nothing to sit against. */}
      <span
        ref={controls}
        className="flex w-full shrink-0 items-center justify-end gap-2 border-t border-rule px-4 py-2 sm:w-auto sm:border-t-0 sm:py-2.5 sm:pl-2 sm:pr-5"
      >
        {run ? (
          // Nothing is deleted while it is being rejudged, and the thing a person wants from
          // this row while that is happening is the run.
          <ButtonLink size="sm" variant="ghost" to={`/runs/${run.run_id}`}>
            Watch
          </ButtonLink>
        ) : confirming ? (
          <>
            {/* `role="alert"`, because the question replaces the control that asked it: a
                reader who is not looking at this row would otherwise be given a new,
                destructive choice with nothing announcing that it had appeared. */}
            <span role="alert" className="text-xs text-ink-3">
              Delete this review?
            </span>
            <Button size="sm" variant="danger" disabled={deleting} onClick={onDelete}>
              {deleting ? (
                <>
                  <Spinner label="" /> Deleting
                </>
              ) : (
                "Confirm"
              )}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </>
        ) : (
          // Present but quiet until the row is under a pointer or holds the keyboard — the
          // device the docket already uses for its select checkbox. A history is read far
          // more often than it is pruned, and a destructive control drawn at full strength on
          // every row of a list competes with the thing the list is for. On a coarse pointer
          // it is simply there: hover is what reveals it, and a finger has none.
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setConfirming(true)}
            aria-label={`Delete review ${review.sequence}`}
            className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100"
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
 *
 * It used to be the one row in the list with a ground of its own — `bg-surface-2` — on the
 * argument that a tint is what says this revision is being made right now. That tint is the
 * panel header's ground, and it sat directly beneath the panel header, so the only row a
 * reader could not press looked like a header and every row they could press looked like
 * nothing. What marks this row is what it says: a spinner, the word *In progress* and the
 * stage the run is on, all of which are drawn rather than dimmed and none of which is
 * borrowed from another part of the ramp.
 */
function PendingRow({ run, sequence }: { run: ReviewRun; sequence: number }) {
  return (
    <li className="group border-t border-l-[3px] border-rule border-l-transparent last:rounded-b-lg">
      <Link
        to={`/runs/${run.run_id}`}
        className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 transition group-last:rounded-b-lg hover:bg-sunken sm:px-5"
      >
        <span className="font-mono text-[14px] font-medium tabular-nums text-ink">
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
  deletingId,
}: {
  lineage: Lineage;
  /** How much still wants a person, by review id, for the revisions that know. */
  wants: Map<string, number>;
  onDelete: (id: string) => void;
  /** The review whose deletion is in flight, if any. */
  deletingId: string | null;
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
  const identity = lineageIdentity(lineage.path);
  return (
    <Panel as="article">
      {/* `bg-surface-2`, which is the ground the elevation contract gives a panel's header
          and every static strip set into a panel. The header used to be the panel's own
          white, the same white as the clickable rows beneath it, separated from them by one
          10%-black hairline — so nothing on the panel said which part of it did something.
          `rounded-t-lg` because a strip that paints to the edge is the part that notices the
          panel's 14px corner. */}
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-t-lg bg-surface-2 px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[14px] leading-tight text-ink-3">
            <span className="[overflow-wrap:anywhere]">
              {identity.parent ? <span className="text-ink-3">{identity.parent}/</span> : null}
              <span className="font-medium text-ink">{identity.name}</span>
            </span>
            {/* An unnamed branch is still a branch, and a lineage is keyed on the id whether
                or not a name came with it — so two lines of work on one repository used to
                draw the same heading with nothing after it. The id is what the record is
                filed under, and it is the only thing left that tells them apart. */}
            {lineage.branch || lineage.branchId ? (
              <>
                <GitBranchIcon className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="sr-only">branch</span>
                <span className="[overflow-wrap:anywhere]">
                  {lineage.branch ?? shortId(lineage.branchId ?? "", 8)}
                </span>
              </>
            ) : null}
          </h2>
          <PathRef path={lineage.path} className="mt-1" />
        </div>
        {/* A lineage of one has no trajectory to draw, which left the whole right half of the
            header empty on exactly the case a first-time reader meets. What goes there
            instead is the fact the rail would otherwise have carried: how much history this
            line of work has. */}
        {lineage.reviews.length > 1 ? (
          <TrajectoryRail lineage={lineage} />
        ) : lineage.reviews.length ? (
          <span className="font-mono text-[11px] tabular-nums text-ink-3">
            {plural(lineage.reviews.length, "revision")}
          </span>
        ) : null}
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
            deleting={deletingId === review.id}
            onDelete={() => onDelete(review.id)}
          />
        ))}
      </ul>
      {/* A toggle, not a one-way door. The comment above `shown` argues that a collapsed
          lineage is the right default because a history is scanned far more often than it is
          read — and this button used to disappear the moment it was pressed, so a lineage of
          thirty revisions stayed thirty rows tall for the rest of the session with no way
          back to the default the same argument asks for. */}
      {hidden > 0 || expanded ? (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          className="flex min-h-11 w-full items-center rounded-b-lg border-t border-rule px-4 text-[13px] font-semibold text-ink-2 transition hover:bg-sunken sm:px-5"
        >
          {expanded
            ? "Show fewer revisions"
            : `Show ${hidden} older ${hidden === 1 ? "revision" : "revisions"}`}
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
  /**
   * The search filter and the status filter are split, because the counts on the status
   * chips have to be counted off one and not the other.
   *
   * A chip saying how many revisions it would return is only true if it is counted against
   * everything the *other* control has already let through. Counted off `all` it would
   * ignore the search box — the same fault the "N revisions kept" line beside it used to
   * have — and counted off the fully filtered list every chip but the pressed one reads
   * zero.
   */
  const matching = useMemo(
    () =>
      all.filter((review) =>
        `${review.repository.path} ${review.repository.branch ?? ""}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [all, query],
  );
  const visible = useMemo(
    () => matching.filter((review) => status === "all" || review.status === status),
    [matching, status],
  );
  /**
   * How many revisions each status filter would return, and therefore which of them are worth
   * offering at all.
   *
   * On a healthy workspace four of the five return nothing, and a chip that empties the page
   * to an empty state is a dead end a reader was invited to walk into. The docket's filter
   * settled this rule and its comment calls it general: a count of zero is worth reading and
   * worth nothing to press.
   */
  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>(STATUS_FILTERS.map((item) => [item, 0]));
    for (const review of matching) {
      counts.set("all", (counts.get("all") ?? 0) + 1);
      if (counts.has(review.status))
        counts.set(review.status, (counts.get(review.status) ?? 0) + 1);
    }
    return counts;
  }, [matching]);
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
          {/* One notice for both listings, because they fail the same way and mean the same
              thing to a reader. The runs query is the only source of the pending row, the
              Rejudging label and the Watch button, so a failed poll used to remove the
              revision being made right now from a history that went on claiming to be
              complete — silently, on the page that polls precisely because somebody comes
              back to it. */}
          {reviews.isError || runs.isError ? (
            <Notice tone="working" className="mb-6">
              Lost contact with the workspace. This history may be out of date, and a review in
              progress may not be listed.
            </Notice>
          ) : null}

          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex items-baseline gap-3">
              <Label as="h2" className="text-ink">
                Lines of work
              </Label>
              {/* Two numbers about the same list, measured the same way. The left one said
                  "branches" and counted lineages, which are keyed on repository, branch
                  *and* case — so two cases on one branch printed as two branches. The right
                  one was counted off the unfiltered history, so a search commonly produced
                  "1 branch · 43 revisions kept" above four rows. */}
              <span className="font-mono text-[11px] tabular-nums text-ink-3">
                {plural(lineages.length, "line of work", "lines of work")} ·{" "}
                {visible.length !== all.length
                  ? `${plural(visible.length, "revision")} shown`
                  : all.length >= REVIEW_PAGE_SIZE
                    ? `showing the newest ${REVIEW_PAGE_SIZE}`
                    : `${plural(all.length, "revision")} kept`}
              </span>
            </div>
            {/* Drawn whenever there is any history at all, and the argument for a threshold
                is answered elsewhere. A search field and five chips beside a single row does
                look like furniture outweighing the work — but every chip now says how many
                revisions it would return and a chip that would return none cannot be
                pressed, so the strip states the shape of the history rather than offering
                five ways to empty it. Hiding the controls below some count would take a
                capability away at a number nothing could justify. */}
            {all.length ? (
              <div className="flex flex-wrap items-center gap-2">
                <SearchInput
                  label="Search reviews"
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Repository or branch"
                  className="w-full sm:w-64"
                />
                {/* `flex-wrap`, not a hidden-scrollbar scroller. macOS keeps overlay
                    scrollbars hidden until the trackpad is touched and `scrollbar-none`
                    removed them for good, so on a narrow viewport the strip simply ended
                    with two chips unreachable and nothing saying so. */}
                <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-1">
                  {STATUS_FILTERS.map((item) => {
                    const count = statusCounts.get(item) ?? 0;
                    return (
                      <ToggleButton
                        key={item}
                        pressed={status === item}
                        disabled={!count && status !== item}
                        onClick={() => setStatus(item)}
                      >
                        {humanise(item)}
                        <span className="tabular-nums">{count}</span>
                      </ToggleButton>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>

          {/* The list below changes under a search or a filter with nothing said about it, so
              a reader who is not looking at it has no way to learn whether their query
              matched. One region covers the arrival, the search and the filter. */}
          <LiveRegion>{plural(lineages.length, "line of work", "lines of work")} shown</LiveRegion>

          {!lineages.length ? (
            <EmptyState
              title={all.length ? "No review matches that" : "No reviews yet"}
              action={
                all.length ? (
                  // The empty state used to say to adjust the controls and then not offer to.
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setQuery("");
                      setStatus("all");
                    }}
                  >
                    Clear the filters
                  </Button>
                ) : (
                  <ButtonLink to="/start">Review a repository</ButtonLink>
                )
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
                  // Which review is being deleted, not whether any is. `remove.isPending`
                  // handed to every row disabled Confirm on a row nobody had touched.
                  deletingId={remove.isPending ? (remove.variables ?? null) : null}
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
