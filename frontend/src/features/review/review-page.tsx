import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type Review } from "../../api";
import { cn } from "../../lib/cn";
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
import { ErrorNotice, LoadingPanel } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import {
  type QueueFilter,
  needsAttention,
  orderedFindings,
  useStandingDecisions,
} from "./docket-rules";
import { AtlasSurface } from "./atlas-surface";
import { ContextRail } from "./context-rail";
import { Docket } from "./docket";
import { RevisionRail, lineageOf } from "./revision-rail";
import { AskSurface, DeltaSurface, ReportSurface } from "./surfaces";

/**
 * What the page is showing.
 *
 * `Docket` is the review — the list and the assessments, which are the same thing. The other
 * three are documents about the review rather than modes of working through it, which is why
 * they are peers of it rather than columns beside it.
 */
const SURFACES = [
  { id: "docket", label: "Docket" },
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
function ReviewCounts({ review, className }: { review: Review; className?: string }) {
  const { byCandidate: decisions } = useStandingDecisions(review);
  const findings = orderedFindings(review);

  const outstanding = findings.filter((finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  ).length;
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;
  // The open clarification wants a person as much as any candidate does, and the docket lists
  // it as the first item, so the head counts it as one. Two totals of the same list that
  // disagree on one screen are worse than one total nobody reads.
  const wants = outstanding + (waiting ? review.questions.length : 0);

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
function ReviewHead({
  review,
  onCancel,
  cancelling,
}: {
  review: Review;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;
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
            <span className="text-[10px] font-bold uppercase tracking-[0.13em] text-ink-3">
              Review {review.sequence} · case revision {review.case.revision} ·{" "}
              {relativeTime(review.started_at)}
            </span>
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

        <ReviewCounts review={review} className="mt-2" />
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
   * opened in a second window beside the first — and this page's tabs are five documents
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
   * Which row is open, once somebody or something has chosen. `undefined` means nobody has,
   * and the page falls back to `defaultOpen` below — three states rather than two, because
   * "closed everything deliberately" and "has not chosen yet" are different and the second
   * one must not win over the first.
   */
  const [openId, setOpenId] = useState<string | null | undefined>(undefined);
  const [contextOpen, setContextOpen] = useState(false);

  const review = useQuery({ queryKey: ["review", reviewId], queryFn: () => api.review(reviewId) });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => (query.state.data?.length ? 4000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancel(reviewId),
    onSuccess: async (next) => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
      navigate(`/reviews/${next.id}`);
    },
  });

  const value = review.data;
  const { byCandidate: decisions, ready } = useStandingDecisions(value);

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
    if (value.status === "awaiting_answers" && value.questions.length) return "clarification";
    const first = orderedFindings(value).find((finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id)),
    );
    return first ? first.candidate.id : null;
  }, [value, decisions]);

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
  }, [reviewId]);

  const pendingRun =
    (value &&
      (runs.data ?? []).find(
        (run) => run.branch_id === value.repository.branch_id && run.case_id === value.case.id,
      )) ||
    null;

  /** The revisions of this branch and case, oldest first, for a candidate's trajectory. */
  const lineage = useMemo(
    () =>
      value
        ? [...lineageOf(reviews.data ?? [value], value.repository.branch_id, value.case.id)].sort(
            (left, right) => left.sequence - right.sequence,
          )
        : [],
    [reviews.data, value],
  );

  if (review.isLoading) {
    return (
      <div className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        <LoadingPanel label="Opening the review…" rows={5} />
      </div>
    );
  }
  if (review.error || !value) {
    return (
      <div className="mx-auto w-full max-w-[76rem] p-4 sm:p-6">
        <ErrorNotice error={review.error || new Error("That review could not be found")} />
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
      <ReviewHead review={value} cancelling={cancel.isPending} onCancel={() => cancel.mutate()} />

      <div className="border-b border-rule bg-surface">
        <div className="mx-auto w-full max-w-[76rem] px-2 sm:px-4">
          <Tabs
            label="What to read about this review"
            items={SURFACES}
            active={surface}
            onChange={setSurface}
          />
        </div>
      </div>

      {value.failure ? (
        <div className="mx-auto w-full max-w-[76rem] px-4 pt-4 sm:px-6">
          <ErrorNotice error={new Error(value.failure)} title="This review failed" />
        </div>
      ) : null}

      <TabPanel id="docket" active={surface}>
        <Docket
          review={value}
          decisions={decisions}
          lineage={lineage}
          filter={filter}
          onFilterChange={setFilter}
          openId={open}
          onOpen={show}
          onOpenContext={() => setContextOpen(true)}
          onReadReport={() => setSurface("report")}
        />
        {/* The lineage, under the work rather than beside it: which revision you are reading
            is a fact about the page, not a thing you consult while deciding. */}
        <div className="mx-auto w-full max-w-[76rem] px-4 pb-8 sm:px-6">
          <div className="rounded-lg border border-rule bg-surface px-4 py-3 shadow-rim">
            <RevisionRail
              reviews={lineageOf(reviews.data ?? [value], value.repository.branch_id, value.case.id)}
              currentReviewId={value.id}
              pending={pendingRun}
            />
          </div>
        </div>
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
        <ReportSurface review={value} />
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
        />
      </Drawer>
    </div>
  );
}
