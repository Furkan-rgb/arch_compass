import { cva } from "class-variance-authority";
import { Check, CircleCheck, CircleDot, Loader, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import type { ReviewProgress } from "./types";

/**
 * How far a running review has got, and how that is shown.
 *
 * A review is a sequence of stages and each fails to explain itself alone: a deterministic
 * sweep whose length nobody knows until it finishes, one model call per boundary, a call
 * over all of them, and — where the verdicts did not settle themselves — a stop, until a
 * person answers. A single spinner would make a two-minute run look like a hung request,
 * and a bare percentage would not say what is taking the time. So the flow is drawn as the
 * stages it actually has, with the boundaries named as their verdicts land.
 *
 * The seven stages span two runs. That is deliberate and it is what the reader experiences:
 * one journey, whose middle is theirs to supply. Each pass is its own immutable review
 * pinned to its own case revision, so the second cannot be a continuation of the first as a
 * record — but as a flow it plainly is, and drawing it as two unrelated three-stage runs
 * would hide the only part that needs explaining.
 *
 * `judged` counts finished verdicts, so the boundary under judgement is the next one: the
 * count is derived from what has landed rather than from a separate "starting" message that
 * could disagree with it. Shared by every place a review is watched — the start step, the
 * review page's revise-and-review-again, and the page that is holding for answers — because
 * it is the same run either way.
 */
export type RunState = {
  total: number;
  boundaries: string[];
  /** One entry per boundary, in detection order: `null` until that verdict lands. */
  verdicts: (boolean | null)[];
  judged: number;
  /** The first pass's last call: composing what it needs to ask. */
  eliciting: boolean;
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
      eliciting: false,
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
  if (event.event === "eliciting" && current) {
    return { ...current, judged: event.total, eliciting: true };
  }
  if (event.event === "summarising" && current) {
    return { ...current, judged: event.total, summarising: true };
  }
  return current;
}

type StageState = "waiting" | "active" | "done";

/*
  A stage says where it has got in two places and nowhere else: the marker beside it, and the
  weight of its own name. Filled with the accent while it is happening, the cleared verdict's
  own green once it is, and a quiet outline before its turn comes.

  Three complete sets rather than a base and two overrides, so which colour lands never rests
  on the order a generated stylesheet happens to emit two utilities in.
*/
const stageMarker = cva("grid size-5 place-items-center rounded-full border", {
  variants: {
    state: {
      waiting: "border-rule bg-surface text-ink-3",
      active: "border-primary bg-primary text-on-accent",
      done: "border-cleared-rule bg-cleared-soft text-cleared",
    },
  },
});
const stageTitle = cva("text-meta font-[650]", {
  variants: {
    state: { waiting: "text-ink-3", active: "text-ink", done: "text-ink-2" },
  },
});

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
    <li data-slot="run-stage" className="grid grid-cols-[auto_1fr] items-start gap-3">
      <span className={stageMarker({ state })} aria-hidden>
        {state === "done" ? (
          <Check size={13} />
        ) : state === "active" ? (
          <Loader size={13} className="spin" />
        ) : (
          <CircleDot size={13} />
        )}
      </span>
      <span className="grid min-w-0 gap-0.5">
        <strong className={stageTitle({ state })}>{title}</strong>
        {/* A span rather than the `small` this was: the one line of hand-written element CSS
            this workspace keeps gives every `<small>` the 12px step, it is unlayered, and no
            utility can outrank that. A stage's detail is the smallest step below it. */}
        <span className="text-micro leading-[1.5] text-ink-3">{detail}</span>
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

/**
 * Which half of the journey this run is. `1` judges and then asks; `2` judges again against
 * the answers and concludes.
 *
 * A second pass draws the first pass's stages as done rather than hiding them. They did
 * happen, they are what produced the questions the reader just answered, and a progress list
 * that started at "judge each boundary again" would leave the word "again" unexplained.
 */
export type RunPass = 1 | 2;

export function RunProgress({
  progress,
  heading,
  awaiting = null,
  pass = 1,
  answersRecorded = null,
  showBoundaries = true,
}: {
  progress: RunState;
  heading?: ReactNode;
  awaiting?: AwaitingAnswers;
  pass?: RunPass;
  /** The case revision the answers created, once they have been recorded. */
  answersRecorded?: number | null;
  /** False where the caller draws the boundaries itself, as the review's run log does. */
  showBoundaries?: boolean;
}) {
  const detected = progress !== null;
  const total = progress?.total ?? 0;
  const judged = progress?.judged ?? 0;
  const eliciting = progress?.eliciting ?? false;
  const summarising = progress?.summarising ?? false;
  const second = pass === 2;
  const judging: StageState = second
    ? "done"
    : !detected
      ? "waiting"
      : eliciting || summarising || judged >= total
        ? "done"
        : "active";
  // The one stage that does not end on its own. Every other step here finishes because the
  // application finished it; this one is waiting on a person, and it stays waiting across a
  // reload because it is derived from the stored review rather than from this page's state.
  const answering: StageState = second
    ? "done"
    : awaiting === null
      ? "waiting"
      : awaiting > 0
        ? "active"
        : "done";
  // On a second pass the first three stages are history, so their detail is stated rather
  // than counted: this run's own counters describe the *re*-judging below.
  const firstPassTotal = second ? null : total;

  return (
    <div data-slot="run-flow" className="grid gap-3" role="status" aria-live="polite">
      {heading ? (
        <p
          data-slot="run-heading"
          className="m-0 max-w-[84ch] text-meta leading-[1.55] text-ink-2"
        >
          {heading}
        </p>
      ) : null}
      <ol className="m-0 grid list-none gap-2 p-0">
        <Stage
          state={second || detected ? "done" : "active"}
          title="Sweep the atlas"
          detail={
            firstPassTotal === null ? (
              "The same atlas as the first pass — nothing about the code changed."
            ) : detected ? (
              firstPassTotal === 1 ? (
                "1 boundary found"
              ) : (
                `${firstPassTotal} boundaries found`
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
            second ? (
              "Judged against what the case said before you answered."
            ) : !detected ? (
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
        {/* Its own stage, and its own model call. A first pass does not compose a
            conclusion — there is usually no case to draw one from — so what happens here is
            only the merging: this is the only point that sees every hinge at once, where
            several boundaries turning on one fact become one question rather than several. */}
        {/* Done the moment there is a number of questions to report, whatever that number
            is: `awaiting` is written by the call this stage *is*, so knowing it means the
            call returned. Without this a concluded run left this stage spinning for ever. */}
        <Stage
          state={second ? "done" : awaiting !== null ? "done" : eliciting ? "active" : "waiting"}
          title="Ask what it needs to know"
          detail={
            second
              ? "The questions you answered were composed here."
              : "Only where a verdict turned on something it was not told — it asks rather than guesses."
          }
        />
        {/* Named for what the run does, not for a document it found wanting. Most runs now
            start with nothing written down at all, so "what the case does not say" would be
            describing a gap in something that does not exist — and it would read as the
            reader's omission rather than as the advisor asking for what it needs. */}
        <Stage
          state={answering}
          title="Answer the questions"
          detail={
            second ? (
              "Answered."
            ) : awaiting === null ? (
              "Nothing is reported until these are settled — a verdict reached without them can come out the other way."
            ) : awaiting > 0 ? (
              <>
                {awaiting === 1 ? "1 question is" : `${awaiting} questions are`} waiting on
                you. Answer what you know and leave the rest.
              </>
            ) : (
              "Nothing to ask — every verdict stood on what it already knew."
            )
          }
        />
        {/* A stage because it is a real and visible thing that happens to the reader's
            workspace, not because it takes time: their answers become a case, immutably and
            with a revision number, and that document is what the second pass is pinned to.
            Skipped over entirely by a first pass that had nothing to ask. */}
        <Stage
          state={second ? "done" : answering === "done" ? "done" : "waiting"}
          title="Write the case from your answers"
          detail={
            answersRecorded !== null ? (
              <>Recorded as revision {answersRecorded} of the case.</>
            ) : (
              "Your answers become a case revision you can read, revise and re-run."
            )
          }
        />
        <Stage
          state={
            second
              ? !detected
                ? "waiting"
                : summarising || judged >= total
                  ? "done"
                  : "active"
              : "waiting"
          }
          title="Judge each boundary again"
          detail={
            !second ? (
              "The same boundaries, against what you have just told it."
            ) : !detected ? (
              "One model call each, against the answered case and every policy."
            ) : (
              <>
                {judged} of {total} re-judged
              </>
            )
          }
        />
        <Stage
          state={second && summarising ? "active" : "waiting"}
          title="Read the verdicts as a set"
          detail="One last call: what they amount to together. This is the pass that concludes."
        />
      </ol>

      {/* The meter is for a run that is still counting. Once every verdict has landed and
          the questions are known, a full bar is a claim about progress nothing is making. */}
      {detected && total > 0 && (judged < total || awaiting === null) ? (
        <>
          <div
            className="h-1.5 overflow-hidden rounded-pill bg-sunken"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={judged}
          >
            <span
              className="block h-full rounded-pill bg-primary transition-[width] duration-250 ease-[ease]"
              style={{ width: `${(judged / total) * 100}%` }}
            />
          </div>
          {/* Named, not counted. A reader watching their own repository be judged wants to
              know which boundary is under the model right now, and a verdict that has
              already landed is worth seeing before the page it belongs to exists.
              The names come from the stream, so a watcher reading the run's stored record
              instead has the counts and says so rather than inventing labels for them. */}
          {showBoundaries && progress!.boundaries.length === 0 ? (
            <p className="m-0 text-ui leading-[1.5] text-ink-2">
              Which boundary is under the model right now is in the stream this run is
              writing, not in its record, so it is not shown here.
            </p>
          ) : null}
          {/* Scrolls rather than growing: a repository with sixty boundaries would otherwise
              push everything else on the page out from under the reader. */}
          <ul
            className="m-0 grid max-h-[260px] list-none gap-0.5 overflow-y-auto p-0"
            hidden={!showBoundaries}
          >
            {progress!.boundaries.map((name, index) => {
              const verdict = progress!.verdicts[index];
              const current = index === judged && !summarising && !eliciting;
              return (
                <li
                  key={`${name}-${index}`}
                  className={cn(
                    "grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-control px-2 py-1 text-ui",
                    // The one under the model right now is lifted onto a surface of its own:
                    // it is what a reader watching their code be judged is looking for.
                    current ? "bg-surface text-ink" : "text-ink-2",
                  )}
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
                  <code className="min-w-0 overflow-hidden text-ui text-ellipsis whitespace-nowrap">
                    {name}
                  </code>
                  <span className="text-meta whitespace-nowrap">
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
