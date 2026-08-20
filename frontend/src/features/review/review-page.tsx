import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { useIsTabletUp } from "../../lib/media";
import { relativeTime, repositoryName, shortId } from "../../lib/format";
import { StatusBadge } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Drawer } from "../../ui/drawer";
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
  onAnswer,
}: {
  review: Review;
  onCancel: () => void;
  cancelling: boolean;
  onAnswer: () => void;
}) {
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;
  return (
    <header className="mb-4 flex flex-col justify-between gap-3 border-b border-rule pb-4 lg:flex-row lg:items-end">
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

      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <StatusBadge status={review.status} />
        {waiting ? (
          <>
            <Button onClick={onAnswer}>Answer {review.questions.length}</Button>
            <Button variant="danger" disabled={cancelling} onClick={onCancel}>
              Cancel review
            </Button>
          </>
        ) : (
          <ButtonLink to="/start" variant="secondary">
            Run a new review
          </ButtonLink>
        )}
      </div>
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
      <ReviewHead
        review={value}
        cancelling={cancel.isPending}
        onCancel={() => cancel.mutate()}
        onAnswer={() => select({ kind: "clarification" })}
      />

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
          <div className="grid gap-4 lg:sticky lg:top-20">
            {/* The height has to be spent, not just capped: the queue's own scroller only
                bounds itself if this box lays its children out as a column with a height
                to divide. Capped alone, the list overruns and the clip eats its last row. */}
            <Panel className="flex max-h-[calc(100vh-8rem)] flex-col overflow-hidden">{queue}</Panel>
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

          {!isTabletUp ? (
            <div className="mb-3">
              <Button variant="secondary" size="sm" onClick={() => setQueueOpen(true)}>
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

      {/* The finding is one reading column registered against the attribution gutter, so
          the case, the policies, the structure around it and the provenance behind a
          judgement are one action away rather than crowding a second margin. Opened at
          every width, not only the narrow ones — there is no inline margin left at any. */}
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
