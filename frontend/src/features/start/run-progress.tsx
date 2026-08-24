import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type ReviewRun } from "../../api";
import { humanise, plural, relativeTime } from "../../lib/format";
import { Button, CopyButton } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Label } from "../../ui/panel";
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
  investigate_hinges: "Checking what the repository can answer",
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
 */
function judgingLabel(state: ReviewRun, done: boolean): string {
  const total = state.candidates_to_judge ?? 0;
  const judged = state.candidates_judged ?? 0;
  if (!total) return "Judging candidates";
  if (done) return `Judged ${plural(total, "candidate")}`;
  return `Judging candidate ${Math.min(judged + 1, total)} of ${total}`;
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
