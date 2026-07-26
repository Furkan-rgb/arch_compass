/**
 * How far a running review has got, and how that is shown.
 *
 * `judged` counts finished verdicts, so the boundary under judgement is the next one: the
 * count is derived from what has landed rather than from a separate "starting" message that
 * could disagree with it. Shared by both places a review can be started — the start step and
 * the review page's revise-and-review-again — because it is the same run either way.
 */
export type RunState = { total: number; boundaries: string[]; judged: number } | null;

import type { ReviewProgress } from "./types";

/** Fold one stream line into the run's state; anything else leaves it as it was. */
export function applyProgress(current: RunState, event: ReviewProgress): RunState {
  if (event.event === "detected") {
    return { total: event.total, boundaries: event.boundaries, judged: 0 };
  }
  if (event.event === "judged" && current) {
    return { ...current, judged: event.position };
  }
  return current;
}

export function RunProgress({ progress }: { progress: RunState }) {
  if (!progress) {
    return (
      <p className="run-progress" role="status">
        Sweeping the atlas for boundaries…
      </p>
    );
  }
  if (!progress.total) {
    return (
      <p className="run-progress" role="status">
        No boundaries to judge in this repository. Composing the review.
      </p>
    );
  }
  const position = Math.min(progress.judged + 1, progress.total);
  const current = progress.boundaries[position - 1];
  const done = progress.judged >= progress.total;
  return (
    <div className="run-progress" role="status" aria-live="polite">
      <p className="run-progress__line">
        {done ? (
          <>
            All <strong>{progress.total}</strong> boundaries judged. Composing the review.
          </>
        ) : (
          <>
            Judging boundary <strong>{position}</strong> of{" "}
            <strong>{progress.total}</strong>
            {current ? (
              <>
                {" · "}
                <code>{current}</code>
              </>
            ) : null}
          </>
        )}
      </p>
      <div
        className="run-progress__bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={progress.total}
        aria-valuenow={progress.judged}
      >
        <span style={{ width: `${(progress.judged / progress.total) * 100}%` }} />
      </div>
    </div>
  );
}
