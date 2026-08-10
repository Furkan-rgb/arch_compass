/** The Run log tab: what the run read, and the record of what it did with it. */

import { useQuery } from "@tanstack/react-query";

import { api } from "../../api";
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
  // A second pass carries no investigation of its own; the one behind its questions lives
  // on the pass that asked. Fetched here rather than threaded from the page: only this tab
  // wants it, and the query key matches the page's own review reads so a visited first
  // pass costs nothing to show again.
  const askedPass = useQuery({
    queryKey: ["review", review.elicited_from],
    queryFn: () => api.review(review.elicited_from!),
    enabled: !review.investigation && Boolean(review.elicited_from),
    staleTime: Infinity,
  });
  const investigation = review.investigation ?? askedPass.data?.investigation ?? null;
  const fromAskingPass = !review.investigation && Boolean(askedPass.data?.investigation);
  return (
    <>
      {/* The run's record of what it checked before asking — and the run log is now its
          only mount, so it cannot vanish when the questions do. A second pass never
          investigates (it judges answers and concludes), so its log shows the record of
          the pass that asked: the questions this pass answers were asked on the strength
          of that checking, and this run is the same run continued. */}
      {investigation ? (
        <InvestigationDisclosure
          investigation={investigation}
          note={fromAskingPass ? "from the pass that asked" : undefined}
          className={phoneFlush}
        />
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
