import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";
import { humanise } from "../../lib/format";
import { Button, ButtonLink } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";

/** The workspace's node names, said the way a person would say them. */
const STAGE_LABELS: Record<string, string> = {
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

/**
 * A review being produced, watched by id.
 *
 * This page exists because the previous one did not: a review used to be held inside the
 * streaming response that produced it, so reloading the tab closed the connection and the
 * run was abandoned somewhere between two stages. Now the workspace owns the run and this
 * only watches it — which means the URL is worth bookmarking, the tab is worth closing,
 * and a judgement submitted as a batch can take as long as a batch takes.
 */
export function RunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();

  const run = useQuery({
    queryKey: ["review-run", runId],
    queryFn: () => api.reviewRun(runId),
    // Stop asking once there is nothing left to change.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ? 1500 : false;
    },
  });

  const state = run.data;
  const reviewId = state?.review_id ?? null;
  const settled = Boolean(state && state.status !== "running");

  // A review that exists is a better page than a review that is being made, so as soon as
  // one is composed this hands over. Replace, not push: the run is not a step in history a
  // reader wants the back button to return them to.
  useEffect(() => {
    if (reviewId && settled) navigate(`/reviews/${reviewId}`, { replace: true });
  }, [reviewId, settled, navigate]);

  if (run.isLoading) {
    return (
      <Panel>
        <PanelBody className="flex items-center gap-2 text-sm text-ink-3">
          <Spinner /> Finding the review…
        </PanelBody>
      </Panel>
    );
  }

  if (run.error || !state) {
    return (
      <ErrorNotice
        error={run.error || new Error("That review run could not be found")}
        title="No such run"
      />
    );
  }

  const stages = state.stages.length ? state.stages : ["load_context"];
  const failed = state.status === "failed";

  return (
    <div className="mx-auto max-w-2xl">
      <Panel>
        <PanelHeader
          title={failed ? "This review did not finish" : "Reviewing the repository"}
          description={
            failed
              ? "The run stopped at the stage below. Nothing was recorded as a verdict."
              : "This is running in the workspace, not in this tab. You can close it and come back to this address."
          }
        />
        <PanelBody className="grid gap-4">
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
                    {STAGE_LABELS[stage] ?? humanise(stage)}
                  </span>
                </li>
              );
            })}
          </ol>

          {/* Batch judging is answered in minutes or hours, so the wait is stated rather
              than implied by a spinner that never stops. */}
          {state.stage === "review_candidates" ? (
            <div className="rounded-md border border-held/30 bg-held-soft/40 px-3.5 py-3">
              <Label className="text-held">Queued with the model</Label>
              <p className="mt-1.5 text-sm leading-6 text-ink-2">
                Every candidate went to the provider in one batch, which is metered
                separately from interactive requests and costs half. Batches usually return
                within the hour and are guaranteed within a day. Nothing is waiting on this
                window.
              </p>
            </div>
          ) : null}

          {failed ? <ErrorNotice error={new Error(state.failure)} /> : null}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-3.5">
            <Mono className="text-[11px]">{state.run_id}</Mono>
            <div className="flex gap-2">
              <ButtonLink to="/reviews" variant="secondary" size="sm">
                Review history
              </ButtonLink>
              {reviewId ? (
                <Button size="sm" onClick={() => navigate(`/reviews/${reviewId}`)}>
                  Open the review
                </Button>
              ) : null}
              {failed ? (
                <ButtonLink to="/start" size="sm">
                  Start again
                </ButtonLink>
              ) : null}
            </div>
          </div>

          <LiveRegion>
            {failed
              ? "The review failed."
              : `${STAGE_LABELS[state.stage] ?? humanise(state.stage)}.`}
          </LiveRegion>
        </PanelBody>
      </Panel>
    </div>
  );
}
