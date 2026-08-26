import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type Review } from "../../api";
import { repositoryFixture, reviewFixture, runFixture } from "../../test-fixtures";
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

describe("the review being made right now", () => {
  /**
   * The report this fixes: "when you start a review, it should be visible in the reviews page
   * as well, under the appropriate repo."
   *
   * A lineage was keyed on the path, the branch and the case, and a run derives two of those
   * three from somewhere else — it reports the directory the repository was first seen at,
   * and it carries whatever case the start form gave it, which is a fresh one whenever the
   * branch has no surviving review. So the lookup missed, the run was drawn as a line of work
   * of its own with an empty history, and `latestAt` sorted that block above the real one.
   * The branch is the whole key now, which is what the workspace itself sequences on.
   */
  it("is listed under its repository even when the run names another path and a new case", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        repository_root: "/work/.archcompass/checkouts/payments-platform-1bf2f5",
        case_id: "case-2",
      }),
    ]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    // One line of work, not two, and the heading is the repository the history knows rather
    // than the checkout the run reports.
    const lineages = await screen.findAllByRole("article");
    expect(lineages).toHaveLength(1);
    expect(within(lineages[0]).getByText("payments-platform")).toBeInTheDocument();

    // The run is the next revision of it, and it says what it is and where to watch it.
    const progress = within(lineages[0]).getByText("In progress").closest("a")!;
    expect(progress).toHaveAttribute("href", "/runs/thread-9");
    expect(within(progress).getByText("Review 2")).toBeInTheDocument();
    expect(within(progress).getByText(/Judging candidates/)).toBeInTheDocument();
    // Two cases on one number line, so every row says which case it belongs to.
    expect(within(progress).getByText(/case case-2/)).toBeInTheDocument();
  });

  /**
   * `/api/reviews` answers with whole reviews and can be megabytes. Gating the run on it made
   * the one thing on this page that cannot wait the thing that waited — and where the history
   * failed outright, the run was not listed at all, under a message about something else.
   */
  it("is listed before the history has arrived", async () => {
    vi.spyOn(api, "reviews").mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, "reviewRuns").mockResolvedValue([runFixture()]);

    render(wrap(<ReviewsPage />, client()));

    expect(await screen.findByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Opening review history…")).toBeInTheDocument();
  });

  /** The search used to filter the reviews and not the runs, so it could not remove a panel. */
  it("is removed by a search that does not match its repository", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([runFixture({ review_id: null })]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));
    expect(await screen.findByText("In progress")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search reviews"), {
      target: { value: "ledger" },
    });
    expect(screen.queryByText("In progress")).not.toBeInTheDocument();
  });
});

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

describe("where the review being made is listed", () => {
  /**
   * The report: "when you start a review, it should be visible in the reviews page as well,
   * under the appropriate repo."
   *
   * A run and a review used to be filed under keys built from different fields. A run reports
   * the directory the workspace first saw the repository at and whatever case the start form
   * minted for it — a fresh one whenever the branch has no surviving review — while a review
   * reports the directory its newest atlas was built from and the case it was judged against.
   * Neither field has to agree, so the lookup missed and the run was drawn as a line of work
   * of its own, headed by the checkout directory, with no history under it.
   *
   * This asserts the requirement rather than the key: the page holds one panel per repository
   * reviewed, and the run is the first row of the one it belongs to — above the revisions it
   * succeeds. Rows are found by the address they open, which is the product's own name for
   * them and survives any rewording of what the row says.
   */
  it("is the first row of its repository's panel, not a panel of its own", async () => {
    const history = reviewFixture();
    const elsewhere = reviewFixture({
      id: "review-7",
      repository: repositoryFixture({
        id: "repo-2",
        path: "/work/ledger-service",
        branch_id: "branch-2",
        branch: "topic/pricing",
      }),
      started_at: "2025-12-01T00:00:00Z",
    });
    const inFlight = runFixture({
      repository_root: "/work/.archcompass/checkouts/payments-platform-1bf2f5",
      case_id: "case-2",
      sequence: 2,
    });
    vi.spyOn(api, "reviews").mockResolvedValue([history, elsewhere]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([inFlight]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    render(wrap(<ReviewsPage />, client()));

    // Two repositories have been reviewed, so the page holds two lines of work. A review
    // being made is not a third one.
    const panels = await screen.findAllByRole("article");
    expect(panels).toHaveLength(2);

    const address = (href: string) =>
      screen.getAllByRole("link").find((link) => link.getAttribute("href") === href);
    const watching = address(`/runs/${inFlight.run_id}`);
    expect(watching).toBeDefined();

    // The panel it sits in is the one holding that branch's recorded history, and it is
    // headed by the repository the history names rather than by the checkout the run reports.
    const panel = watching!.closest("article")!;
    expect(panels).toContain(panel);
    expect(within(panel).getByRole("heading", { level: 2 })).toHaveTextContent(
      "payments-platform",
    );
    expect(screen.queryAllByText(/payments-platform-1bf2f5/)).toHaveLength(0);

    // First row, above the revision it succeeds — the next revision of this line of work.
    const rows = within(panel).getAllByRole("listitem");
    expect(rows[0]).toContainElement(watching!);
    expect(rows[1]).toContainElement(address(`/reviews/${history.id}`)!);

    // And the other repository is untouched by it.
    const other = panels.find((item) => item !== panel)!;
    expect(within(other).queryAllByRole("listitem")).toHaveLength(1);
    expect(within(other).getAllByRole("listitem")[0]).toContainElement(
      address(`/reviews/${elsewhere.id}`)!,
    );
  });
});
