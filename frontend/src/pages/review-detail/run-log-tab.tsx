/** The Run log tab: what the run read, and the record of what it did with it. */

import { phoneFlush } from "../../components";
import { InvestigationDisclosure } from "../../investigation-disclosure";
import { RunLog } from "../../review-in-progress";
import type { RunState } from "../../run-progress";
import type { ReviewDetail, ReviewedBoundary } from "../../types";

export function RunLogTab({
  review,
  progress,
  reviewed,
  watching,
  holding,
  running,
  openQuestionCount,
  answered,
  caseRevision,
}: {
  review: ReviewDetail;
  progress: RunState;
  reviewed: ReviewedBoundary[];
  watching: boolean;
  holding: boolean;
  running: boolean;
  openQuestionCount: number;
  /** How many answers the pinned case revision recorded, which is what dates the log. */
  answered: number;
  caseRevision: number | undefined;
}) {
  return (
    <>
      {/* The run's own record of what it checked before asking — or before
          concluding it had nothing to ask, which is the outcome with no questions
          tab to carry the disclosure. The run log always exists, so this is the
          mount a reader can rely on finding. */}
      {review.investigation ? (
        <InvestigationDisclosure investigation={review.investigation} className={phoneFlush} />
      ) : null}
      <RunLog
        review={review}
        progress={progress}
        reviewed={reviewed}
        watching={watching}
        pass={review.elicited_from ? 2 : 1}
        awaiting={holding ? openQuestionCount : running ? null : 0}
        answersRecorded={answered > 0 ? caseRevision : null}
        withVerdicts={!holding}
      />
    </>
  );
}
