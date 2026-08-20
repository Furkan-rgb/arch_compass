import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button, ButtonLink } from "../../ui/button";
import { Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { RunProgress, useReviewRun } from "./run-progress";

/**
 * A review being produced, watched by id.
 *
 * This page exists because the previous one did not: a review used to be held inside the
 * streaming response that produced it, so reloading the tab closed the connection and the
 * run was abandoned somewhere between two stages. Now the workspace owns the run and this
 * only watches it — which means the URL is worth bookmarking, the tab is worth closing,
 * and a judgement submitted as a batch can take as long as a batch takes.
 *
 * It is no longer the only way back to a run. A run in flight is listed on the reviews page
 * and, once its lineage has a review to show it beside, in that review's revision rail —
 * because an address is only findable by somebody still holding it.
 */
export function RunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const run = useReviewRun(runId);

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

  const failed = state.status === "failed";

  return (
    <div className="mx-auto max-w-2xl">
      <Panel>
        <PanelHeader
          title={failed ? "This review did not finish" : "Reviewing the repository"}
          description={
            failed
              ? "The run stopped at the stage below. Nothing was recorded as a verdict."
              : "This is running in the workspace, not in this tab. You can close it and come back to this address, or find it on the reviews page."
          }
        />
        <PanelBody className="grid gap-4">
          <RunProgress state={state} />

          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-rule pt-3.5">
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
        </PanelBody>
      </Panel>
    </div>
  );
}
