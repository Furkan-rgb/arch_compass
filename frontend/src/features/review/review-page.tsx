import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { runPollInterval, useRecordToFollow, useRunsBecomeReviews } from "../../lib/runs";
import {
  VERDICT_ORDER,
  plural,
  relativeTime,
  repositoryName,
  shortId,
  verdictOf,
} from "../../lib/format";
import { StatusBadge } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Drawer } from "../../ui/drawer";
import { TONE_TEXT } from "../../ui/meta";
import { Mark } from "../../ui/mark";
import { Label, Panel, PanelFooter } from "../../ui/panel";
import { ErrorNotice, LoadingPanel, Notice } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import {
  type QueueFilter,
  awaitsAnswers,
  needsAttention,
  orderedFindings,
  useStandingDecisions,
} from "./docket-rules";
import { AtlasSurface } from "./atlas-surface";
import { useRoundAnswers } from "./clarification";
import { ClarificationsSurface } from "./clarifications-surface";
import { ContextRail } from "./context-rail";
import { Docket } from "./docket";
import { RunProgress, useRejudgementNotice } from "../start/run-progress";
import { RevisionRail, lineageOf } from "./revision-rail";
import { AskSurface, DeltaSurface } from "./surfaces";

/**
 * The report arrives with the tab, and not before.
 *
 * It is the only surface here that renders authored prose, so it is the only one that needs
 * the Markdown engine — some 160KB of it, which `surfaces.tsx` used to pull into the review's
 * own chunk for a tab that is not the default. Four of the five tabs never touch it.
 */
const ReportSurface = lazy(() =>
  import("./report-surface").then((module) => ({ default: module.ReportSurface })),
);

/**
 * What the page is showing.
 *
 * `Docket` is the review — the list and the assessments, which are the same thing. The other
 * three are documents about the review rather than modes of working through it, which is why
 * they are peers of it rather than columns beside it.
 */
const SURFACES = [
  { id: "docket", label: "Docket" },
  { id: "rounds", label: "Rounds" },
  { id: "atlas", label: "Atlas" },
  { id: "delta", label: "Delta" },
  { id: "report", label: "Report" },
  { id: "ask", label: "Ask" },
];

/**
 * The docket is the review, so it is what a bare `/reviews/:id` means.
 *
 * It carries no parameter of its own rather than `?tab=docket`: arriving at a review and
 * arriving at its docket are the same arrival, and rewriting the URL on mount to say so
 * would put a second entry in the reader's history for every review they open.
 */
const DEFAULT_SURFACE = "docket";

/** What names the surface in a link: `/reviews/:id?tab=atlas`. */
const SURFACE_PARAM = "tab";

/**
 * What names one finding in a link: `/reviews/:id?candidate=<id>`.
 *
 * Read on arrival and never written afterwards, which is the whole of the distinction the
 * experience doc draws: *which document you are reading is where you are, and your position
 * inside the docket is what you were doing there.* That argument is about walking the list,
 * and it holds — a parameter rewritten on every `j` would put forty entries in the reader's
 * history. It does not cover handing a colleague one finding, which without this means
 * "open review 4, set the filter to All, and scroll to InvoiceGateway".
 */
const CANDIDATE_PARAM = "candidate";

/**
 * The one number in the head that means act, and the verdict spread behind it.
 *
 * A reviewer arrives with two questions — is anything waiting on me, and what is it — and the
 * head used to answer neither: the largest type on it was the repository's name, the fact its
 * reader was least in doubt about.
 *
 * Counts are orientation, read once, on the way to the work, so this is a line and not a
 * dashboard. The leading count is deliberately plain ink even where most of what it counts is
 * material: a hue on a mixed total would be a verdict painted on something that is not one.
 */
function ReviewCounts({
  review,
  findings,
  className,
}: {
  review: Review;
  /** The same sorted list the docket is showing, sorted once by the page for both. */
  findings: Finding[];
  className?: string;
}) {
  const { byCandidate: decisions } = useStandingDecisions(review);

  const outstanding = findings.filter((finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  ).length;
  const waiting = awaitsAnswers(review);
  // The open clarification wants a person as much as any candidate does, and the docket lists
  // it as the first item, so the head counts it as one. Two totals of the same list that
  // disagree on one screen are worse than one total nobody reads — which is what this was,
  // because it added `questions.length` rather than one: a held review with five outstanding
  // candidates and four questions said "9 things still want you" forty pixels above a chip
  // reading "Attention 5". Nothing is lost by counting the round once; the sentence directly
  // below this already names how many questions are unanswered.
  const wants = outstanding + (waiting ? 1 : 0);

  const asked = new Set(review.questions.flatMap((question) => question.candidate_ids));
  const blocked = findings.filter((finding) => asked.has(finding.candidate.id)).length;
  const questions = plural(review.questions.length, "unanswered question");

  if (!findings.length && !waiting) return null;

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-ink-3">
        <span className="font-semibold text-ink">
          {wants
            ? `${plural(wants, "thing")} still want${wants === 1 ? "s" : ""} you`
            : "Nothing waiting on you"}
        </span>
        <span aria-hidden="true" className="hidden h-3 w-px bg-rule sm:block" />
        {VERDICT_ORDER.map((verdict) => {
          const descriptor = verdictOf(verdict);
          const count = findings.filter((finding) => finding.verdict === verdict).length;
          return (
            <span
              key={verdict}
              className={cn(
                "items-center gap-1.5",
                // A zero recedes on a laptop and disappears on a phone. "0 material" is worth
                // a glance where there is room for the whole scale; where there is not, it is
                // a line of the viewport spent saying nothing happened.
                count ? "inline-flex text-ink-2" : "hidden text-ink-3 sm:inline-flex",
              )}
            >
              <Mark
                shape={descriptor.glyph}
                className={cn("size-[13px]", count ? TONE_TEXT[descriptor.tone] : "text-ink-3")}
              />
              <span className={cn("font-mono tabular-nums", count > 0 && "font-semibold text-ink")}>
                {count}
              </span>
              {descriptor.label.toLowerCase()}
            </span>
          );
        })}
      </div>

      {/* One sentence, in the same ink as anything else that is read rather than acted on.
          No tint, no rule, no button: the answer is given inside the item that holds the
          question, which is the only place it is asked for. */}
      {waiting ? (
        <p className="mt-1 text-[12px] leading-[1.45] text-ink-3">
          {blocked
            ? `${blocked === outstanding && blocked > 1 ? "All " : ""}${plural(
                blocked,
                "candidate",
              )} ${blocked === 1 ? "is" : "are"} waiting on ${questions}, answered at the top of the docket.`
            : `This review is held on ${questions}.`}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Which review this is, in one line.
 *
 * What identifies a review is the repository, the branch and the commit it read — not the
 * phrase "Architecture review", which used to be set at 30px above every one of them.
 */
/**
 * Said at the top of a page every part of which is about a moment that has passed.
 *
 * A revision is recorded once per round it waits in and once more when it finishes, so review
 * 2 can be three records under one number. The listing keeps the newest of them — one entry
 * per revision, which is right — and that leaves the earlier records reachable by the URL
 * somebody is already holding and by nothing else. Reading one, a person saw a review waiting
 * on questions they had answered an hour before, a docket of verdicts that had since moved,
 * and a report composed before their answers existed. Every word of it was true about the
 * moment it was recorded; none of it was true now, and nothing on the page said which.
 *
 * The report is named because that is where it was first noticed, and because it is the one
 * surface here that reads like a document rather than like a live view — a document with no
 * date on it is one a reader assumes is current.
 */
/**
 * What became of the review since this record was taken.
 *
 * The status of the record the execution now stands on, which is a fact about the *review*
 * and is said here for that reason and nowhere else. Two surfaces read it as a fact about the
 * round this record asked and both said something false with it: for round one of a review
 * that was cancelled at round two it says `cancelled`, over an answer that was given.
 */
function supersededSince(review: Review): string {
  const sequence = review.sequence;
  switch (review.superseded_by_status) {
    case "completed":
      return `Review ${sequence} has finished since.`;
    case "cancelled":
      return `Review ${sequence} was stopped since.`;
    case "failed":
      return `Review ${sequence} did not finish.`;
    case "awaiting_answers":
      // What it did, not what it is doing. A snapshot that asked says `awaiting_answers` for
      // ever, including while its own round is being judged and after its run has died — so
      // "is waiting on that round" is the present-tense claim this whole page stopped making.
      return `Review ${sequence} asked again since.`;
    default:
      return `Review ${sequence} has moved on since.`;
  }
}

function SupersededNotice({ review }: { review: Review }) {
  return (
    <div className="mx-auto w-full max-w-[76rem] px-4 pt-4 sm:px-6">
      <Notice tone="working">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p className="min-w-0 text-[13px] leading-6 text-ink-2">
            <span className="font-semibold text-ink">
              This is an earlier record of review {review.sequence}
            </span>{" "}
            — round {review.round}, as it stood when it was recorded. Its findings, its
            questions and its report are all that moment. {supersededSince(review)}
          </p>
          <ButtonLink to={`/reviews/${review.superseded_by}`} variant="secondary">
            Read the current record
          </ButtonLink>
        </div>
      </Notice>
    </div>
  );
}

function ReviewHead({
  review,
  findings,
  onCancel,
  cancelling,
  failure,
}: {
  review: Review;
  findings: Finding[];
  onCancel: () => void;
  cancelling: boolean;
  /** A cancellation that did not go through, which used to be reported nowhere at all. */
  failure?: unknown;
}) {
  const waiting = awaitsAnswers(review);
  return (
    <header className="border-b border-rule bg-surface">
      <div className="mx-auto w-full max-w-[76rem] px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
            <h1
              title={review.repository.path}
              className="flex min-w-0 flex-wrap items-baseline gap-x-2 font-mono text-[15px] leading-tight tracking-[-0.01em] text-ink-3 sm:text-[17px]"
            >
              <span className="font-medium text-ink [overflow-wrap:anywhere]">
                {repositoryName(review.repository.path)}
              </span>
              {review.repository.branch ? (
                <>
                  <span aria-hidden="true">/</span>
                  <span className="[overflow-wrap:anywhere]">{review.repository.branch}</span>
                </>
              ) : null}
              {review.repository.commit ? (
                <span className="text-[0.8em]">{shortId(review.repository.commit, 10)}</span>
              ) : null}
            </h1>
            <Label>
              Review {review.sequence} · case revision {review.case.revision} ·{" "}
              {review.round > 1 ? <>round {review.round} · </> : null}
              {relativeTime(review.started_at)}
            </Label>
          </div>

          {/* One control, and it is the way out rather than the way on. */}
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status={review.status} />
            {waiting ? (
              <Button variant="secondary" size="sm" disabled={cancelling} onClick={onCancel}>
                Cancel review
              </Button>
            ) : (
              <ButtonLink to="/start" variant="secondary" size="sm">
                New review
              </ButtonLink>
            )}
          </div>
        </div>

        <ReviewCounts review={review} findings={findings} className="mt-2" />

        {/* A cancellation that failed used to be swallowed whole: the button re-enabled, the
            review carried on waiting, and nothing said why. It belongs beside the control
            that was pressed. */}
        {failure ? (
          <div className="mt-2.5">
            <ErrorNotice
              error={failure}
              title="This review was not cancelled"
              action={
                <Button variant="secondary" size="sm" disabled={cancelling} onClick={onCancel}>
                  Try again
                </Button>
              }
            />
          </div>
        ) : null}
      </div>
    </header>
  );
}

export function ReviewPage() {
  const { reviewId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const requestedSurface = search.get(SURFACE_PARAM) ?? undefined;
  const navigate = useNavigate();
  const client = useQueryClient();

  /**
   * Which surface is on screen, read from the URL rather than held in state.
   *
   * A tab that only lives in memory is a tab that cannot be linked to, refreshed onto, or
   * opened in a second window beside the first — and this page's tabs are six documents
   * about one review, which is exactly the kind of thing somebody sends to a colleague.
   *
   * A query parameter rather than a path segment, which is the less pretty of the two and
   * the only one that works. `/reviews/:id/:surface?` and a nested `:surface` child both
   * change which route variant the URL matches, and in this app — two levels of `<Routes>`
   * inside a `<Suspense>` around lazy pages — that remounts the page. Remounting costs the
   * reader the row they had open, the filter they set and their scroll, which is the exact
   * promise `docs/experience.md` makes about leaving a surface and coming back. A parameter
   * never changes the match, so the page is never rebuilt. There is a test for it.
   *
   * An unrecognised value falls back to the docket rather than rendering nothing, and the
   * fallback is silent: `?tab=atals` shows the review, which is what the reader was asking
   * for, and the tab strip says where they actually landed.
   */
  const surface = SURFACES.some((item) => item.id === requestedSurface)
    ? requestedSurface!
    : DEFAULT_SURFACE;
  const setSurface = (next: string) =>
    setSearch((current) => {
      const params = new URLSearchParams(current);
      if (next === DEFAULT_SURFACE) params.delete(SURFACE_PARAM);
      else params.set(SURFACE_PARAM, next);
      return params;
    });

  const [filter, setFilter] = useState<QueueFilter>("attention");
  /**
   * Which review this page has already chosen an opening filter for.
   *
   * A ref rather than state because choosing must not itself be a render, and per review
   * rather than once because the route carries no key — walking to another revision does not
   * remount this page, and a page that chose once would open every later review on whatever
   * the last one wanted.
   */
  const openedFilterFor = useRef<string | null>(null);
  /**
   * Which row is open, once somebody or something has chosen. `undefined` means nobody has,
   * and the page falls back to `defaultOpen` below — three states rather than two, because
   * "closed everything deliberately" and "has not chosen yet" are different and the second
   * one must not win over the first.
   */
  const [openId, setOpenId] = useState<string | null | undefined>(undefined);
  const [contextOpen, setContextOpen] = useState(false);
  /**
   * Which tab of the judgement-context drawer is open.
   *
   * Here rather than in the drawer, which unmounts its contents when it closes: a reviewer
   * checking Policies on twenty consecutive candidates was pressing Policies twenty times.
   */
  const [contextTab, setContextTab] = useState("case");
  /**
   * What the reviewer has typed into the clarification round, and what they have checked for
   * a bulk decision, and which rows settled under them this session.
   *
   * All three are "what you were doing there", and all three used to live inside components
   * that a tab switch, a keystroke or a collapsed card unmounts. The round's answers are the
   * worst of them — the experience doc's rule is *never navigate away from unsaved input*,
   * and pressing `j` with the round open threw away every answer in it.
   */
  const answers = useRoundAnswers();
  const [settledHere, setSettledHere] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);

  const review = useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => api.review(reviewId),
    // A review is a record, not a message. It is immutable and sequenced per branch and case
    // — the charter's third commitment — so nothing about it can come back different, and
    // the five-second default had every remount re-download 180KB to redraw the same page.
    staleTime: Infinity,
  });
  /**
   * The lineage, as a list rather than as a stack of reviews.
   *
   * A stored review is most of a repository's atlas, and the rail under the docket draws a
   * number, a state and a date off each entry — so the summary listing is exactly what it
   * needs, and asking for the whole thing was megabytes a row to draw a line of text.
   */
  const summaries = useQuery({ queryKey: ["reviews", "summary"], queryFn: api.reviewSummaries });
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => runPollInterval(query.state.data),
  });
  // A run leaving that list is a review arriving. Polling it and not acting on the change is
  // what left a finished background run invisible until a reload.
  useRunsBecomeReviews(runs.data);
  const cancel = useMutation({
    mutationFn: () => api.cancel(reviewId),
    onSuccess: async (next) => {
      // `["review"]` as well, and by prefix. `["reviews"]` does not reach `["review", id]`,
      // which holds the snapshot this cancellation just superseded and is `staleTime:
      // Infinity` — so its `answerable` and `superseded_by` were never refetched, and a
      // reader who came back to it was still offered the form and the Cancel button for a
      // round the server would refuse. Those two fields are the first mutable things on an
      // otherwise immutable record, which is why nothing had needed to invalidate it before.
      await Promise.all([
        client.invalidateQueries({ queryKey: ["reviews"] }),
        client.invalidateQueries({ queryKey: ["review"] }),
      ]);
      navigate(`/reviews/${next.id}`);
    },
  });

  const value = review.data;
  const { byCandidate: decisions, ready } = useStandingDecisions(value);

  /**
   * The order a reviewer meets candidates in, sorted once for everything that shows it.
   *
   * The head's counts and the docket both want this list, and each of them used to sort the
   * whole review for itself — on every render of this page, which is every keystroke, every
   * filter press, every drawer toggle and every four-second run poll.
   */
  const findings = useMemo(() => (value ? orderedFindings(value) : []), [value]);

  /** The lineage this review belongs to, oldest first. */
  const lineage = useMemo(
    () =>
      value
        ? [...lineageOf(summaries.data ?? [], value.repository.branch_id, value.case.id)].sort(
            (left, right) => left.sequence - right.sequence,
          )
        : [],
    [summaries.data, value],
  );

  /**
   * The reviews themselves, and only where there is a trajectory to draw with them.
   *
   * A candidate's trajectory is the verdict each revision reached about it, which is a fact
   * that lives inside each review's findings and cannot be read off a listing. So this is the
   * heavy request, and it is asked for only when the lineage the rail drew says there is more
   * than one revision — which on a first review, the common case, means it is never made.
   */
  const revisions = useQuery({
    queryKey: ["reviews"],
    queryFn: api.reviews,
    enabled: lineage.length > 1,
    // No `staleTime: Infinity` here, unlike the review itself: each *review* in this list is
    // immutable, the list is not — a run finishing adds a revision, and a trajectory that
    // could never learn about it would be a strip that stops at the day the tab was opened.
  });
  const trajectory = useMemo(
    () =>
      value && revisions.data
        ? [...lineageOf(revisions.data, value.repository.branch_id, value.case.id)].sort(
            (left, right) => left.sequence - right.sequence,
          )
        : [],
    [revisions.data, value],
  );

  /**
   * The run making a revision of this lineage, if one is in flight.
   *
   * Declared above `defaultOpen` because that memo reads it — both in its body and in its
   * dependency list, which is evaluated the moment the memo is reached. Thirty lines further
   * down it was a temporal dead zone, and the render threw.
   */
  const pendingRun =
    (value &&
      (runs.data ?? []).find(
        (run) => run.branch_id === value.repository.branch_id && run.case_id === value.case.id,
      )) ||
    null;

  /**
   * The run that is *this revision* being judged again, which is a narrower thing.
   *
   * `pendingRun` matches on branch and case, which is right for the lineage rail — any run of
   * this lineage is an entry in it. It is wrong for the round. A second review of the same
   * repository continues the branch's newest case, so its run matches every completed review
   * on that branch: the docket drew a card headed "Round 1 answered" over an empty list, on a
   * review that had never asked anything, and `defaultOpen` handed the docket to it so the
   * first finding wanting a person no longer opened.
   *
   * Two conditions, and each rules out a different half of that. The run has to be making
   * *this* number — a new review takes the next one — and this review has to have asked
   * something, because a round that was never put cannot have been answered.
   */
  const rejudging =
    pendingRun && value && pendingRun.sequence === value.sequence && value.questions.length
      ? pendingRun
      : null;

  // Armed here rather than in the card that renders its button, because the card unmounts the
  // instant the run leaves the listing — which is the instant the notification is owed.
  const rejudgementNotice = useRejudgementNotice(rejudging, runs.data);
  /**
   * Open on a filter that has something in it.
   *
   * `attention` is the right first question and it is the wrong first answer for a review
   * that cleared everything: the docket opened on `Attention 0`, and seven judged boundaries
   * sat behind a chip the reader had to notice and press. What they saw instead was a tick
   * and a sentence, on a page they had just waited on — which reads as a review that found
   * nothing rather than one that settled everything. Measured on a real repository: seven
   * candidates, seven cleared, nothing on screen.
   *
   * Once per review and never after. The filter belongs to the reader the moment they touch
   * it — the docket's own rule is that nothing moves it while they work down the list — so
   * this only ever answers the question "what should be showing when the page arrives".
   *
   * Waits for `ready`, because a decided candidate is settled and the decisions arrive
   * separately: choosing before they land would open on `attention` for a review whose only
   * open rows had already been decided.
   */
  useEffect(() => {
    if (!value || !ready || openedFilterFor.current === value.id) return;
    openedFilterFor.current = value.id;
    const wanting = findings.some((finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id)),
    );
    // `all` rather than `settled`: with nothing wanting attention the two hold the same rows,
    // and `all` is the one that cannot hide a finding whatever else is true of the review.
    setFilter(wanting ? "attention" : "all");
  }, [value, ready, findings, decisions]);
  /**
   * The revision this reader's own answer produced, followed as soon as it exists.
   *
   * `replace`, because the record left behind is the one that says it is out of date: putting
   * it in the history would make Back a way to arrive at a stale page from a fresh one.
   */
  const follow = useRecordToFollow(value, rejudging, runs.data);
  useEffect(() => {
    if (follow) navigate(`/reviews/${follow}`, { replace: true });
  }, [follow, navigate]);

  /**
   * Which item the docket opens on: the clarification when one is waiting, otherwise the
   * first thing that needs a human.
   *
   * Two things have to be true at once, and getting one of them wrong broke the other. The
   * choice has to be available on the first paint, or the docket renders with nothing open
   * and then expands a row a moment later. And it has to stop being a derived value: as a
   * memo over `decisions` it recomputed the instant a decision landed, so deciding the open
   * row moved the cursor from *outside* the docket — which looks exactly like the docket's
   * own auto-advance, except it skips the bookkeeping that keeps the row you just decided on
   * the list, so the row vanished as you acted on it.
   *
   * So it is derived until the branch's decisions have actually arrived, and state after
   * that. `ready` rather than "the map is non-empty", because an empty map means both "nobody
   * has decided anything" and "still in flight", and freezing against the second one opens a
   * row the team settled last week.
   */
  const defaultOpen = useMemo<string | null>(() => {
    if (!value) return null;
    // The round it has just been answered in, too: it is still the item that was last worked
    // on, and it now holds the record of what was said and what that started.
    if (awaitsAnswers(value) || rejudging) return "clarification";
    const first = findings.find((finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id)),
    );
    return first ? first.candidate.id : null;
  }, [value, findings, decisions, rejudging]);

  const open = openId === undefined ? defaultOpen : openId;

  // The functional update is what makes this safe rather than a race. The effect is scheduled
  // from the render where the decisions arrived and flushes some time later — and a keystroke
  // can land in that gap, which is not hypothetical: `j` immediately after the docket painted
  // moved the cursor and then had it moved back underneath by this. Reading the current value
  // inside the updater means a choice already made always wins.
  useEffect(() => {
    if (!ready || !value) return;
    setOpenId((current) => (current === undefined ? defaultOpen : current));
  }, [ready, value, defaultOpen]);

  useEffect(() => {
    setOpenId(undefined);
    setSettledHere([]);
    setSelected([]);
  }, [reviewId]);

  // A retained row is retained against *this* question of the list. Asking a different one —
  // which is what changing the filter is — is the moment the reader stops needing to see
  // what they just decided. Nothing retained means nothing to clear: an unconditional `[]`
  // is a new array every time and therefore a render every time the page mounts.
  useEffect(() => {
    setSettledHere((kept) => (kept.length ? [] : kept));
  }, [filter]);

  /**
   * The finding a link named, opened once and never written back.
   *
   * After the decisions have landed, because `openCandidate` widens the filter to show the
   * candidate and cannot tell whether it wants a person until it knows what the team decided
   * about it. The ref is what makes this "on arrival" rather than "whenever the parameter is
   * still there": a reader who walks away from the named row must not be dragged back to it.
   */
  const honoured = useRef<string | null>(null);
  const requestedCandidate = search.get(CANDIDATE_PARAM);
  useEffect(() => {
    if (!ready || !value || !requestedCandidate) return;
    if (honoured.current === requestedCandidate) return;
    honoured.current = requestedCandidate;
    openCandidate(requestedCandidate);
    // `openCandidate` closes over the filter and the decisions this should read, and the ref
    // above is what stops it running twice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, value, requestedCandidate]);

  /**
   * The review, and what the team has already decided about it, before anything is drawn.
   *
   * The docket's whole claim is *what still wants a person*, and that is not knowable from
   * the review alone: a waived material finding is settled, and a decision taken against a
   * verdict that has since moved is not. Painting the list while the branch's decisions are
   * in flight puts rows in the attention filter that the team settled last week, moves them
   * out from under the reader a moment later, and — because the keyboard is live from the
   * first paint — offers `A` on a row that was never outstanding.
   *
   * There is a real case for splitting this — the decisions request cannot even *start*
   * until the review has resolved, because it needs `repository.branch_id`, so a cold open
   * spends two sequential round trips showing one generic panel while the repository, the
   * branch, the commit and the surface strip have all been known since the first. What
   * stopped it is that the review's *failure* is known at the same moment, and
   * `review-workbench.test.tsx` holds that a failed review shows its failure without hiding
   * the rest of it — the notice and the findings on one screen, which a docket arriving a
   * request later does not give. Splitting the gate is a change to that promise and belongs
   * with it, not underneath it.
   *
   * `ready` is true the moment the request settles either way, so a workspace that cannot
   * answer this does not hold the page: it draws the review with nothing decided, which is
   * what an unanswerable question about decisions honestly amounts to.
   */
  if (review.isLoading || !ready) {
    return (
      <div className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        <LoadingPanel label="Opening the review…" rows={5} />
      </div>
    );
  }
  if (review.error || !value) {
    return (
      <div className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        {/* A retry rather than a reload, because the workspace is a local process and a
            failed read is far more often a moment than a fault. Only where there is a
            request to make again: "that review could not be found" is an answer. */}
        <ErrorNotice
          error={review.error || new Error("That review could not be found")}
          action={
            review.error ? (
              <Button variant="secondary" size="sm" onClick={() => void review.refetch()}>
                Try again
              </Button>
            ) : (
              <ButtonLink to="/reviews" variant="secondary" size="sm">
                Your reviews
              </ButtonLink>
            )
          }
        />
      </div>
    );
  }

  function show(id: string | null) {
    setOpenId(id);
  }

  /**
   * Open a candidate from a surface that is not the docket.
   *
   * The docket's filter is the reader's, so nothing moves it while they work down the list.
   * But arriving from the delta or from an answer's citation is being handed one specific
   * candidate, and a filter that hides it would answer the request with an empty list.
   */
  function openCandidate(candidateId: string) {
    const finding = value?.findings.find((item) => item.candidate.id === candidateId);
    if (finding) {
      const wants = needsAttention(finding, decisions.get(candidateId));
      if (filter !== "all" && wants !== (filter === "attention")) {
        setFilter(wants ? "attention" : "settled");
      }
    }
    show(candidateId);
    setSurface("docket");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ReviewHead
        review={value}
        findings={findings}
        cancelling={cancel.isPending}
        onCancel={() => cancel.mutate()}
        failure={cancel.error}
      />

      {value.superseded_by ? <SupersededNotice review={value} /> : null}

      {/* Pinned under the topbar, because this strip is the only thing on the page that says
          which of the six documents is on screen and the only way to reach the other five.
          A real docket is dozens of rows long: scrolled to the fortieth, everything that
          oriented you had scrolled off, and reaching the atlas meant scrolling back to the
          top of a list you had just worked your way down. It is 44px under the 48px rail,
          which is what `scroll-mt-24` on a row is measured against.

          `z-20` sits under the rail's `z-30` so the two never fight over an overlap, and far
          under the drawers, which have to cover both. The docket itself is untouched: it
          still scrolls with the page rather than inside a box, which `overflow.test.tsx`
          holds — a sticky sibling above it is not a scrollport around it.

          No `border-b` of its own, and no container of its own either. `Tabs`'s line variant
          draws that rule itself, on a wrapper of its own that the selected tab's `-mb-px`
          underline is registered against — so the two were drawn at the same seam: 2px of
          hairline across the centred column and 1px in the margins either side of it, which
          reads as a rendering fault rather than as a decision. The measure and the padding
          go onto that same wrapper through `className` rather than into a third div around
          it, which is one element fewer between the strip and the tabs.

          `px-2 sm:px-3` because a tab is `px-2 sm:px-3`: 8+8 and 12+12 put the first label
          on the same optical left edge as the head's repository name above it and the
          docket's rows below it, which are `px-4 sm:px-6`. It was `px-2 sm:px-4`, right
          below `sm` and 4px out above it — a visible break in the one vertical line three
          stacked regions share. */}
      <div className="sticky top-12 z-20 bg-surface">
        <Tabs
          label="What to read about this review"
          items={SURFACES}
          active={surface}
          onChange={setSurface}
          className="mx-auto w-full max-w-[76rem] px-2 sm:px-3"
        />
      </div>

      {value.failure ? (
        <div className="mx-auto w-full max-w-[76rem] px-4 pt-4 sm:px-6">
          <ErrorNotice error={new Error(value.failure)} title="This review failed" />
        </div>
      ) : null}

      <TabPanel id="docket" active={surface}>
        <Docket
          review={value}
          findings={findings}
          decisions={decisions}
          // Empty rather than short while the reviews are still arriving. A trajectory drawn
          // from half a lineage is a claim that the candidate was not raised in the revisions
          // that are missing, which is a different thing from not knowing yet. The depth
          // beside it comes from the cheap listing, which has already answered, and buys the
          // row the space the strip will want so nothing reflows when it lands.
          lineage={trajectory}
          lineageDepth={lineage.length}
          answers={answers}
          rejudging={rejudging}
          rejudgementNotice={rejudgementNotice}
          filter={filter}
          onFilterChange={setFilter}
          openId={open}
          onOpen={show}
          settledHere={settledHere}
          onSettledHere={setSettledHere}
          selected={selected}
          onSelectedChange={setSelected}
          onOpenContext={() => setContextOpen(true)}
          onReadReport={() => setSurface("report")}
          onReadDelta={() => setSurface("delta")}
        />
        {/* The lineage, under the work rather than beside it: which revision you are reading
            is a fact about the page, not a thing you consult while deciding. */}
        <div className="mx-auto w-full max-w-[76rem] px-4 pb-8 sm:px-6">
          {/* `Panel`, rather than its recipe written out by hand with padding added on top.
              The wrapper was `rounded-lg border border-rule bg-surface px-4 py-3 shadow-rim`
              — the `raised` tone, literally — and `RevisionRail` pads itself as well, so the
              heading sat 28px from the panel edge and a rail entry's text 38px, where
              everything else on the page starts at the container's 16 or 24. The rail keeps
              its own padding; the panel stops adding a second copy of it. */}
          <Panel>
            {/* A failed request used to fall back to `[value]` — this review, alone — so a
                review 4 whose lineage could not be read printed "One immutable revision" and
                every trajectory on the page quietly vanished. A lineage that cannot be read
                is not a lineage of one.

                And neither is a lineage that has not been read yet. `lineage` is derived from
                `summaries.data ?? []`, so while the listing was in flight the rail was handed
                an empty array and printed its zero-entry copy — "The first review of this
                case" — over an empty timeline, to somebody who had just opened review 6. That
                sentence is a positive claim and it is only true once the listing has actually
                answered. */}
            {summaries.error ? (
              <div className="px-3 py-3">
                <ErrorNotice
                  error={summaries.error}
                  title="The lineage could not be read"
                  action={
                    <Button variant="secondary" size="sm" onClick={() => void summaries.refetch()}>
                      Try again
                    </Button>
                  }
                />
              </div>
            ) : summaries.isLoading ? (
              <div className="px-3 py-3">
                <LoadingPanel label="Reading the lineage…" rows={2} />
              </div>
            ) : (
              <RevisionRail reviews={lineage} currentReviewId={value.id} pending={pendingRun} />
            )}
            {/* The work in flight, read here rather than only on its own address.
                `RunProgress` was written for two placements and only ever got one, which was
                survivable while a run was always a revision the rail could link to. It is not
                any more: a run continuing this revision is now that revision's own row, so
                without this the only way to watch a round you had just answered was to
                already know the run's URL.

                A `PanelFooter`, which is what this block is: a strip set into a panel, on
                `--surface-2`, with a full-bleed rule above it. The rule used to be drawn
                inside the wrapper's own padding, so it stopped 16px short of the panel on
                both sides — a hairline in this system separates a panel's parts and can only
                do that by spanning it. */}
            {pendingRun ? (
              <PanelFooter>
                <RunProgress state={pendingRun} />
              </PanelFooter>
            ) : null}
          </Panel>
        </div>
      </TabPanel>

      <TabPanel
        id="rounds"
        active={surface}
        className="mx-auto w-full max-w-[76rem] p-4 sm:p-6"
      >
        {/* Beside the docket rather than inside the drawer, because "what have I been asked
            and what did I say" is a question about the review, not about one candidate. It
            was answerable only per candidate, in the judgement context drawer, and nowhere
            said that a second round was a second round. */}
        <ClarificationsSurface review={value} />
      </TabPanel>
      <TabPanel id="atlas" active={surface} className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        {/* Next to the docket, because "what next" and "where is it" are the two questions a
            reviewer arrives with and the list only answers the first. */}
        <AtlasSurface review={value} onOpen={openCandidate} />
      </TabPanel>
      <TabPanel id="delta" active={surface} className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        {/* Seeing that something changed and looking at it are one action, not two. */}
        <DeltaSurface review={value} onOpen={openCandidate} />
      </TabPanel>
      <TabPanel id="report" active={surface} className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        {/* The fallback is what the reader sees while the Markdown chunk arrives, and it says
            the same thing the report's own loading state says — a tab that flashed a blank
            panel between two spinners would read as a surface that failed and recovered. */}
        <Suspense fallback={<LoadingPanel label="Rendering the report…" />}>
          <ReportSurface review={value} />
        </Suspense>
      </TabPanel>
      <TabPanel id="ask" active={surface} className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        <AskSurface review={value} onOpen={openCandidate} />
      </TabPanel>

      {/* The case, the policies, the structure around a candidate and the provenance behind a
          judgement: one action away from the row being decided, rather than crowding it. */}
      <Drawer
        open={contextOpen}
        onClose={() => setContextOpen(false)}
        side="right"
        title="Judgement context"
        description="Case, policies, structure and provenance"
      >
        <ContextRail
          review={value}
          finding={
            value.findings.find((finding) => finding.candidate.id === open) ?? null
          }
          tab={contextTab}
          onTabChange={setContextTab}
        />
      </Drawer>
    </div>
  );
}
