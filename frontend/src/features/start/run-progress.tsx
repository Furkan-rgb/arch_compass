import { useQuery } from "@tanstack/react-query";

import { api, type ReviewRun } from "../../api";
import { humanise, plural } from "../../lib/format";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { ErrorNotice, LiveRegion, Notice, Spinner } from "../../ui/states";

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
  review_candidates: "Judging every candidate in one batch",
  investigate_hinges: "Checking what the repository can answer",
  generate_questions: "Asking what the repository cannot answer",
  write_waiting_synopsis: "Summarising what the review found",
  write_final_synopsis: "Summarising what the review found",
  compose_waiting_review: "Composing the review",
  compose_final_review: "Composing the review",
  record_waiting_review: "Recording the review",
  record_review: "Recording the review",
  revise_case: "Recording your answers on the case",
  select_candidates_for_rejudgement: "Choosing what to judge again",
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
  "review_candidates",
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
    queryFn: () => api.reviewRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });
}

/**
 * A review being produced, wherever that needs showing.
 *
 * Lives apart from the page that first held it because it is now wanted in two places: on
 * its own address, and in the right-hand pane of the review page when the lineage a reader
 * is looking at has a revision still being made. Those are the same thing seen from two
 * directions — "what is this run doing" — so they are one component rather than two that
 * drift.
 */
export function RunProgress({ state }: { state: ReviewRun }) {
  const settled = state.status !== "running";
  const failed = state.status === "failed";
  const stages = state.stages.length ? state.stages : ["load_context"];

  return (
    <div className="grid gap-4">
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
                {done ? <CheckIcon /> : <Spinner />}
              </span>
              <span className={done ? "text-ink-2" : "font-medium text-ink"}>
                {step.judging ? judgingLabel(state, done) : stageLabel(step.stage)}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Batch judging is answered in minutes or hours, so the wait is stated rather than
          implied by a spinner that never stops.

          Read off `batch` and never off `stage`. The stage says which node the graph is in,
          and the graph enters that node on a *prediction* — `supports_batch` is true for any
          Google key with batching switched on, and the provider is the only thing that knows
          whether it will actually take one. A key on a project that is not eligible for the
          Batch API is refused with `400 FAILED_PRECONDITION` and the review falls back to
          judging every candidate interactively, which is the right thing to do and was
          invisible: this panel went on telling the reader their review was queued as a batch,
          at half price, guaranteed within a day, for the whole of the fallback. None of those
          three was true, and the run now says which one it is. */}
      {state.batch === "queued" ? (
        <Notice tone="working" title="Queued with the model">
          Every candidate went to the provider in one batch, which is metered separately from
          interactive requests and costs half. Batches usually return within the hour and are
          guaranteed within a day. Nothing is waiting on this window.
        </Notice>
      ) : null}
      {state.batch === "unavailable" ? (
        <Notice title="Judging one candidate at a time">
          This model would not take the whole review as one batch, so it is being judged
          interactively instead. Nothing is lost — the verdicts are the same — but it is
          slower and it is metered as ordinary requests. On Google, batching needs billing
          enabled on the project behind the key.
        </Notice>
      ) : null}

      {failed ? <ErrorNotice error={new Error(state.failure)} /> : null}

      <Mono className="text-[11px]">{state.run_id}</Mono>

      <LiveRegion>{failed ? "The review failed." : `${stageLabel(state.stage)}.`}</LiveRegion>
    </div>
  );
}
