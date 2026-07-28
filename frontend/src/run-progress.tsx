import { Check, CircleCheck, CircleDot, Loader, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { ReviewProgress } from "./types";

/**
 * How far a running review has got, and how that is shown.
 *
 * A review is three stages, and each fails to explain itself alone: a deterministic sweep
 * whose length nobody knows until it finishes, one model call per boundary, and a last call
 * over all of them. A single spinner would make a two-minute run look like a hung request,
 * and a bare percentage would not say what is taking the time. So the flow is drawn as the
 * stages it actually has, with the boundaries named as their verdicts land.
 *
 * `judged` counts finished verdicts, so the boundary under judgement is the next one: the
 * count is derived from what has landed rather than from a separate "starting" message that
 * could disagree with it. Shared by both places a review can be started — the start step and
 * the review page's revise-and-review-again — because it is the same run either way.
 */
export type RunState = {
  total: number;
  boundaries: string[];
  /** One entry per boundary, in detection order: `null` until that verdict lands. */
  verdicts: (boolean | null)[];
  judged: number;
  summarising: boolean;
} | null;

/** Fold one stream line into the run's state; anything else leaves it as it was. */
export function applyProgress(current: RunState, event: ReviewProgress): RunState {
  if (event.event === "detected") {
    return {
      total: event.total,
      boundaries: event.boundaries,
      verdicts: Array.from({ length: event.total }, () => null),
      judged: 0,
      summarising: false,
    };
  }
  if (event.event === "judged" && current) {
    // Written by position, which is the only thing that identifies a boundary in the
    // stream. Two boundaries can share a name; their positions cannot collide.
    const verdicts = [...current.verdicts];
    verdicts[event.position - 1] = event.material;
    return { ...current, verdicts, judged: event.position };
  }
  if (event.event === "summarising" && current) {
    return { ...current, judged: event.total, summarising: true };
  }
  return current;
}

type StageState = "waiting" | "active" | "done";

function Stage({
  state,
  title,
  detail,
}: {
  state: StageState;
  title: string;
  detail: ReactNode;
}) {
  return (
    <li className={`run-flow__stage run-flow__stage--${state}`}>
      <span className="run-flow__marker" aria-hidden>
        {state === "done" ? (
          <Check size={13} />
        ) : state === "active" ? (
          <Loader size={13} className="spin" />
        ) : (
          <CircleDot size={13} />
        )}
      </span>
      <span className="run-flow__stage-body">
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
    </li>
  );
}

/**
 * How many answers the run is waiting on, once it knows.
 *
 * `null` while the run is still producing verdicts — nothing can be said about questions
 * that have not been composed yet. `0` once it has finished and asked nothing. A positive
 * number is a run that is not over: it has judged everything it can against what it was
 * told, and what happens next is the reader's to supply.
 */
export type AwaitingAnswers = number | null;

export function RunProgress({
  progress,
  heading,
  awaiting = null,
}: {
  progress: RunState;
  heading?: ReactNode;
  awaiting?: AwaitingAnswers;
}) {
  const detected = progress !== null;
  const total = progress?.total ?? 0;
  const judged = progress?.judged ?? 0;
  const summarising = progress?.summarising ?? false;
  const judging: StageState = !detected
    ? "waiting"
    : summarising || judged >= total
      ? "done"
      : "active";
  // The one stage that does not end on its own. Every other step here finishes because the
  // application finished it; this one is waiting on a person, and it stays waiting across a
  // reload because it is derived from the stored review rather than from this page's state.
  const answering: StageState =
    awaiting === null ? "waiting" : awaiting > 0 ? "active" : "done";

  return (
    <div className="run-flow" role="status" aria-live="polite">
      {heading ? <p className="run-flow__heading">{heading}</p> : null}
      <ol className="run-flow__stages">
        <Stage
          state={detected ? "done" : "active"}
          title="Sweep the atlas"
          detail={
            detected ? (
              total === 1 ? (
                "1 boundary found"
              ) : (
                `${total} boundaries found`
              )
            ) : (
              <>Parsing is deterministic, so this part is quick.</>
            )
          }
        />
        <Stage
          state={judging}
          title="Judge each boundary"
          detail={
            !detected ? (
              "One model call each, against the case and every policy."
            ) : total === 0 ? (
              "Nothing to judge in this repository."
            ) : (
              <>
                {judged} of {total} judged
              </>
            )
          }
        />
        {/* Named for both things this call does. It composes the conclusion *and* the
            questions, because a verdict that rested on something the case did not say
            records what that was, and this is the only stage that sees all of those at
            once — where several boundaries turning on one fact become one question rather
            than several. A reader watching the run should know the questions are coming
            from here rather than wondering where they appeared from. */}
        <Stage
          state={summarising ? "active" : "waiting"}
          title="Read the verdicts as a set"
          detail="One last call: what they amount to together, and what is still worth asking."
        />
        {/* Named for what the run does, not for a document it found wanting. Most runs now
            start with nothing written down at all, so "what the case does not say" would be
            describing a gap in something that does not exist — and it would read as the
            reader's omission rather than as the advisor asking for what it needs. */}
        <Stage
          state={answering}
          title="Ask questions if needed"
          detail={
            awaiting === null ? (
              "Only where a verdict turned on something it was not told — it asks rather than guesses."
            ) : awaiting > 0 ? (
              <>
                {awaiting === 1 ? "1 question is" : `${awaiting} questions are`} waiting on
                you. The review carries on against your answers.
              </>
            ) : (
              "Nothing to ask — every verdict stood on what it already knew."
            )
          }
        />
      </ol>

      {detected && total > 0 ? (
        <>
          <div
            className="run-progress__bar"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={judged}
          >
            <span style={{ width: `${(judged / total) * 100}%` }} />
          </div>
          {/* Named, not counted. A reader watching their own repository be judged wants to
              know which boundary is under the model right now, and a verdict that has
              already landed is worth seeing before the page it belongs to exists.
              The names come from the stream, so a watcher reading the run's stored record
              instead has the counts and says so rather than inventing labels for them. */}
          {progress!.boundaries.length === 0 ? (
            <p className="run-flow__nameless">
              Which boundary is under the model right now is in the stream this run is
              writing, not in its record, so it is not shown here.
            </p>
          ) : null}
          <ul className="run-flow__boundaries">
            {progress!.boundaries.map((name, index) => {
              const verdict = progress!.verdicts[index];
              const current = index === judged && !summarising;
              return (
                <li
                  key={`${name}-${index}`}
                  className={`run-flow__boundary ${
                    current ? "run-flow__boundary--current" : ""
                  }`}
                >
                  {verdict === null ? (
                    current ? (
                      <Loader size={12} className="spin" aria-hidden />
                    ) : (
                      <CircleDot size={12} aria-hidden />
                    )
                  ) : verdict ? (
                    <TriangleAlert size={12} aria-hidden />
                  ) : (
                    <CircleCheck size={12} aria-hidden />
                  )}
                  <code>{name}</code>
                  <span className="run-flow__boundary-verdict">
                    {verdict === null
                      ? current
                        ? "judging…"
                        : "waiting"
                      : verdict
                        ? "should change"
                        : "earning its place"}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}
