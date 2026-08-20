import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { reviewFixture, runFixture } from "../../test-fixtures";
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
    const previous = reviewFixture({ status: "completed", questions: [], sequence: 1 });
    vi.spyOn(api, "reviews").mockResolvedValue([previous]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        branch_id: previous.repository.branch_id,
        case_id: previous.case.id,
        sequence: 2,
      }),
    );

    render(wrap(<RunPage />));

    expect(await screen.findByText(/Review 2 · in progress/)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Architecture review of payments-platform/ }),
    ).toBeInTheDocument();

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

  it("hands over to the review the moment there is one to read", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({ status: "completed", review_id: "review-7", stage: "record_review" }),
    );

    render(wrap(<RunPage />));

    // Replace rather than push: the run is not a step the back button should return to.
    await waitFor(() => expect(screen.getByText("Review workbench")).toBeInTheDocument());
  });

  it("says a failed run failed, and offers the way back", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([]);
    vi.spyOn(api, "reviewRun").mockResolvedValue(
      runFixture({
        status: "failed",
        failure: "The provider refused the batch",
        review_id: null,
      }),
    );

    render(wrap(<RunPage />));

    expect(await screen.findByText(/Review 2 · did not finish/)).toBeInTheDocument();
    expect(screen.getByText(/The provider refused the batch/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start again" })).toHaveAttribute("href", "/start");
  });
});
