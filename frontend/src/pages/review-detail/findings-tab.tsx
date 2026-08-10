/** The Findings tab: what the reader's answers moved, the ledger of verdicts, the conclusion. */

import { AddressedLedger } from "../../delta";
import { HeldVerdicts } from "../../review-awaiting";
import { FindingsLedger, JudgingLedger } from "../../review-ledger";
import { BulkDecide } from "../../triage";
import type { RunState } from "../../run-progress";
import { Conclusion } from "./conclusion";
import { WhatAnswersChanged } from "./what-answers-changed";
import { verdictChanges } from "./verdict-changes";
import type {
  BoundaryTriage,
  OpenQuestion,
  RecordedAnswer,
  ReviewDetail,
  ReviewedBoundary,
} from "../../types";

export function FindingsTab({
  reviewId,
  reviewed,
  report,
  triage,
  policyCount,
  branchId,
  openRow,
  onOpenRow,
  onShowInAtlas,
  progress,
  running,
  holding,
  judgedBefore,
  askedEarlier,
  answered,
  undecided,
}: {
  reviewId: string;
  reviewed: ReviewedBoundary[];
  report: ReviewDetail["report"] | null;
  triage: Map<string, BoundaryTriage>;
  policyCount: number;
  branchId: string | null;
  openRow: string | null;
  onOpenRow: (reference: string | null) => void;
  /** Absent while there is no map to show a boundary in. */
  onShowInAtlas: ((nodeId: string) => void) | null;
  progress: RunState;
  running: boolean;
  holding: boolean;
  /** The verdicts of the pass this one answers, where there is one and it has loaded. */
  judgedBefore: ReviewedBoundary[] | undefined;
  /** The questions the asking pass put, which is where the wording lives. */
  askedEarlier: OpenQuestion[];
  answered: RecordedAnswer[];
  /** Material boundaries with nobody's name on them — what the bulk gesture would decide. */
  undecided: ReviewedBoundary[];
}) {
  const ledger = (
    <FindingsLedger
      reviewed={reviewed}
      policyCount={policyCount}
      reviewId={reviewId}
      open={openRow}
      onOpen={onOpenRow}
      onShowInAtlas={onShowInAtlas}
      triage={triage}
      branchId={branchId}
    />
  );
  return (
    <>
      {/* First, and only on a second pass: what the reader's own answers changed.
          They did the work a moment ago, and this is the one place the product's
          claim is checkable rather than asserted. */}
      {judgedBefore ? (
        <WhatAnswersChanged
          changes={verdictChanges(judgedBefore, reviewed)}
          total={reviewed.length}
          questions={askedEarlier}
          answered={answered}
        />
      ) : null}
      {/* Adoption, when there is a plural to adopt: everything material and
          undecided, one recorded decision each. What used to be the baseline
          button, with an author attached. */}
      {!running && !holding && branchId && undecided.length > 1 ? (
        <BulkDecide boundaries={undecided} branchId={branchId} reviewId={reviewId} />
      ) : null}
      {/* The boundaries this revision closed, above the ledger of the ones it still
          has: the best news first, and it has no row of its own to live in. */}
      {!running && report?.delta?.addressed_boundaries?.length ? (
        <AddressedLedger addressed={report.delta.addressed_boundaries} />
      ) : null}
      {running ? (
        <JudgingLedger progress={progress} />
      ) : holding ? (
        <HeldVerdicts reviewed={reviewed} findings={ledger} />
      ) : (
        ledger
      )}
      {/* No questions here any more. A concluded review has none to ask — the
          summarising stage has no field for one, which is what stops the loop
          reopening — so the conclusion is the conclusion, and asking happens on its
          own surface before this page exists. */}
      {report && !running && !holding ? <Conclusion overview={report.overview} /> : null}
    </>
  );
}
