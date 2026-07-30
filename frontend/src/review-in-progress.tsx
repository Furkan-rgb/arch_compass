import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { api } from "./api";
import { ErrorPanel, sheet } from "./components";
import { RunProgress, type AwaitingAnswers, type RunPass, type RunState } from "./run-progress";
import { VERDICT_WORDS } from "./review-ledger";
import type { BoundaryReview, BoundaryReviewSummary, ReviewedBoundary } from "./types";

/**
 * The run behind a review — its stages, and every boundary it decided, in order.
 *
 * One surface, wherever it is watched from. There used to be two: the start step drew a run
 * it owned, and the review's own page drew a thinner version of the same thing from polled
 * counts. Two renderings of one fact drift, and the reader has to work out which of them to
 * believe. It is now a tab of the review, live while the run is live and readable afterwards
 * as the record of how that review was produced.
 *
 * It reads from whichever source knows more. The browser holding the stream has the boundary
 * names and each verdict as it lands; any other browser — a second tab, a reload, a run
 * started from the CLI — has the counts the run writes to its own record. Both are the same
 * run, and the panel says which of the two it is looking at rather than pretending the
 * thinner one is complete.
 */

/** The record's own counts, as the shape the flow already draws. */
export function progressFromSummary(
  summary: BoundaryReviewSummary | undefined,
): RunState {
  if (!summary || summary.boundaries_detected === null) return null;
  const total = summary.boundaries_detected ?? 0;
  return {
    total,
    // No names: the detected order is known only to the run that swept for them, and
    // inventing labels here would be presenting a guess as evidence.
    boundaries: [],
    verdicts: Array.from({ length: total }, () => null),
    judged: summary.boundaries_reviewed,
    // Which of the two set-wide calls is running is not in the counts — the record knows
    // only that every verdict has landed. It is reported as the one this pass will make,
    // which the row does know: a run that names the pass it answers concludes, and one that
    // does not asks.
    eliciting: total > 0 && summary.boundaries_reviewed >= total && !summary.elicited_from,
    summarising:
      total > 0 && summary.boundaries_reviewed >= total && Boolean(summary.elicited_from),
    // Read off the status rather than the counts, which cannot tell a run still in its last
    // call from one that finished it. `succeeded` is the only status that means concluded: a
    // held run has judged everything too and is emphatically not over, and the aftermaths
    // (failed, cancelled) never reach this flow at all — that page draws them as unfinished.
    concluded: summary.status === "succeeded",
  };
}

/** Whichever source knows more about the same run. */
export function watchedProgress(
  live: RunState | undefined,
  summary: BoundaryReviewSummary | undefined,
): RunState {
  if (live) return live;
  return progressFromSummary(summary);
}

/** One line per boundary, in the order the run reached it. */
export type CrawlEntry = {
  /** Its place in the detection order, which is the only thing that identifies it. */
  position: number;
  label: string | null;
  verdict: boolean | null;
  /** The one under the model right now. */
  live: boolean;
};

/**
 * The run's decisions as a crawl, from whichever of the two records has them.
 *
 * A finished review carries every verdict it reached, so its log is read off the report and
 * survives the stream that produced it. A running one has only what the stream has said so
 * far. No timestamps: the events carry none, and printing a clock the run never recorded
 * would be inventing evidence about when a model call happened.
 *
 * `withVerdicts` is false while a run is holding for answers. The verdicts exist and are in
 * the report this reads, and the whole of that state is that they are not reported yet — a
 * log that printed them here would be the reveal, taken out of the reader's hands.
 */
export function runCrawl(
  progress: RunState,
  reviewed: ReviewedBoundary[],
  withVerdicts = true,
): CrawlEntry[] {
  if (reviewed.length > 0) {
    return reviewed.map((item, index) => ({
      position: index + 1,
      label: item.candidate.participants[0]?.qualified_name ?? item.reference,
      verdict: withVerdicts ? item.material : null,
      live: false,
    }));
  }
  if (!progress) return [];
  const settled = progress.eliciting || progress.summarising || progress.concluded;
  return Array.from({ length: progress.total }, (_, index) => ({
    position: index + 1,
    label: progress.boundaries[index] ?? null,
    verdict: progress.verdicts[index] ?? null,
    live: index === progress.judged && !settled,
  }));
}

export function RunLog({
  review,
  progress,
  reviewed,
  watching,
  pass,
  awaiting = null,
  answersRecorded = null,
  withVerdicts = true,
}: {
  review: BoundaryReview;
  progress: RunState;
  /** The verdicts of a review that reached them, which is where a finished log comes from. */
  reviewed: ReviewedBoundary[];
  watching: boolean;
  pass: RunPass;
  awaiting?: AwaitingAnswers;
  answersRecorded?: number | null;
  /** False while the run holds: those verdicts are not reported anywhere until answered. */
  withVerdicts?: boolean;
}) {
  const client = useQueryClient();
  // Generated as optional because the server fills it in, but a review that has been
  // begun always carries one — this page was reached by that identifier.
  const reviewId = review.review_id ?? "";
  const running = review.status === "running";
  const cancel = useMutation({
    mutationFn: () => api.cancelReview(reviewId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["review", reviewId] }),
        client.invalidateQueries({ queryKey: ["reviews"] }),
      ]);
    },
  });
  const crawl = runCrawl(progress, reviewed, withVerdicts);

  return (
    // The stages and the crawl side by side, and stacked once the pair is narrower than the
    // two 280px columns it is: neither reads as a caption on the other.
    <div
      data-slot="run-log"
      className="grid grid-cols-[minmax(280px,0.9fr)_minmax(280px,1.1fr)] items-start gap-3 max-[860px]:grid-cols-[1fr]"
    >
      {/* Neither panel carries the sheet's standing gap: the two sit in one row, and a gap
          under them would be a gap under the row. */}
      <div className={cn(sheet, "mb-0 p-[var(--card-pad)]")}>
        <RunProgress
          progress={progress}
          pass={pass}
          awaiting={awaiting}
          answersRecorded={answersRecorded}
          // The crawl beside these names every boundary the run reached, so the stages do
          // not repeat the list underneath themselves.
          showBoundaries={false}
          heading={
            !running ? null : watching ? (
              <>
                This tab is running it. Leaving the page does not stop the run — it carries
                on and this page shows where it got to.
              </>
            ) : (
              <>
                Started elsewhere, so this page follows the run's own record: how far it has
                got, but not the boundary names, which are known to whoever started it.
              </>
            )
          }
        />
        {running ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule-soft pt-3">
            <Button
              type="button"
              variant="destructive"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              <Square size={13} aria-hidden fill="currentColor" />
              {cancel.isPending ? "Stopping…" : "Cancel this review"}
            </Button>
            <p className="m-0 flex-[1_1_24ch] text-meta leading-[1.5] text-ink-2">
              It stops after the boundary being judged right now, so up to one model call
              from here. The verdicts already reached are not kept: a review is every
              boundary or none.
            </p>
          </div>
        ) : null}
        {cancel.isError ? <ErrorPanel error={cancel.error} /> : null}
      </div>

      <div className={cn(sheet, "mb-0")}>
        <ol
          data-slot="run-crawl"
          className="m-0 grid max-h-[420px] list-none gap-px overflow-y-auto p-2"
        >
          {crawl.map((entry) => (
            <li key={entry.position} className={cn(crawlLine, entry.live && liveLine)}>
              <span className={crawlPosition}>{entry.position}</span>
              <b className={crawlLabel}>
                {entry.label
                  ? entry.live
                    ? `judging ${entry.label}…`
                    : `${entry.label} ${entry.verdict === null && withVerdicts ? "queued" : "judged"}`
                  : entry.live
                    ? "judging boundary…"
                    : `boundary ${entry.position}`}
              </b>
              <em
                className={cn(
                  crawlVerdict,
                  entry.verdict === null
                    ? ""
                    : entry.verdict
                      ? "text-material"
                      : "text-cleared",
                )}
              >
                {entry.verdict === null
                  ? ""
                  : entry.verdict
                    ? VERDICT_WORDS.material
                    : VERDICT_WORDS.cleared}
              </em>
            </li>
          ))}
          {crawl.length === 0 ? (
            <li className={crawlLine}>
              <span className={crawlPosition} />
              <b className={crawlLabel}>Nothing has been decided yet.</b>
              <em className={crawlVerdict} />
            </li>
          ) : null}
        </ol>
      </div>
    </div>
  );
}

/* One decision per line, in the face this product stores values in: a numbered column so
   the position is scannable, the boundary's own name, and the verdict at the end. */
const crawlLine =
  "grid grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 rounded-sm px-2 py-[3px] font-mono text-meta text-ink-2";
const liveLine = "bg-accent-soft text-accent-ink";
const crawlPosition = "text-right text-micro tabular-nums text-ink-3";
const crawlLabel = "overflow-hidden font-normal text-ellipsis whitespace-nowrap";
const crawlVerdict = "text-micro not-italic whitespace-nowrap";
