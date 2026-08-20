import { useQuery } from "@tanstack/react-query";

import { api, type ReviewRun } from "../../api";
import { humanise } from "../../lib/format";
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
  review_candidates: "Judging every candidate in one batch",
  generate_questions: "Asking what the repository cannot answer",
  compose_waiting_review: "Composing the review",
  compose_final_review: "Composing the review",
  record_waiting_review: "Recording the review",
  record_review: "Recording the review",
  revise_case: "Recording your answers on the case",
  select_candidates_for_rejudgement: "Choosing what to judge again",
};

export const stageLabel = (stage: string) => STAGE_LABELS[stage] ?? humanise(stage);

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
        {stages.map((stage: string, index: number) => {
          const last = index === stages.length - 1;
          const done = !last || settled;
          return (
            <li key={`${stage}-${index}`} className="flex items-center gap-2.5 text-sm">
              <span
                aria-hidden="true"
                className="grid size-5 shrink-0 place-items-center rounded-full border border-rule bg-surface-2 text-ink-3"
              >
                {done ? <CheckIcon /> : <Spinner />}
              </span>
              <span className={done ? "text-ink-2" : "font-medium text-ink"}>
                {stageLabel(stage)}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Batch judging is answered in minutes or hours, so the wait is stated rather than
          implied by a spinner that never stops. */}
      {state.stage === "review_candidates" ? (
        <Notice tone="working" title="Queued with the model">
          Every candidate went to the provider in one batch, which is metered separately from
          interactive requests and costs half. Batches usually return within the hour and are
          guaranteed within a day. Nothing is waiting on this window.
        </Notice>
      ) : null}

      {failed ? <ErrorNotice error={new Error(state.failure)} /> : null}

      <Mono className="text-[11px]">{state.run_id}</Mono>

      <LiveRegion>{failed ? "The review failed." : `${stageLabel(state.stage)}.`}</LiveRegion>
    </div>
  );
}
