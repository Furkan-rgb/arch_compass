import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { useIsTabletUp } from "../../lib/media";
import { type Tone, relativeTime, repositoryName, shortId, verdictOf } from "../../lib/format";
import { StatusBadge, Tag } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Drawer } from "../../ui/drawer";
import { GitBranchIcon } from "../../ui/icons";
import { Mono, PathRef, TONE_TEXT } from "../../ui/meta";
import { Panel, PanelBody } from "../../ui/panel";
import { ErrorNotice, LoadingPanel } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import {
  AttentionQueue,
  type QueueFilter,
  type QueueSelection,
  needsAttention,
  orderedFindings,
} from "./attention-queue";
import { ClarificationRound } from "./clarification";
import { ContextRail } from "./context-rail";
import { FindingBackBar, FindingDetail } from "./finding-detail";
import { RevisionRail } from "./revision-rail";
import {
  AskSurface,
  AtlasSurface,
  DeltaSurface,
  EvidenceSurface,
  ProvenanceSurface,
  ReportSurface,
} from "./surfaces";

const SURFACES = [
  { id: "workbench", label: "Workbench" },
  { id: "delta", label: "Delta" },
  { id: "atlas", label: "Atlas" },
  { id: "evidence", label: "Evidence" },
  { id: "retrieval", label: "Retrieval" },
  { id: "report", label: "Report" },
  { id: "ask", label: "Ask" },
];

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
    <header className="mb-5">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
            Review {review.sequence} · case revision {review.case.revision}
          </div>
          <h1 className="mt-1.5 max-w-3xl font-display text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-[30px]">
            {review.case.goal || `Architecture review of ${repositoryName(review.repository.path)}`}
          </h1>
          <div className="mt-2.5 flex max-w-full flex-wrap items-center gap-1.5">
            <PathRef path={review.repository.path} className="min-w-0" />
            {review.repository.branch ? (
              <Tag>
                {/* The icon carries the noun, so the pill can spend its width on the name.
                    It stays labelled for anything not reading the shape. */}
                <GitBranchIcon className="size-3.5 shrink-0 text-ink-3" aria-hidden="true" />
                <span className="sr-only">branch</span>
                {review.repository.branch}
              </Tag>
            ) : null}
            {review.repository.commit ? (
              <Tag>
                <Mono className="text-[11px]">{shortId(review.repository.commit, 10)}</Mono>
              </Tag>
            ) : null}
            <Tag>started {relativeTime(review.started_at)}</Tag>
            <StatusBadge status={review.status} />
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
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
      </div>
    </header>
  );
}

function StatusRibbon({ review }: { review: Review }) {
  const attention = review.findings.filter(needsAttention).length;
  const material = review.findings.filter((finding) => finding.verdict === "material").length;
  const held = review.findings.filter((finding) => finding.verdict === "held").length;
  const policies = new Set(
    review.retrieval_manifest.flatMap((item) => item.selected_policy_ids),
  ).size;
  const waiting = review.status === "awaiting_answers" ? review.questions.length : 0;

  // A line rather than a panel of four big numbers: this is orientation, read once, and it
  // used to cost about 120px above the work it was orienting you to.
  // The first cell counts what a person still has to deal with, so it is the one cell that
  // carries a verdict's tone — taken from the table that decides them rather than written
  // out here, because a hue written out here is one nothing stops from spreading.
  const cells: Array<[number, string, Tone | null]> = [
    [attention + waiting, `need you — ${material} material, ${held} held`, verdictOf("material").tone],
    [review.findings.length, "judged", null],
    [policies, "policies retrieved", null],
    [
      review.delta.new.length + review.delta.changed.length,
      review.previous_review_id ? `new or changed since review ${review.sequence - 1}` : "new",
      null,
    ],
  ];

  return (
    <div className="mb-4 flex flex-wrap overflow-hidden rounded-md border border-rule bg-surface">
      {cells.map(([value, label, tone], index) => (
        <div
          key={label}
          className={cn(
            "flex items-baseline gap-2 px-4 py-2.5",
            index < cells.length - 1 && "border-r border-rule",
          )}
        >
          <span
            className={cn(
              "font-display text-lg font-semibold tabular-nums",
              tone && value > 0 ? TONE_TEXT[tone] : "text-ink",
            )}
          >
            {value}
          </span>
          <span className="text-xs text-ink-3">{label}</span>
        </div>
      ))}
    </div>
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
  // Choosing what to look at and working down the list are different jobs; the rail is only
  // needed for the first, so it can be put away for the second.
  const [railOpen, setRailOpen] = useState(true);

  const review = useQuery({ queryKey: ["review", reviewId], queryFn: () => api.review(reviewId) });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  const cancel = useMutation({
    mutationFn: () => api.cancel(reviewId),
    onSuccess: async (next) => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
      navigate(`/reviews/${next.id}`);
    },
  });

  const value = review.data;

  // The queue's opening position: the clarification when one is waiting, otherwise the first
  // thing that needs a human, otherwise the first finding at all.
  const defaultSelection = useMemo<QueueSelection | null>(() => {
    if (!value) return null;
    if (value.status === "awaiting_answers" && value.questions.length) return { kind: "clarification" };
    const ordered = orderedFindings(value);
    const first = ordered.find(needsAttention) ?? ordered[0];
    return first ? { kind: "finding", candidateId: first.candidate.id } : null;
  }, [value]);

  useEffect(() => {
    setSelection(null);
  }, [reviewId]);

  const active = selection ?? defaultSelection;
  const selectedFinding =
    active?.kind === "finding"
      ? (value?.findings.find((finding) => finding.candidate.id === active.candidateId) ?? null)
      : null;

  if (review.isLoading) return <LoadingPanel label="Opening the review…" rows={5} />;
  if (review.error || !value) {
    return <ErrorNotice error={review.error || new Error("That review could not be found")} />;
  }

  function select(next: QueueSelection) {
    setSelection(next);
    setQueueOpen(false);
  }

  const detail =
    active?.kind === "clarification" ? (
      <ClarificationRound review={value} />
    ) : selectedFinding ? (
      <FindingDetail
        review={value}
        finding={selectedFinding}
        onOpenContext={isTabletUp ? undefined : () => setContextOpen(true)}
      />
    ) : (
      <Panel>
        <PanelBody>
          <p className="text-sm text-ink-3">
            This review composed no findings. The delta and atlas surfaces still describe what was
            analysed.
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
    />
  );

  return (
    <div>
      <ReviewHead
        review={value}
        cancelling={cancel.isPending}
        onCancel={() => cancel.mutate()}
        onAnswer={() => {
          setSurface("workbench");
          select({ kind: "clarification" });
        }}
      />

      {value.failure ? (
        <div className="mb-5">
          <ErrorNotice error={new Error(value.failure)} title="This review failed" />
        </div>
      ) : null}

      <StatusRibbon review={value} />

      <Tabs
        label="Review surfaces"
        items={SURFACES}
        active={surface}
        onChange={setSurface}
        className="mb-5"
      />

      <TabPanel id="workbench" active={surface}>
        <div
          className={cn(
            "grid min-h-0 items-start gap-6",
            isTabletUp && railOpen
              ? "lg:grid-cols-[19rem_minmax(0,1fr)]"
              : "grid-cols-1",
          )}
        >
          {isTabletUp && railOpen ? (
            <div className="grid gap-4 lg:sticky lg:top-20">
              <Panel className="max-h-[calc(100vh-9rem)] overflow-hidden">
                {queue}
                <button
                  type="button"
                  onClick={() => setRailOpen(false)}
                  className="w-full border-t border-rule px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3 transition hover:bg-sunken hover:text-ink"
                >
                  Hide the queue
                </button>
              </Panel>
              <Panel>
                <RevisionRail current={value} reviews={reviews.data ?? [value]} />
              </Panel>
            </div>
          ) : null}

          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap gap-2">
              {isTabletUp && !railOpen ? (
                <Button variant="secondary" size="sm" onClick={() => setRailOpen(true)}>
                  Show the queue
                </Button>
              ) : null}
              {!isTabletUp ? (
                <Button variant="secondary" size="sm" onClick={() => setQueueOpen(true)}>
                  Attention queue
                </Button>
              ) : null}
            </div>
            {!isTabletUp && selectedFinding ? (
              <FindingBackBar finding={selectedFinding} onBack={() => setQueueOpen(true)} />
            ) : null}
            {detail}
          </div>
        </div>
      </TabPanel>

      <TabPanel id="delta" active={surface}>
        <DeltaSurface review={value} />
      </TabPanel>
      <TabPanel id="atlas" active={surface}>
        <AtlasSurface review={value} />
      </TabPanel>
      <TabPanel id="evidence" active={surface}>
        <EvidenceSurface review={value} />
      </TabPanel>
      <TabPanel id="retrieval" active={surface}>
        <ProvenanceSurface review={value} />
      </TabPanel>
      <TabPanel id="report" active={surface}>
        <ReportSurface review={value} />
      </TabPanel>
      <TabPanel id="ask" active={surface}>
        <AskSurface review={value} />
      </TabPanel>

      <Drawer
        open={queueOpen}
        onClose={() => setQueueOpen(false)}
        side="bottom"
        title="Attention queue"
        description="What this review needs from a human"
      >
        <div className="max-h-[70vh]">{queue}</div>
      </Drawer>

      {/* The context rail is a document margin now, so this only exists for the width
          where there is no margin to put it in. */}
      <Drawer
        open={contextOpen && !isTabletUp}
        onClose={() => setContextOpen(false)}
        side="right"
        title="Judgement context"
        description="Case, policies and provenance"
      >
        <ContextRail review={value} finding={selectedFinding} />
      </Drawer>
    </div>
  );
}
