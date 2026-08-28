import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type ReviewRun } from "../../api";
import { useIsTabletUp } from "../../lib/media";
import { Button, ButtonLink } from "../../ui/button";
import { Mono } from "../../ui/meta";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { RevisionRail, lineageOf } from "../review/revision-rail";
import { NotifyWhenDone, RunProgress, useReviewRun } from "./run-progress";

/**
 * What the browser tab says while a review is being made.
 *
 * A run is minutes long and this page's own copy tells the reader they can go and do
 * something else — and then nothing outside this page said anything at all: no title, no
 * signal, nothing when it landed. The tab is the one surface that survives being left, so it
 * carries the same sentence the progress list is showing.
 */
function tabTitle(state: ReviewRun): string {
  if (state.status === "failed") return "Review did not finish";
  if (state.status === "cancelled") return "Review stopped";
  if (state.status !== "running") return "Review ready";
  const total = state.candidates_to_judge ?? 0;
  const judged = state.candidates_judged ?? 0;
  if (total) return `Judging ${Math.min(judged + 1, total)} of ${total}`;
  return "Review in progress";
}

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
  const client = useQueryClient();
  const isTabletUp = useIsTabletUp();

  const run = useReviewRun(runId);
  // The lineage needs a number, a status and a date off each revision and nothing else, so it
  // reads the projection rather than pulling every stored review's whole atlas across to draw
  // a rail of six lines.
  const reviews = useQuery({ queryKey: ["reviews", "summary"], queryFn: api.reviewSummaries });

  const state = run.data;
  const reviewId = state?.review_id ?? null;
  const settled = Boolean(state && state.status !== "running");

  const cancel = useMutation({
    mutationFn: () => api.cancelRun(runId),
    onSuccess: async (stopped) => {
      // The run keeps its id and its stages under `cancelled`, so the address this page is
      // already watching goes on answering and there is nowhere to navigate to.
      client.setQueryData(["review-run", runId], stopped);
      await client.invalidateQueries({ queryKey: ["review-runs"] });
    },
  });

  /**
   * Where the keyboard goes when the button it was standing on removes itself.
   *
   * Stopping a run flips the status to `cancelled`, and the footer's whole control set is
   * gated on the run still being live — so the most consequential press on this page ended
   * with the pressed element gone from the document, focus fallen to `<body>`, the next Tab
   * restarting at the top of the page, and nothing said about what had happened. The page
   * does not navigate away either: `reviewId` is null for a cancelled run.
   *
   * "Start again" is the affordance the stopped state already grows, carrying this run's
   * repository and its excluded folders, so it is a destination rather than a placeholder —
   * the same focus-return gesture `ui/drawer.tsx` performs when it closes. It fires only for
   * a stop somebody asked for here; a run that failed on its own must not steal focus from
   * whatever a reader was doing while they waited.
   */
  const againId = useId();
  useEffect(() => {
    if (cancel.isSuccess) document.getElementById(againId)?.focus();
  }, [cancel.isSuccess, againId]);

  // A review that exists is a better page than a review that is being made, so as soon as
  // one is composed this hands over. Replace, not push: the run is not a step in history a
  // reader wants the back button to return them to.
  useEffect(() => {
    if (reviewId && settled) navigate(`/reviews/${reviewId}`, { replace: true });
  }, [reviewId, settled, navigate]);

  // Captured once and restored once, so leaving this page gives the tab back whatever the
  // shell had put there — an effect that re-ran on every poll would restore its own title.
  useEffect(() => {
    const original = document.title;
    return () => {
      document.title = original;
    };
  }, []);
  const headline = state ? tabTitle(state) : null;
  useEffect(() => {
    if (headline) document.title = `${headline} · ArchCompass`;
  }, [headline]);

  if (run.isLoading) {
    return (
      <Panel>
        <PanelBody className="flex items-center gap-2 text-sm text-ink-2">
          <Spinner label="" /> Finding the review…
        </PanelBody>
      </Panel>
    );
  }

  /**
   * Only the absence of a run is "no such run".
   *
   * This gated on `run.error` too, and React Query keeps `data` and sets `error` when a
   * *background* refetch fails — so a sleeping laptop, a dropped connection or one 502 during
   * a poll that runs every 1500ms for minutes replaced a healthy run with a claim that it did
   * not exist, then put it back on the next poll. Nothing already on screen is taken away by
   * a failed refresh; the failure is said quietly below instead.
   */
  if (!state) {
    return (
      <ErrorNotice
        error={run.error || new Error("That review run could not be found")}
        title="No such run"
        action={
          <Button variant="secondary" size="sm" onClick={() => void run.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const failed = state.status === "failed";
  const stopped = state.status === "cancelled";
  const lineage = lineageOf(reviews.data ?? [], state.branch_id, state.case_id);
  /**
   * The number, once the lineage has answered — and nothing before it.
   *
   * `lineage.length + 1` is computed from `reviews.data ?? []`, so while the summaries query
   * is still out the lineage is empty and the fallback is 1. A run that is really revision 5
   * opened as "Review 1 · in progress" and then renumbered itself. `CaseNote` on the start
   * page was rewritten to remove exactly this: a sentence that names a case revision is a
   * claim, and a claim made before the answer arrives is a guess. Saying the status alone for
   * one render is cheaper than a placeholder that shifts.
   */
  const sequence = state.sequence ?? (reviews.isPending ? null : lineage.length + 1);
  const status = failed ? "did not finish" : stopped ? "stopped" : "in progress";
  // The whole of what the run was started with, handed back rather than thrown away.
  // `?root=` is the same hand-off the repositories page makes; the folders travel beside it
  // as one `exclude` each, so a path with a comma in it needs no escaping rule of its own.
  // Sending somebody back to a blank form to re-tick ten minutes of folder choices was this
  // page discarding what it is printing twenty lines above.
  const again = state.repository_root
    ? `/start?${new URLSearchParams([
        ["root", state.repository_root],
        ...(state.excluded_paths ?? []).map((path) => ["exclude", path]),
      ]).toString()}`
    : "/start";

  return (
    <div>
      <header className="mb-5">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
          {/* The same head as a recorded revision: what identifies this is the repository,
              the branch and the path it read. It carried "Architecture review of X" at 30px
              — the exact string at the exact size the review page deleted as the largest
              type on the page spent on the fact the reader is least in doubt about — so
              watching a run and then reading the review it became looked like two products. */}
          <div className="min-w-0">
            <Label>{sequence === null ? status : `Review ${sequence} · ${status}`}</Label>
            <h1
              title={state.repository_root}
              className="mt-1.5 flex min-w-0 flex-wrap items-baseline gap-x-2 font-mono text-[15px] leading-tight tracking-[-0.01em] text-ink-3 sm:text-[17px]"
            >
              <span className="font-medium text-ink [overflow-wrap:anywhere]">
                {state.repository_name || "this repository"}
              </span>
              {state.branch_name ? (
                <>
                  <span aria-hidden="true">/</span>
                  <span className="[overflow-wrap:anywhere]">{state.branch_name}</span>
                </>
              ) : null}
            </h1>
            {/* The whole path behind the ellipsis, wherever this row had to shorten it. An
                absolute path is the identity of the thing being reviewed and is regularly
                wider than the box; two sibling checkouts differing only in a middle segment
                truncate to the same string, and there was nothing to recover the difference
                from. */}
            {state.repository_root ? (
              <Mono
                title={state.repository_root}
                className="mt-1.5 block truncate text-[11px] text-ink-3"
              >
                {state.repository_root}
              </Mono>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <NotifyWhenDone done={settled} headline={headline} />
            <ButtonLink to="/reviews" variant="secondary">
              Review history
            </ButtonLink>
            {failed || stopped ? (
              <ButtonLink id={againId} to={again}>
                Start again
              </ButtonLink>
            ) : null}
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
              title={
                failed
                  ? "This review did not finish"
                  : stopped
                    ? "This review was stopped"
                    : "Reviewing the repository"
              }
              description={
                failed
                  ? "The run stopped at the stage below. Nothing was recorded as a verdict."
                  : stopped
                    ? "The run finished the stage it was in and went no further. Nothing was recorded as a verdict."
                    : "This is running in the workspace, not in this tab. You can close it and come back to this address, or find it on the reviews page. Its findings appear here as soon as they are composed."
              }
            />
            <PanelBody>
              {/* A failed poll is a fact about the connection, not about the run. It is said
                  here, in one line, and nothing on the page is removed for it. */}
              {run.isError ? (
                <p className="mb-4 flex items-center gap-2 text-xs text-ink-2">
                  <Spinner label="" /> Lost contact with the workspace. Still trying — what is
                  below is the last thing it said.
                </p>
              ) : null}
              <RunProgress
                state={state}
                onCancel={() => cancel.mutate()}
                cancelling={cancel.isPending}
              />
              {/* No retry slot: "Stop this run" is still on screen directly above this, and
                  a second button saying the same thing would be two controls for one act. */}
              {cancel.error ? (
                <div className="mt-4">
                  <ErrorNotice error={cancel.error} title="The run could not be stopped" />
                </div>
              ) : null}
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}
