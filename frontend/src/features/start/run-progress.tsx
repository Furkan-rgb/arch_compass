import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, type ReviewRun } from "../../api";
import { humanise, plural, relativeTime } from "../../lib/format";
import { Button, CopyButton } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { useToast } from "../../ui/toast";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";

/** The workspace's node names, said the way a person would say them. */
export const STAGE_LABELS: Record<string, string> = {
  load_context: "Loading the architecture case",
  analyze_repository: "Indexing the repository",
  detect_candidates: "Detecting architecture candidates",
  calculate_delta: "Comparing against the previous review",
  select_initial_candidates: "Choosing what to judge",
  load_policy_corpus: "Loading the policy corpus",
  retrieve_policy_set: "Retrieving the policies that bear on each candidate",
  judge_candidate: "Judging candidates",
  review_candidate: "Judging candidates",
  generate_questions: "Asking what the repository cannot answer",
  write_waiting_synopsis: "Summarising what the review found",
  write_final_synopsis: "Summarising what the review found",
  compose_waiting_review: "Composing the review",
  compose_final_review: "Composing the review",
  record_waiting_review: "Recording the review",
  record_review: "Recording the review",
  await_answers: "Waiting for your answers",
  // LangGraph's own name for the pause, which arrives in the stage list beside ours.
  __interrupt__: "Waiting for your answers",
  revise_case: "Recording your answers on the case",
  select_candidates_for_rejudgement: "Choosing what to judge again",
  seal_case: "Writing this review's case revision",
};

export const stageLabel = (stage: string) => STAGE_LABELS[stage] ?? humanise(stage);

/**
 * The stages that are one candidate's turn through the loop.
 *
 * They are one step of the review however many times the graph enters them. Listed
 * separately they were the whole progress list: fifteen candidates arrived as thirty rows
 * of `Judging candidates` and `Review candidate` alternating, which reads as a stuck run
 * rather than a working one, and buried the eight steps that are genuinely different from
 * each other.
 */
const JUDGING_STAGES = new Set([
  "retrieve_policy_set",
  "review_candidate",
  "judge_candidate",
]);

type Step = { key: string; stage: string; judging: boolean };

/** The stage log as steps: consecutive turns through the candidate loop become one. */
export function progressSteps(stages: readonly string[]): Step[] {
  const steps: Step[] = [];
  stages.forEach((stage, index) => {
    const judging = JUDGING_STAGES.has(stage);
    if (judging && steps[steps.length - 1]?.judging) return;
    steps.push({ key: `${stage}-${index}`, stage, judging });
  });
  return steps;
}

/**
 * How far through its candidates a round is, or nothing where there is nothing to say.
 *
 * A depth, not a stage — which is why it is a count rather than another row. The counts are
 * absent on a run that has not selected yet and on one resumed after a restart, and the
 * step falls back to its plain label rather than claiming `0 of 0`.
 *
 * Both halves of a candidate's turn are said, because only one of them used to be and it is
 * the shorter one. Retrieval runs first and is most of the wait; while it was uncounted this
 * line read "Judging candidate 1 of 50" from the moment the round selected — a claim about a
 * candidate nothing had looked at yet, on a number that then sat still long enough to read
 * as a stuck run. It says what is actually happening now, and the number under it moves.
 */
function judgingLabel(state: ReviewRun, done: boolean): string {
  const total = state.candidates_to_judge ?? 0;
  const judged = state.candidates_judged ?? 0;
  const retrieved = state.candidates_retrieved ?? 0;
  if (!total) return "Judging candidates";
  if (done) return `Judged ${plural(total, "candidate")}`;
  // Judging is the later half, so any judgement at all means retrieval is no longer what a
  // reader is waiting on — and a resumed run reports no retrievals but may report verdicts.
  if (judged || !retrieved) {
    return `Judging candidate ${Math.min(judged + 1, total)} of ${total}`;
  }
  return `Retrieving policies for candidate ${Math.min(retrieved, total)} of ${total}`;
}

/** Poll a run while it is running, and stop the moment there is nothing left to change. */
export function useReviewRun(runId: string) {
  return useQuery({
    queryKey: ["review-run", runId],
    queryFn: ({ signal }) => api.reviewRun(runId, signal),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });
}

/**
 * How often the elapsed line is re-read, which is not how often the run is polled.
 *
 * "Started 4 minutes ago" is only ever wrong by less than the unit it is printed in, so a
 * second's precision would be a render a second for a sentence that changes once a minute.
 * The clock stops with the run, because a settled run's elapsed time is a fact rather than a
 * thing that goes on growing.
 */
const TICK_MS = 15_000;

function useTicking(live: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, [live]);
  return now;
}

/**
 * What is left, at the rate this run has actually managed — and nothing at all where that
 * rate is not yet measurable.
 *
 * Two candidates rather than one, because one is not a rate: the corpus is loaded and the
 * first policies are retrieved inside the same stretch, so a single candidate's elapsed time
 * is mostly setup and extrapolating from it overstates the wait by minutes. And it says "at
 * this rate" rather than naming a finishing time, because it is an extrapolation from a
 * handful of samples and a slow candidate can change the rate underneath it.
 */
function estimateLeft(state: ReviewRun, now: number): string | null {
  const total = state.candidates_to_judge ?? 0;
  const judged = state.candidates_judged ?? 0;
  if (judged < 2 || total <= judged) return null;
  const started = state.started_at ? Date.parse(state.started_at) : Number.NaN;
  if (Number.isNaN(started)) return null;
  const elapsed = now - started;
  if (elapsed <= 0) return null;
  const minutes = Math.round(((elapsed / judged) * (total - judged)) / 60_000);
  return minutes < 1
    ? "under a minute left at this rate"
    : `about ${plural(minutes, "minute")} left at this rate`;
}

/**
 * A review being produced, wherever that needs showing.
 *
 * Lives apart from the page that first held it because it is now wanted in two places: on
 * its own address, and in the right-hand pane of the review page when the lineage a reader
 * is looking at has a revision still being made. Those are the same thing seen from two
 * directions — "what is this run doing" — so they are one component rather than two that
 * drift.
 *
 * `onCancel` is optional because stopping a run belongs to the page a reader went to in order
 * to watch it, and not to a pane on the review page that is reporting one revision of a
 * lineage in passing.
 */
export function RunProgress({
  state,
  onCancel,
  cancelling = false,
}: {
  state: ReviewRun;
  onCancel?: () => void;
  cancelling?: boolean;
}) {
  const settled = state.status !== "running";
  const failed = state.status === "failed";
  const stages = state.stages.length ? state.stages : ["load_context"];
  const now = useTicking(!settled);
  const left = settled ? null : estimateLeft(state, now);

  return (
    <div className="grid gap-4">
      {/* A run measured in minutes had no clock on it at all, so "is this moving" could only
          be answered by watching the stage list and remembering what it said. */}
      {state.started_at ? (
        <p className="text-xs text-ink-3">
          Started {relativeTime(state.started_at, now)}
          {left ? <> · {left}</> : null}
        </p>
      ) : null}

      <ol className="grid gap-2.5" aria-label="Review progress">
        {progressSteps(stages).map((step, index, steps) => {
          const last = index === steps.length - 1;
          const done = !last || settled;
          return (
            <li key={step.key} className="flex items-center gap-2.5 text-sm">
              <span
                aria-hidden="true"
                className="grid size-5 shrink-0 place-items-center rounded-full border border-rule bg-surface-2 text-ink-3"
              >
                {done ? <CheckIcon /> : <Spinner label="" />}
              </span>
              <span className={done ? "text-ink-2" : "font-medium text-ink"}>
                {step.judging ? judgingLabel(state, done) : stageLabel(step.stage)}
              </span>
            </li>
          );
        })}
      </ol>

      {/* No retry on this one, deliberately. Every other `ErrorNotice` in this flow reports a
          request that a second attempt might answer; this reports a run that already ended.
          The way on is a new run, which the page's head offers as "Start again" with the
          repository carried into it. */}
      {failed ? <ErrorNotice error={new Error(state.failure)} /> : null}

      {/* The run id was a bare mono line with nothing beside it, which reads as a rendering
          leftover rather than as the identifier the workspace files this job under. It is
          worth copying — it is what a log line and a support question both need — so it says
          what it is and offers to be taken. */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-rule pt-3">
        <div className="flex min-w-0 items-center gap-2">
          <Label className="shrink-0">Run</Label>
          <Mono className="min-w-0 truncate text-[11px] text-ink-3">{state.run_id}</Mono>
          <CopyButton value={state.run_id} label="Copy the run id" />
        </div>
        {onCancel && !settled ? (
          <Button variant="secondary" size="sm" disabled={cancelling} onClick={onCancel}>
            {cancelling ? (
              <>
                <Spinner label="" /> Stopping…
              </>
            ) : (
              "Stop this run"
            )}
          </Button>
        ) : null}
      </div>

      <LiveRegion>{failed ? "The review failed." : `${stageLabel(state.stage)}.`}</LiveRegion>
    </div>
  );
}

/**
 * One notification when a rejudgement lands, armed and fired from above the thing it is about.
 *
 * `NotifyWhenDone` cannot do this job, and the difference is where each of them lives. On the
 * run's own page the component sits beside a query that keeps answering with the run after it
 * has finished, so it observes `done` and fires. On the review page it sat inside the round's
 * card, and `GET /api/reviews/runs` lists only what is still running — so the moment the work
 * finished the run left the list, the card unmounted, and the effect that owed somebody a
 * notification went with it. A reviewer who pressed the button, granted permission and read
 * "You will be told when it is done" was never told.
 *
 * So the arming lives on the page, which stays mounted, and the card renders the control. The
 * signal is the run *leaving* — the same signal `useRunsBecomeReviews` reads, and the only one
 * available, because a finished run is not something this endpoint ever reports.
 */
export function useRejudgementNotice(
  run: ReviewRun | null,
  /**
   * Every run currently in flight, which is what says a watched one has ended.
   *
   * Separate from `run` because `run` is narrowed to this review's own rejudgement and goes
   * null for a second reason: the page is between reviews. Opening another revision leaves
   * the review query with no data for a render, `run` collapses to null with the work still
   * running, and reading that as completion fired a notification saying a review had finished
   * judging while it was half way through — and disarmed, so the real ending was never
   * announced. A run is listed until it is genuinely done, so leaving the list is the only
   * signal that means what this needs it to mean. `undefined` is the list not having answered
   * yet, which is not an absence.
   */
  inFlight: readonly ReviewRun[] | undefined,
): {
  supported: boolean;
  armed: boolean;
  arm: () => Promise<boolean>;
} {
  const [armed, setArmed] = useState(false);
  // What was running when we last looked. Held in a ref rather than state because it is read
  // by the effect that watches for its disappearance and must not itself cause a render. The
  // message is kept rather than the number it is built from: by the time this fires the run
  // is gone from every listing, so anything not written down while it was here is lost.
  const watching = useRef<{ id: string; headline: string } | null>(null);
  // Joined so the effect depends on a value rather than on an array identity — the query
  // hands back a fresh array on every poll.
  const listed = (inFlight ?? [])
    .map((item) => item.run_id)
    .sort()
    .join(" ");

  useEffect(() => {
    const held = watching.current;
    // A promise already made outranks the run currently in view. This page is not remounted
    // when the reader walks to another review — the route carries no key — so arming on one
    // rejudgement and then opening a second one used to rewrite what was being watched: the
    // notification went to whichever run happened to finish first, named the wrong review,
    // and consumed the arming, so the one somebody actually asked about was never announced.
    const takeOver = !armed || !held || held.id === run?.run_id;
    if (run && run.status === "running" && takeOver) {
      watching.current = {
        id: run.run_id,
        // "finished judging" claimed which of four endings it was. A run leaves the listing
        // on all of them — finished, failed, stopped, and paused to ask another round, which
        // `record_waiting_review` reaches by writing `awaiting_answers` over `running`
        // mid-stream. By the time this fires the run is gone and none of them can be told
        // apart, so it says the one thing true of every one of them.
        headline: run.sequence
          ? `Review ${run.sequence} has finished running`
          : "The review has finished running",
      };
      return;
    }
    const gone = watching.current;
    // The listing not having answered yet is not the run having ended.
    if (!gone || inFlight === undefined) return;
    if (listed.split(" ").includes(gone.id)) return;
    watching.current = null;
    if (!armed) return;
    setArmed(false);
    if (typeof Notification !== "undefined") {
      new Notification("ArchCompass", { body: gone.headline });
    }
  }, [run, armed, listed, inFlight]);

  const arm = async () => {
    if (typeof Notification === "undefined") return false;
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return false;
    setArmed(true);
    return true;
  };

  return { supported: typeof Notification !== "undefined", armed, arm };
}

/**
 * What a rejudgement is doing, said where somebody committed to it.
 *
 * A one-line version of `RunProgress` for the place a reviewer presses the button rather than
 * the place they go to watch. Three facts and no stage list: how much work is running, how
 * long it looks like taking, and that it survives the tab — which is the one a person needs
 * before deciding whether to wait. The estimate is the same `estimateLeft` the progress panel
 * uses, so the two cannot disagree.
 *
 * The notice is passed in rather than owned here, because this component does not outlive the
 * work it describes — see `useRejudgementNotice`.
 */
export function RejudgementNote({
  run,
  notice,
}: {
  run: ReviewRun;
  notice?: ReturnType<typeof useRejudgementNotice>;
}) {
  const toast = useToast();
  const running = run.status === "running";
  const now = useTicking(running);
  const left = running ? estimateLeft(run, now) : null;
  const total = run.candidates_to_judge ?? 0;

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-md border border-rule bg-sunken px-3 py-2.5">
      <p className="flex min-w-0 items-center gap-2 text-xs leading-5 text-ink-2">
        {running ? <Spinner label="" /> : <CheckIcon />}
        {/* Read off the run rather than assumed from the fact that one exists. Answering does
            not always rejudge: *Conclude with remaining uncertainty* seals without selecting
            a single candidate, so `select_candidates_for_rejudgement` never runs and
            `candidates_to_judge` stays zero for the life of that run. Saying "Judging again"
            there put a false sentence directly above the progress panel on the same screen,
            which was correctly listing "Writing this review's case revision". A count of zero
            is not a rejudgement, so the stage says what is happening instead. */}
        <span className="min-w-0">
          {!running
            ? "This run has finished."
            : total
              ? `Judging ${plural(total, "candidate")} again${
                  left ? ` — ${left}` : ""
                }. This runs in the workspace, not in this tab, so you can close it.`
              : `${
                  run.stage ? stageLabel(run.stage) : "Working"
                }. This runs in the workspace, not in this tab, so you can close it.`}
        </span>
      </p>
      {notice?.supported && running ? (
        notice.armed ? (
          <span className="text-xs text-ink-3">You will be told when it is done.</span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              if (!(await notice.arm())) {
                toast.warn("This browser is set not to show notifications from this page.");
              }
            }}
          >
            Tell me when it is done
          </Button>
        )
      ) : null}
    </div>
  );
}

/**
 * One notification when the review lands, asked for and never assumed.
 *
 * A review is minutes long and this page says as much, which makes going and doing something
 * else the ordinary case — and then nothing told anybody it had finished. The browser's own
 * permission prompt is the wrong thing to spend on arrival, though: a page that asks before
 * the reader has any reason to want one is the pattern every browser now buries. So the offer
 * is a control, the prompt is the reader pressing it, and a refusal is remembered by the
 * browser rather than asked again here.
 *
 * Absent entirely where the browser has no `Notification` — which is also the path jsdom
 * takes, so no test has to stub one.
 */
export function NotifyWhenDone({ done, headline }: { done: boolean; headline: string | null }) {
  const toast = useToast();
  const [armed, setArmed] = useState(false);
  const fired = useRef(false);

  useEffect(() => {
    if (!armed || !done || fired.current || !headline) return;
    fired.current = true;
    new Notification("ArchCompass", { body: headline });
  }, [armed, done, headline]);

  if (typeof Notification === "undefined" || done) return null;
  if (armed) {
    return <span className="text-xs text-ink-3">You will be told when it is done.</span>;
  }
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={async () => {
        const permission = await Notification.requestPermission();
        if (permission === "granted") setArmed(true);
        else toast.warn("This browser is set not to show notifications from this page.");
      }}
    >
      Tell me when it is done
    </Button>
  );
}
