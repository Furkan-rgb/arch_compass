import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { useIsTabletUp } from "../../lib/media";
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
import { MetaLine, TONE_TEXT } from "../../ui/meta";
import { Panel, PanelBody } from "../../ui/panel";
import { ErrorNotice, LoadingPanel } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import {
  AttentionQueue,
  type QueueFilter,
  type QueueSelection,
  inFilter,
  needsAttention,
  orderedFindings,
  useStandingDecisions,
} from "./attention-queue";
import { ClarificationRound } from "./clarification";
import { ContextRail } from "./context-rail";
import { FindingBackBar, FindingDetail } from "./finding-detail";
import { RevisionRail, lineageOf } from "./revision-rail";
import { AskSurface, DeltaSurface, ReportSurface } from "./surfaces";

/**
 * What the detail column is showing.
 *
 * These used to be seven peers across the top of the whole page, and six of them unmounted
 * the queue — which the charter calls the product. They were never views of the review;
 * they were modes of the column beside the queue, and they are labelled and placed as that
 * now. Evidence and Retrieval are gone: both printed, one click further away, what the open
 * finding and its judgement context already show. Atlas is gone from here and scoped to the
 * selected candidate inside the judgement context, because an unscoped repository search
 * helps decide nothing in particular.
 */
const SURFACES = [
  { id: "workbench", label: "Workbench" },
  { id: "delta", label: "Delta" },
  { id: "report", label: "Report" },
  { id: "ask", label: "Ask" },
];

/**
 * How much is left, and what is stopping it.
 *
 * A reviewer arrives at this page with exactly two questions, and until now the head
 * answered neither: the largest type on it was the repository's name — the fact its reader
 * was least in doubt about — and the only other thing it said was a status word. So the
 * counts are stated here, once, before the work.
 *
 * They are a strip and not a dashboard on purpose. The charter is blunt about what a count
 * is for — "orientation, read once, on the way to the work. A number that nobody acts on is
 * decoration" — so there is no card, no chart, no target and no trend. Small type, one line
 * where it fits, wrapping where it does not, and every glyph and hue arriving from the tone
 * table rather than being picked here, because a verdict's three channels are decided in one
 * place for the whole product.
 *
 * The numbers come off the list the queue itself walks, and `decided` is the queue's own
 * definition of a settled row rather than a second one. Two counts of the same thing that
 * disagree on the same screen are worse than one count nobody reads.
 *
 * The blocked state is a sentence. It was a tinted, bordered banner carrying its own Answer
 * button, which made the heaviest element on the page the one region that is meant to be
 * read once and left behind — and made it the fourth place the same question could be
 * answered from. `held` is doing two different jobs here, a verdict the model reached and
 * the state the page is in, and only the verdict gets the hue.
 */
function ReviewOrientation({ review, className }: { review: Review; className?: string }) {
  const decisions = useStandingDecisions(review);
  const findings = orderedFindings(review);

  // Deliberately not `decisions.has(...)`: a decision taken against a verdict that has since
  // moved is re-raised by the queue as something needing a person again, so counting it here
  // would have the strip claim work that the list is still asking for.
  const decided = findings.filter((finding) => {
    const decision = decisions.get(finding.candidate.id);
    return Boolean(decision) && !needsAttention(finding, decision);
  }).length;

  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;
  const asked = new Set(review.questions.flatMap((question) => question.candidate_ids));
  const blocked = findings.filter((finding) => asked.has(finding.candidate.id)).length;
  const outstanding = findings.filter((finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  ).length;
  const questions = plural(review.questions.length, "unanswered question");

  if (!findings.length && !waiting) return null;

  return (
    <div className={className}>
      {findings.length ? (
        <MetaLine
          className="text-[13px]"
          items={[
            <span key="total" className="inline-flex items-center gap-1.5 text-ink-2">
              <span className="font-semibold tabular-nums text-ink">{findings.length}</span>
              {findings.length === 1 ? "candidate" : "candidates"}
            </span>,
            ...VERDICT_ORDER.map((verdict) => {
              const descriptor = verdictOf(verdict);
              const count = findings.filter((finding) => finding.verdict === verdict).length;
              return (
                // A zero recedes rather than alarms. None of these is a target to hit, and
                // "no material findings" is the ordinary case, not an empty slot to fill.
                <span
                  key={verdict}
                  className={cn(
                    "inline-flex items-center gap-1.5",
                    count ? "text-ink-2" : "text-ink-3",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "text-[10px]",
                      count ? TONE_TEXT[descriptor.tone] : "text-ink-3",
                    )}
                  >
                    {descriptor.glyph}
                  </span>
                  <span
                    className={cn("font-semibold tabular-nums", count ? "text-ink" : "text-ink-3")}
                  >
                    {count}
                  </span>
                  {descriptor.label.toLowerCase()}
                </span>
              );
            }),
            <span
              key="decided"
              className={cn(
                "inline-flex items-center gap-1.5",
                decided ? "text-ink-2" : "text-ink-3",
              )}
            >
              <span className={cn("font-semibold tabular-nums", decided ? "text-ink" : "text-ink-3")}>
                {decided}
              </span>
              decided
            </span>,
          ]}
        />
      ) : null}

      {/* One sentence, in the same ink as anything else that is read rather than acted on.
          No tint, no rule, no button: the answer is given inside the finding the question
          holds up, which is the only place it is asked for, and the queue lists the round as
          a row because the queue is the list of what still wants a person. */}
      {waiting ? (
        <p className={cn("text-[13px] leading-6 text-ink-2", findings.length > 0 && "mt-2")}>
          {blocked
            ? `${blocked === outstanding && blocked > 1 ? "All " : ""}${plural(
                blocked,
                "candidate",
              )} ${blocked === 1 ? "is" : "are"} waiting on ${questions}, answered inside the finding under Hinges on.`
            : `This review is held on ${questions}.`}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Which review this is, in one line.
 *
 * The heading was "Architecture review of payments-platform" at 30px — the largest type on
 * the page spent on the fact its reader was least in doubt about. What identifies a review
 * is the repository, the branch and the commit it read, so that is the heading, in the
 * measured voice, and it fits on one line with the status and the way out.
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
    <header className="mb-4 border-b border-rule pb-4">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3">
            Review {review.sequence} · case revision {review.case.revision} · started{" "}
            {relativeTime(review.started_at)}
          </div>
          <h1 className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[17px] leading-tight tracking-[-0.01em] text-ink-3 sm:text-[19px]">
            <span className="font-medium text-ink [overflow-wrap:anywhere]">
              {repositoryName(review.repository.path)}
            </span>
            {review.repository.branch ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="[overflow-wrap:anywhere]">{review.repository.branch}</span>
              </>
            ) : null}
            {review.repository.commit ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="text-[0.85em]">{shortId(review.repository.commit, 10)}</span>
              </>
            ) : null}
          </h1>
          <p
            title={review.repository.path}
            className="mt-1.5 truncate font-mono text-[11px] text-ink-3"
          >
            {review.repository.path}
          </p>
        </div>

        {/* One control, and it is the way out rather than the way on. The blocking question
            used to be answerable from a primary button here as well as from the queue's
            clarification row and from the finding it holds up — three affordances for one
            answer, the loudest of them furthest from the work. Cancelling is the only thing
            this corner is still for, so it is dressed as what it is: secondary, and no
            longer wearing the destructive red, which in this system is a verdict's hue. */}
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <StatusBadge status={review.status} />
          {waiting ? (
            <Button variant="secondary" disabled={cancelling} onClick={onCancel}>
              Cancel review
            </Button>
          ) : (
            <ButtonLink to="/start" variant="secondary">
              Run a new review
            </ButtonLink>
          )}
        </div>
      </div>

      <ReviewOrientation review={review} className="mt-4" />
    </header>
  );
}

export function ReviewPage() {
  const { reviewId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const isTabletUp = useIsTabletUp();

  const [surface, setSurface] = useState("workbench");
  const [filter, setFilter] = useState<QueueFilter>("attention");
  const [selection, setSelection] = useState<QueueSelection | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);

  const review = useQuery({ queryKey: ["review", reviewId], queryFn: () => api.review(reviewId) });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  // A run for this same branch and case is the next revision of the lineage this page is
  // already showing, so it belongs in this page's rail rather than only at an address
  // somebody had to keep hold of.
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
  const decisions = useStandingDecisions(value);

  // The queue's opening position: the clarification when one is waiting, otherwise the first
  // thing that needs a human, otherwise the first finding at all.
  const defaultSelection = useMemo<QueueSelection | null>(() => {
    if (!value) return null;
    if (value.status === "awaiting_answers" && value.questions.length) return { kind: "clarification" };
    const ordered = orderedFindings(value);
    const first =
      ordered.find((finding) => needsAttention(finding, decisions.get(finding.candidate.id))) ??
      ordered[0];
    return first ? { kind: "finding", candidateId: first.candidate.id } : null;
  }, [value, decisions]);

  useEffect(() => {
    setSelection(null);
  }, [reviewId]);

  // A run for this same branch and case is the next revision of the lineage on screen, so
  // it belongs in this rail. Opening it is a link like every other entry — the run has its
  // own address, and that page renders the same head and rail around its progress.
  const pendingRun =
    (value &&
      (runs.data ?? []).find(
        (run) => run.branch_id === value.repository.branch_id && run.case_id === value.case.id,
      )) ||
    null;

  const active = selection ?? defaultSelection;
  const selectedFinding =
    active?.kind === "finding"
      ? (value?.findings.find((finding) => finding.candidate.id === active.candidateId) ?? null)
      : null;

  /**
   * The next thing that still wants a person, in the order the queue lists them.
   *
   * Offered at the foot of a finding rather than jumped to when a decision is recorded:
   * deciding something and being moved somewhere else without being asked is the interface
   * concluding you were finished, which is the one thing the charter says never to do on a
   * person's behalf.
   */
  const nextUp = useMemo<Finding | null>(() => {
    if (!value || active?.kind !== "finding") return null;
    const outstanding = orderedFindings(value).filter((finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id)),
    );
    const at = outstanding.findIndex((finding) => finding.candidate.id === active.candidateId);
    return at === -1 ? (outstanding[0] ?? null) : (outstanding[at + 1] ?? null);
  }, [value, active, decisions]);

  if (review.isLoading) return <LoadingPanel label="Opening the review…" rows={5} />;
  if (review.error || !value) {
    return <ErrorNotice error={review.error || new Error("That review could not be found")} />;
  }

  function select(next: QueueSelection) {
    setSelection(next);
    setQueueOpen(false);
    // The queue's job is to hand the column an item; a mode that ignored what it handed
    // over would make the list ornamental.
    setSurface("workbench");
  }

  /**
   * Open a candidate from somewhere that is not the queue.
   *
   * The queue's filter is the reader's, so nothing moves it while they work down the list.
   * But arriving from another surface is not working down the list — it is being handed a
   * specific candidate, and a filter that hides it would answer the request with an empty
   * rail. So the filter widens to one that contains it, and only then.
   */
  function open(candidateId: string) {
    const finding = value?.findings.find((item) => item.candidate.id === candidateId);
    if (finding && !inFilter(finding, filter, decisions.get(candidateId))) {
      setFilter(needsAttention(finding, decisions.get(candidateId)) ? "attention" : "settled");
    }
    select({ kind: "finding", candidateId });
  }

  const detail =
    active?.kind === "clarification" ? (
      <ClarificationRound review={value} />
    ) : selectedFinding ? (
      <FindingDetail
        review={value}
        finding={selectedFinding}
        next={nextUp}
        onNext={nextUp ? () => select({ kind: "finding", candidateId: nextUp.candidate.id }) : undefined}
        onAnswer={() => select({ kind: "clarification" })}
        onOpenContext={() => setContextOpen(true)}
      />
    ) : (
      <Panel>
        <PanelBody>
          <p className="text-sm text-ink-3">
            This review composed no findings. The delta still describes what was analysed.
          </p>
        </PanelBody>
      </Panel>
    );

  const queue = (
    <AttentionQueue
      review={value}
      selection={active}
      onSelect={select}
      filter={filter}
      onFilterChange={setFilter}
      onReadReport={() => setSurface("report")}
      className="min-h-0 flex-1"
    />
  );

  return (
    <div>
      <ReviewHead review={value} cancelling={cancel.isPending} onCancel={() => cancel.mutate()} />

      {value.failure ? (
        <div className="mb-4">
          <ErrorNotice error={new Error(value.failure)} title="This review failed" />
        </div>
      ) : null}

      {/* The queue is the page, not a tab on it. Every mode of the column beside it is read
          with the list still on screen, because choosing what to look at next is what a
          reviewer is doing between every other action. */}
      <div
        className={cn(
          "grid min-h-0 items-start gap-6",
          isTabletUp && "lg:grid-cols-[19rem_minmax(0,1fr)]",
        )}
      >
        {isTabletUp ? (
          /* Both numbers below are measured from the top of the viewport, not from the head
             above them — which is why gaining the orientation strip does not move either.
             The head scrolls away under the shell's own sticky header and the rail carries
             on without it; what the rail has to clear is that header (53px: a 32px control
             row inside 10px of padding, over a hairline) plus the main column's 32px of top
             padding, so it pins level with where the content starts. 5rem is that sum on the
             8px rhythm. */
          <div className="grid gap-4 lg:sticky lg:top-20">
            {/* The height has to be spent, not just capped: the queue's own scroller only
                bounds itself if this box lays its children out as a column with a height
                to divide. Capped alone, the list overruns and the clip eats its last row.

                And the cap is the pinned geometry written out as its terms rather than as
                the 8rem they add up to: the panel's top edge is `top-20`'s 5rem, and 3rem is
                left underneath it — the 1rem grid gap, then 2rem of the revision rail, which
                is what says there is something below the queue at all. Written as the sum
                because the total looks like a header height, and the next person to add a
                row to the head would otherwise retune it against a head that has nothing to
                do with it.

                `h-` as well as `max-h-`, and they are not redundant. A cap alone leaves the
                panel content-sized, so the list inside it has no spare height to claim and
                `flex-1` resolves to nothing — which is how the queue ended up half empty
                below its last row while still being told to fill the column. The cap is what
                `overflow.test.tsx` asserts on and what bounds a long queue; the height is
                what a short one grows into. */}
            <Panel className="flex h-[calc(100vh-5rem-3rem)] max-h-[calc(100vh-5rem-3rem)] flex-col overflow-hidden">
              {queue}
            </Panel>
            <Panel>
              <RevisionRail
                reviews={lineageOf(
                  reviews.data ?? [value],
                  value.repository.branch_id,
                  value.case.id,
                )}
                currentReviewId={value.id}
                pending={pendingRun}
              />
            </Panel>
          </div>
        ) : null}

        <div className="min-w-0">
          <Tabs
            label="What to read about this review"
            items={SURFACES}
            active={surface}
            onChange={setSurface}
            className="mb-4"
          />

          {/* The way into the queue below the tablet breakpoint, sized as a target rather
              than as a chip — but only where the finding is not already carrying one.
              With a finding open on a phone this sat directly above `FindingBackBar`, so
              two buttons a thumb apart opened the same drawer and the top one was the one
              that did not say where it went. */}
          {!isTabletUp && !(selectedFinding && surface === "workbench") ? (
            <div className="mb-3">
              <Button variant="secondary" onClick={() => setQueueOpen(true)}>
                Attention queue
              </Button>
            </div>
          ) : null}

          <TabPanel id="workbench" active={surface}>
            {!isTabletUp && selectedFinding ? (
              <FindingBackBar finding={selectedFinding} onBack={() => setQueueOpen(true)} />
            ) : null}
            {detail}
          </TabPanel>

          <TabPanel id="delta" active={surface}>
            {/* Seeing that something changed and looking at it are one action, not two: the
                delta hands the candidate to the workbench rather than naming it and leaving
                the reader to find it in the queue. */}
            <DeltaSurface review={value} onOpen={open} />
          </TabPanel>
          <TabPanel id="report" active={surface}>
            <ReportSurface review={value} />
          </TabPanel>
          <TabPanel id="ask" active={surface}>
            <AskSurface review={value} onOpen={open} />
          </TabPanel>
        </div>
      </div>

      <Drawer
        open={queueOpen}
        onClose={() => setQueueOpen(false)}
        side="bottom"
        title="Attention queue"
        description="What this review needs from a human"
      >
        <div className="flex max-h-[70vh] flex-col">{queue}</div>
      </Drawer>

      {/* The finding is one reading column, so the case, the policies, the structure around
          it and the provenance behind a judgement are one action away rather than crowding a
          second margin. Opened at every width, not only the narrow ones — there is no inline
          margin left at any. */}
      <Drawer
        open={contextOpen}
        onClose={() => setContextOpen(false)}
        side="right"
        title="Judgement context"
        description="Case, policies, structure and provenance"
      >
        <ContextRail review={value} finding={selectedFinding} />
      </Drawer>
    </div>
  );
}
