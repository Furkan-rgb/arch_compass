import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type Review } from "../../api";
import { reviewFixture, runFixture } from "../../test-fixtures";
import { ToastProvider } from "../../ui/toast";
import { ReviewsPage } from "./reviews-page";

function client() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrap(children: ReactNode, queries: QueryClient) {
  return (
    <ToastProvider>
      <QueryClientProvider client={queries}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>
  );
}

/** A second revision of the same lineage, so there is a trajectory to draw. */
function successor(overrides: Partial<Review> = {}): Review {
  const base = reviewFixture();
  return reviewFixture({
    id: "review-2",
    sequence: 2,
    status: "completed",
    questions: [],
    previous_review_id: base.id,
    started_at: "2026-01-02T00:00:00Z",
    finished_at: "2026-01-02T00:10:00Z",
    delta: {
      unchanged: [],
      changed: [],
      new: ["candidate-1", "candidate-2"],
      addressed: [
        {
          candidate_id: "gone-1",
          title: "The invoice boundary is appropriate",
          last_seen_review_id: "review-1",
          last_verdict: "held",
        },
      ],
    },
    ...overrides,
  });
}

afterEach(() => vi.restoreAllMocks());

describe("a run that finishes while nobody is looking", () => {
  /**
   * The poll above the run list said its whole purpose was that "a run that finished while
   * they were away has to become a review without a reload". It did not: `["reviews"]` was
   * never invalidated when the run list changed, and `refetchOnWindowFocus` is off, so a page
   * left open never refetched anything at all.
   */
  it("becomes a review, because the run leaving the list invalidates the reviews", async () => {
    const reviews = vi.spyOn(api, "reviews").mockResolvedValue([]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([runFixture()]);
    const queries = client();

    render(wrap(<ReviewsPage />, queries));
    await screen.findByText("payments-platform");
    expect(reviews).toHaveBeenCalledTimes(1);

    // The run finishes: the workspace stops listing it, and what it produced is a review.
    reviews.mockResolvedValue([reviewFixture()]);
    act(() => {
      queries.setQueryData(["review-runs"], []);
    });

    await waitFor(() => expect(reviews).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Review 1")).toBeInTheDocument();
  });

  /**
   * A listed run may name a review it is already attached to — answering a clarification
   * round rejudges the snapshot that asked the questions, and the run reports until it is
   * genuinely done. Drawn as they arrive that is two rows for one revision.
   */
  it("is one row, not two, while it is rejudging a review that already exists", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({ review_id: "review-1", sequence: 1 }),
    ]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    const lineage = (await screen.findByText("payments-platform")).closest("article")!;
    expect(within(lineage).getAllByText(/^Review 1$/)).toHaveLength(1);
    expect(within(lineage).queryByText("In progress")).not.toBeInTheDocument();
    expect(within(lineage).getByText(/Rejudging/)).toBeInTheDocument();
    // Nothing is deleted while it is being remade; the run is what the row offers instead.
    expect(within(lineage).getByRole("link", { name: "Watch" })).toHaveAttribute(
      "href",
      "/runs/thread-9",
    );
    expect(within(lineage).queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });
});

describe("what still wants a person", () => {
  /**
   * The page used to answer this in a section of its own — every open candidate across every
   * lineage, listed above the history. The claims read out of context, the rows repeated the
   * reviews below them, and the history it belonged to started below the fold. The fact stays
   * and the list goes: a review's row says how much of it wants a person, in the words the
   * review's own head uses, and the claims are read where they can be acted on.
   */
  it("says on the newest revision how much of it still wants a person", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    // Two candidates nobody has decided about, plus the open round's one question — which is
    // exactly what the review's own head counts, so the two totals cannot disagree.
    expect(await screen.findByText("3 things want you")).toBeInTheDocument();
    expect(screen.queryByText("Waiting on you")).not.toBeInTheDocument();
  });

  /**
   * `needsAttention(finding, undefined)` is true for anything not cleared, so a count taken
   * before the branch's decisions land names everything the team settled weeks ago and then
   * shrinks. `docket-rules.ts` names this hazard; this page was the second caller.
   */
  it("says nothing until the branch's standing decisions have arrived", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockReturnValue(new Promise(() => {}));

    render(wrap(<ReviewsPage />, client()));

    expect(await screen.findByText("Review 1")).toBeInTheDocument();
    expect(screen.queryByText(/wants? you/)).not.toBeInTheDocument();
  });

  /**
   * A branch whose decisions could not be read can only make the count too high, and a number
   * on a row has nowhere to say so.
   */
  it("says nothing when the branch's decisions could not be read", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockRejectedValue(new Error("no such branch"));

    render(wrap(<ReviewsPage />, client()));

    expect(await screen.findByText("Review 1")).toBeInTheDocument();
    await waitFor(() => expect(api.decisions).toHaveBeenCalled());
    expect(screen.queryByText(/wants? you/)).not.toBeInTheDocument();
  });

  /**
   * An outstanding candidate in review 1 was either carried into review 2, where it is
   * counted, or it went away. A superseded snapshot claiming it too says the same open item
   * twice down one lineage.
   */
  it("counts the newest revision and no other", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture(), successor()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    // Review 2 is completed, so its two undecided candidates are the whole of what it wants.
    expect(await screen.findByText("2 things want you")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Show 1 older revision/ }));

    const older = screen.getByText("Review 1").closest("li")!;
    expect(within(older).queryByText(/wants? you/)).not.toBeInTheDocument();
  });

  /**
   * The status filter belongs to the list of lineages. It used to change what the page said
   * was waiting on you, because the grouping ran on the filtered list: pressing **Completed**
   * removed every review awaiting answers, and with them every open clarification question.
   * A filter now hides rows and never restates one.
   */
  it("does not promote a superseded revision when the filter hides the newest", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture(), successor({ status: "failed" })]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));
    expect(await screen.findByText("2 things want you")).toBeInTheDocument();

    // Named with its count: every status chip now says how many revisions it would return,
    // so a chip that would return none cannot be pressed.
    fireEvent.click(screen.getByRole("button", { name: "Awaiting answers 1" }));

    // Review 1 is on screen now and it is still a superseded snapshot: what it raised was
    // carried into review 2, which is filtered out, not transferred to the row left standing.
    expect(screen.getByText("Review 1")).toBeInTheDocument();
    expect(screen.queryByText(/wants? you/)).not.toBeInTheDocument();
  });
});

describe("the lineage list", () => {
  /**
   * The rail is the page's whole argument — "Nothing on the page showed that review 4
   * succeeded review 3" is the fault the redesign fixed — and it carried `aria-hidden`.
   */
  it("says the trajectory in words for anybody not looking at it", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture(), successor()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    expect(
      await screen.findByText("Review 1, then review 2 with 2 raised and 1 addressed."),
    ).toBeInTheDocument();
  });

  /** `/api/reviews` answers with the newest 100, and the header used to report that as a total. */
  it("says the list is a page when the list is full", async () => {
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });
    vi.spyOn(api, "reviews").mockResolvedValue(
      Array.from({ length: 100 }, (_, index) =>
        reviewFixture({ id: `review-${index + 1}`, sequence: index + 1, questions: [] }),
      ),
    );

    render(wrap(<ReviewsPage />, client()));

    expect(await screen.findByText(/showing the newest 100/)).toBeInTheDocument();
    expect(screen.queryByText(/100 revisions kept/)).not.toBeInTheDocument();
  });

  it("keeps the page when the history fails, and offers the way back", async () => {
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    const reviews = vi
      .spyOn(api, "reviews")
      .mockRejectedValueOnce(new Error("workspace unreachable"))
      .mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    expect(await screen.findByText(/workspace unreachable/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reviews" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("payments-platform")).toBeInTheDocument();
    expect(reviews).toHaveBeenCalledTimes(2);
  });
});
