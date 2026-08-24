import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { reviewSummaryFixture, runFixture } from "../../test-fixtures";
import { RunPage } from "./run-page";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/runs/thread-9"]}>
        <Routes>
          <Route path="/runs/:runId" element={children} />
          <Route path="/reviews/:reviewId" element={<div>Review workbench</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("a review being made", () => {

  it("reads as the next revision of its lineage, not as a job with a thread id", async () => {
    // Everything a review is filed under exists before the review does: the repository, the
    // branch, the case, and the sequence taken from the newest review on that branch. So the
    // page is the review page's head and rail, with progress where the findings will go.
    const previous = reviewSummaryFixture({ status: "completed", sequence: 1 });
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([previous]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        branch_id: previous.repository.branch_id,
        case_id: previous.case_id,
        sequence: 2,
      }),
    );

    render(wrap(<RunPage />));

    expect(await screen.findByText(/Review 2 · in progress/)).toBeInTheDocument();
    // The same head a recorded revision wears: the repository and the branch in mono, then
    // the path. It used to be "Architecture review of payments-platform" at 30px — the exact
    // string at the exact size the review page deleted as the largest type on the page spent
    // on the fact the reader is least in doubt about.
    const head = screen.getByRole("heading", { name: /payments-platform/ });
    expect(head).toHaveClass("font-mono");
    expect(within(head).getByText("main")).toBeInTheDocument();
    expect(screen.queryByText(/Architecture review of/)).not.toBeInTheDocument();
    expect(screen.getByText("/work/payments-platform")).toBeInTheDocument();

    // The rail carries the revision before it and this one, in sequence.
    const rail = (await screen.findByText("Review lineage")).parentElement!;
    expect(within(rail).getByRole("link", { name: /Review 1/ })).toHaveAttribute(
      "href",
      `/reviews/${previous.id}`,
    );
    const current = within(rail).getByRole("link", { name: /Review 2/ });
    expect(current).toHaveAttribute("aria-current", "page");

    // The stage, said the way a person would say it rather than as a node name — on the
    // rail entry and again in the progress list, which is the pane the findings will fill.
    const progress = screen.getByRole("list", { name: "Review progress" });
    expect(within(progress).getByText("Judging candidates")).toBeInTheDocument();
    expect(within(rail).getByText("Judging candidates")).toBeInTheDocument();
  });

  it("says the candidate loop once, with how deep into it the run is", async () => {
    // A loop is one step that is fifteen deep, not fifteen steps. Listing every turn made
    // the progress list thirty rows of the same two labels alternating, which reads as a
    // run that is stuck — and buried the steps that genuinely differ from each other.
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        stage: "judge_candidate",
        stages: [
          "load_context",
          "select_initial_candidates",
          "retrieve_policy_set",
          "judge_candidate",
          "review_candidate",
          "judge_candidate",
          "review_candidate",
          "judge_candidate",
        ],
        candidates_to_judge: 15,
        candidates_judged: 5,
      }),
    );

    render(wrap(<RunPage />));

    const progress = await screen.findByRole("list", { name: "Review progress" });
    expect(within(progress).getByText("Judging candidate 6 of 15")).toBeInTheDocument();
    // Two rows before it and none after: every turn through the loop is that one row.
    expect(within(progress).getAllByRole("listitem")).toHaveLength(3);
  });

  it("counts the candidate loop as done once the run has left it", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        status: "completed",
        review_id: null,
        stage: "record_review",
        stages: ["judge_candidate", "record_review"],
        candidates_to_judge: 15,
        candidates_judged: 15,
      }),
    );

    render(wrap(<RunPage />));

    const progress = await screen.findByRole("list", { name: "Review progress" });
    expect(within(progress).getByText("Judged 15 candidates")).toBeInTheDocument();
  });

  it("hands over to the review the moment there is one to read", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({ status: "completed", review_id: "review-7", stage: "record_review" }),
    );

    render(wrap(<RunPage />));

    // Replace rather than push: the run is not a step the back button should return to.
    await waitFor(() => expect(screen.getByText("Review workbench")).toBeInTheDocument());
  });

  it("says a failed run failed, and offers the way back", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        status: "failed",
        failure: "The provider refused the request",
        review_id: null,
      }),
    );

    render(wrap(<RunPage />));

    expect(await screen.findByText(/Review 2 · did not finish/)).toBeInTheDocument();
    expect(screen.getByText(/The provider refused the request/)).toBeInTheDocument();
    // The repository the run failed on, carried into the form rather than thrown away. It
    // went to a blank `/start`, where the reader found the repository again and re-ticked
    // every folder they had left out — while the path was printed twenty lines above.
    expect(screen.getByRole("link", { name: "Start again" })).toHaveAttribute(
      "href",
      "/start?root=%2Fwork%2Fpayments-platform",
    );
  });

  /**
   * The other half of the same hand-off, which the wire could not carry until now.
   *
   * A rerun with a different scope is a review of a different question, so "Start again"
   * offering the repository without the folders was offering to start something else. The
   * run says what it left out; the link says it too, one parameter per folder so a path with
   * a comma in it needs no escaping rule.
   */
  it("carries the folders the run left out into the form that starts the next one", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        status: "failed",
        failure: "The provider refused the request",
        review_id: null,
        excluded_paths: ["docs", "tests"],
      }),
    );

    render(wrap(<RunPage />));

    expect(await screen.findByRole("link", { name: "Start again" })).toHaveAttribute(
      "href",
      "/start?root=%2Fwork%2Fpayments-platform&exclude=docs&exclude=tests",
    );
  });

  /**
   * A failed poll is a fact about the connection, not about the run.
   *
   * The page gated on `run.error || !state`, and React Query keeps `data` and sets `error`
   * when a *background* refetch fails — so a sleeping laptop or one 502 during a poll that
   * runs every 1500ms for minutes replaced a healthy run with "No such run", then put it
   * back on the next poll.
   */
  it("keeps the run on screen when a poll fails, and says contact was lost", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    const poll = vi
      .spyOn(api, "reviewRun")
      .mockResolvedValueOnce(runFixture({}))
      .mockRejectedValue(new Error("Failed to fetch"));

    render(wrap(<RunPage />));

    await screen.findByRole("list", { name: "Review progress" });
    // The poll runs at 1500ms, which is longer than the default wait.
    await waitFor(() => expect(poll.mock.calls.length).toBeGreaterThan(1), { timeout: 3000 });

    expect(await screen.findByText(/Lost contact with the workspace/)).toBeInTheDocument();
    // And nothing that was on screen has been taken away by the refresh that failed.
    expect(screen.queryByText("No such run")).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Review progress" })).toBeInTheDocument();
    expect(screen.getByText("thread-9")).toBeInTheDocument();
  });

  it("offers a way to stop a run somebody no longer wants", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(runFixture({}));
    const cancelled = vi
      .spyOn(api, "cancelRun")
      .mockResolvedValue(runFixture({ status: "cancelled", stage: "judge_candidate" }));

    render(wrap(<RunPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Stop this run" }));

    await waitFor(() => expect(cancelled).toHaveBeenCalledWith("thread-9"));
    // The run keeps its id under `cancelled`, so this address goes on answering rather than
    // navigating anywhere — and the page says which of the three ends it came to.
    expect(await screen.findByText(/Review 2 · stopped/)).toBeInTheDocument();
    expect(screen.getByText("This review was stopped")).toBeInTheDocument();
  });
});
