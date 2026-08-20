import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";
import { useIsTabletUp } from "../../lib/media";
import { Tag } from "../../ui/badge";
import { ButtonLink } from "../../ui/button";
import { GitBranchIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { RevisionRail, lineageOf } from "../review/revision-rail";
import { RunProgress, useReviewRun } from "./run-progress";

/**
 * The revision being made, read as a revision.
 *
 * A run is filed under exactly what a review is filed under — a repository, a branch, a case
 * — and the sequence it will take is known from the newest review on that branch. So this is
 * not a job page with a thread id on it: it is review N of a lineage, opened at its own
 * address, with the same head and the same rail as the revisions on either side of it.
 *
 * What it does not have is a composed review, so the surfaces that read one are absent
 * rather than empty: no atlas, no delta, no evidence, no attention queue. In the pane where
 * the findings will go is the only thing there is to say about a review that has not been
 * composed, which is how far the run has got. It stays here until the review exists, and
 * then hands over to it.
 */
export function RunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const isTabletUp = useIsTabletUp();

  const run = useReviewRun(runId);
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });

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
  const lineage = lineageOf(reviews.data ?? [], state.branch_id, state.case_id);
  const sequence = state.sequence ?? lineage.length + 1;

  return (
    <div>
      <header className="mb-5">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
              Review {sequence} · {failed ? "did not finish" : "in progress"}
            </div>
            <h1 className="mt-1.5 max-w-3xl font-display text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-[30px]">
              Architecture review of {state.repository_name || "this repository"}
            </h1>
            <div className="mt-2.5 flex max-w-full flex-wrap items-center gap-1.5">
              {state.repository_root ? (
                <Mono className="min-w-0 truncate text-[11px] text-ink-3">
                  {state.repository_root}
                </Mono>
              ) : null}
              {state.branch_name ? (
                <Tag>
                  <GitBranchIcon className="size-3.5 shrink-0 text-ink-3" aria-hidden="true" />
                  <span className="sr-only">branch</span>
                  {state.branch_name}
                </Tag>
              ) : null}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <ButtonLink to="/reviews" variant="secondary">
              Review history
            </ButtonLink>
            {failed ? <ButtonLink to="/start">Start again</ButtonLink> : null}
          </div>
        </div>
      </header>

      <div
        className={
          isTabletUp
            ? "grid min-h-0 items-start gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]"
            : "grid min-h-0 items-start gap-6"
        }
      >
        {isTabletUp ? (
          <div className="lg:sticky lg:top-20">
            <Panel>
              <RevisionRail reviews={lineage} pending={state} pendingCurrent />
            </Panel>
          </div>
        ) : null}

        <div className="min-w-0">
          <Panel>
            <PanelHeader
              title={failed ? "This review did not finish" : "Reviewing the repository"}
              description={
                failed
                  ? "The run stopped at the stage below. Nothing was recorded as a verdict."
                  : "This is running in the workspace, not in this tab. You can close it and come back to this address, or find it on the reviews page. Its findings appear here as soon as they are composed."
              }
            />
            <PanelBody>
              <RunProgress state={state} />
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}
