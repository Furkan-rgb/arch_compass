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
import { applyProgress, type RunState } from "./run-progress";

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
        })
        .catch((failure: unknown) => setError(failure))
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

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunHandle {
  const handle = useContext(RunContext);
  if (handle === null) {
    throw new Error("useRun must be used inside a RunProvider");
  }
  return handle;
}
