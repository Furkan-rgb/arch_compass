import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";

import { api } from "./api";
import { RunSignals, type RunPhase, type SettledPhase } from "./run-notice";
import { applyProgress, type RunState } from "./run-progress";

/**
 * How a finished stream is read as one of the three ways a run ends.
 *
 * The status is the server's word for it and this is the only place it is translated, so the
 * signals never have to know the wire's vocabulary. `succeeded` and `awaiting_answers` are the
 * two outcomes a run can reach on its own; anything else — cancelled, or a status this build
 * has not heard of — reached no verdicts, which is what `failed` means here and is a claim the
 * notice can make honestly whatever the exact reason was.
 */
function settledAs(status: string | undefined): SettledPhase {
  if (status === "awaiting_answers") return "holding";
  if (status === "succeeded") return "concluded";
  return "failed";
}

/**
 * The running review, held above the page that started it.
 *
 * A run is not a property of any page. It belongs to the request doing the work, and it
 * outlives whatever the reader is looking at — so keeping its progress inside the start
 * step meant leaving that page threw the detail away, and the review's own page had to
 * make do with polled counts even while a live stream was open in the same tab.
 *
 * So the run lives here, and there is exactly one place to watch it: the review's page.
 * Starting a run navigates there as soon as the stream says what the review is called,
 * which is before the first model call.
 */
export interface RunHandle {
  /** The review being produced right now, if this browser is the one producing it. */
  reviewId: string | null;
  /** Progress as the stream reported it; `null` until detection finishes. */
  progress: RunState;
  running: boolean;
  error: unknown;
  /**
   * Start a run. `elicitedFrom` names the first pass this one answers, which is what makes
   * it a second pass: it judges against the answered case and concludes rather than asking
   * again. Omitted for every review that was not reached by answering.
   */
  start: (
    caseId: string,
    repositoryRoot: string,
    elicitedFrom?: string | null,
  ) => void;
  /** True when this browser holds the live stream for that review. */
  watching: (reviewId: string) => boolean;
}

const RunContext = createContext<RunHandle | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [progress, setProgress] = useState<RunState>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  /**
   * How the last run ended, kept after it has ended.
   *
   * Not on `RunHandle`, because no page asks: the pages watch a review's own record, which
   * outlives this browser's memory of having produced it. This exists for the signals below,
   * whose entire subject is the transition — and a transition needs the state on both sides of
   * it to still be here one render later.
   */
  const [settled, setSettled] = useState<SettledPhase | null>(null);
  // Guards a second start while one is in flight. State would be a render behind, and two
  // streams would both write into one progress, which is a plausible double-click away.
  const inFlight = useRef(false);

  const start = useCallback(
    (caseId: string, repositoryRoot: string, elicitedFrom?: string | null) => {
      if (inFlight.current) return;
      inFlight.current = true;
      setReviewId(null);
      setProgress(null);
      setError(null);
      setSettled(null);
      setRunning(true);
      api
        .streamReview(
          caseId,
          repositoryRoot,
          (event) => {
            if (event.event === "started") {
              // The first line, and the only one that matters to navigation: from here the
              // review exists and can be opened, reloaded or cancelled from anywhere.
              setReviewId(event.review_id);
              navigate(`/reviews/${event.review_id}`);
              return;
            }
            setProgress((current) => applyProgress(current, event));
          },
          elicitedFrom,
        )
        .then(async (review) => {
          await Promise.all([
            client.invalidateQueries({ queryKey: ["reviews"] }),
            client.invalidateQueries({ queryKey: ["review", review.review_id] }),
          ]);
          // After the invalidations, so a reader the notice sends to the page finds the
          // record it is about rather than the stale one this run has just superseded.
          setSettled(settledAs(review.status));
        })
        .catch((failure: unknown) => {
          setError(failure);
          setSettled("failed");
        })
        .finally(() => {
          inFlight.current = false;
          setRunning(false);
          setProgress(null);
        });
    },
    [client, navigate],
  );

  const value = useMemo<RunHandle>(
    () => ({
      reviewId,
      progress,
      running,
      error,
      start,
      watching: (candidate: string) => running && candidate === reviewId,
    }),
    [error, progress, reviewId, running, start],
  );

  // `running` wins over the last outcome, so a second run started from the review page puts
  // the tab back to "Reviewing…" rather than leaving the previous run's word up while a new
  // one is in flight. `start` clears the outcome anyway; this makes the ordering irrelevant.
  const phase: RunPhase | null = running ? "running" : settled;

  return (
    <RunContext.Provider value={value}>
      {/* Beside the routes rather than inside one, for the same reason the run itself is held
          here: the moments worth reporting are exactly the ones where the reader is not on the
          page that would otherwise report them. */}
      <RunSignals phase={phase} reviewId={reviewId} />
      {children}
    </RunContext.Provider>
  );
}

export function useRun(): RunHandle {
  const handle = useContext(RunContext);
  if (handle === null) {
    throw new Error("useRun must be used inside a RunProvider");
  }
  return handle;
}
