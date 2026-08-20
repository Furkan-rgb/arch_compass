import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { VIEWPORT, setViewportWidth } from "../../test-setup";
import { reviewFixture, runFixture } from "../../test-fixtures";
import { ReviewPage } from "./review-page";

function wrap(children: ReactNode, path = "/reviews/review-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/reviews/:reviewId" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  setViewportWidth(VIEWPORT.desktop);
  vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
});

afterEach(() => {
  vi.restoreAllMocks();
  setViewportWidth(VIEWPORT.desktop);
});

describe("the review workbench", () => {
  it("opens on the clarification when the review is waiting for a human", async () => {
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByText("The repository cannot answer these")).toBeInTheDocument();
    expect(screen.getByText("Who owns persistence?")).toBeInTheDocument();
    // And exactly one way to answer it. The chrome used to carry an "Answer 1" button while
    // the queue listed the clarification and the finding offered it again under "Hinges on" —
    // one action with four affordances, which reads as nagging rather than as confident. The
    // queue keeps its row, because the queue is the list of things needing a person; a button
    // in the header is not.
    expect(screen.queryByRole("button", { name: /^Answer \d/ })).not.toBeInTheDocument();
    expect(screen.getByText(/waiting on 1 unanswered question/)).toBeInTheDocument();
  });

  it("orders the queue by what needs a human, cleared findings last", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    // The default filter is "attention", so the cleared candidate is deliberately not listed.
    const queue = await screen.findByRole("list", { name: "Candidates" });
    const listed = within(queue)
      .getAllByRole("button")
      .map((item) => item.textContent ?? "");
    expect(listed[0]).toContain("The provider abstraction carries one implementation");
    expect(listed[1]).toContain("Domain depends on an adapter");
    expect(listed.join(" ")).not.toContain("The invoice boundary is appropriate");

    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    const all = within(await screen.findByRole("list", { name: "Candidates" }))
      .getAllByRole("button")
      .map((item) => item.textContent ?? "");
    expect(all.at(-1)).toContain("The invoice boundary is appropriate");
  });

  it("names whose voice produced each part of the assessment", async () => {
    // The charter keeps three jobs apart — the machine assembles, the model judges, the
    // person decides — and they were apart in the domain and identical on screen.
    //
    // What makes them apart is no longer a typeface or a gutter. It is placement and an
    // attribution line: the model's sentence is the only reading-size text in the article and
    // it is introduced by who produced it, the machine's numbers are behind a disclosure that
    // names itself, and the decision is the bar that says whose it is. That is worth failing a
    // build over in exactly the way the gutter was.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    // The identifier leads, because that is what a reviewer is looking for.
    const heading = await screen.findByRole("heading", { name: "domain.orders" });
    const article = heading.closest("article")!;
    expect(within(article).getByText("Measured")).toBeInTheDocument();
    expect(within(article).getByText("Judged")).toBeInTheDocument();
    expect(within(article).getByText("Standing decision")).toBeInTheDocument();
    // And each voice says who, not only what. The decision states its own emptiness rather
    // than a second heading printing the attribution the bar underneath already carries.
    expect(within(article).getByText(/Nobody has decided this/)).toBeInTheDocument();
    expect(
      within(article).getByText("The provider abstraction carries one implementation"),
    ).toBeInTheDocument();
    expect(within(article).getByText(/Recommended response/)).toBeInTheDocument();
    expect(within(article).getByText(/Dependencies point inward/)).toBeInTheDocument();
    // The excerpt is coloured, so its text is spread across token spans — it still has to
    // read back as the file's own line.
    const excerpt = article.querySelector("code.language-python");
    expect(excerpt?.textContent).toContain("from adapters.db import Store");
    expect(excerpt?.querySelector(".hljs-keyword")).not.toBeNull();

    // Model, prompt and retrieval identity are real, but they are not the argument. The
    // prompt identity is in the DOM inside a closed <details> rather than absent — which is
    // the point of a disclosure, and is also why this asks whether it is *visible* rather
    // than whether it exists.
    expect(within(article).getByText("judge:v1")).not.toBeVisible();
    fireEvent.click(within(article).getByText("Provenance"));
    expect(within(article).getByText("judge:v1")).toBeVisible();
  });

  it("keeps the standing decision separate from the model's verdict", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const decide = vi.spyOn(api, "decide").mockResolvedValue({
      id: "decision-1",
      branch_id: "branch-1",
      candidate_id: "candidate-2",
      disposition: "accept",
      author: "user",
      reasoning: null,
      decided_at: "2026-01-01T00:00:00Z",
      review_id: "review-1",
      finding_verdict: "material",
      finding_model_identity: "fake:deterministic",
      finding_prompt_identity: "judge:v1",
      finding_retrieval_identity: "retrieval-1",
    });

    render(wrap(<ReviewPage />));

    expect(await screen.findByText(/Nobody has decided this/)).toBeInTheDocument();

    // Waiving without a reason is still refused by the form rather than by the server — but
    // the refusal moved to where the reason is. Waive is a disclosure now: the field it needs
    // does not exist until it is pressed, because it was the widest control in the bar and
    // empty in the two states that do not want it.
    const waive = screen.getByRole("button", { name: "Waive" });
    expect(waive).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(waive);
    expect(waive).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /Record waiver/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));
    await waitFor(() =>
      expect(decide).toHaveBeenCalledWith("review-1", "candidate-2", "accept", null),
    );
  });

  it("records an explicit skip and resumes by review identity", async () => {
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(api, "answer")
      .mockResolvedValue(reviewFixture({ id: "review-2", status: "completed", questions: [] }));

    render(wrap(<ReviewPage />));

    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Skip explicitly" }));
    expect(screen.getByText("1/1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save and rejudge" }));
    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [{ question_id: "question-1", status: "skipped", value: null }],
        false,
      ),
    );
  });

  it("carries an answer through as answered rather than skipped", async () => {
    // A question with nothing proposed is answered by writing, which is the shape every
    // question had before the model started offering answers.
    const review = reviewFixture({
      questions: [{ ...reviewFixture().questions[0], options: [] }],
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(api, "answer")
      .mockResolvedValue(reviewFixture({ id: "review-2", status: "completed", questions: [] }));

    render(wrap(<ReviewPage />));

    fireEvent.change(await screen.findByLabelText("Who owns persistence?"), {
      target: { value: "  The platform team owns it.  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Conclude with remaining uncertainty" }));

    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [
          {
            question_id: "question-1",
            status: "answered",
            value: "The platform team owns it.",
          },
        ],
        true,
      ),
    );
  });

  it("answers with a proposed option, verbatim", async () => {
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(api, "answer")
      .mockResolvedValue(reviewFixture({ id: "review-2", status: "completed", questions: [] }));

    render(wrap(<ReviewPage />));

    // The model proposed these, so the reviewer's whole job here is one click.
    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Conclude with remaining uncertainty" }));

    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [
          {
            question_id: "question-1",
            status: "answered",
            value: "The domain owns it and adapters implement its ports",
          },
        ],
        true,
      ),
    );
  });

  it("keeps a menu escapable — an answer nobody proposed is still writable", async () => {
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(api, "answer")
      .mockResolvedValue(reviewFixture({ id: "review-2", status: "completed", questions: [] }));

    render(wrap(<ReviewPage />));

    // There is no box while the offered answers stand — the menu is the shorter path, and
    // two ways to answer the same question at once is a worse question.
    expect(screen.queryByLabelText("Who owns persistence?")).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole("radio", { name: /Something else/ }));
    fireEvent.change(screen.getByLabelText("Who owns persistence?"), {
      target: { value: "Neither — it is a shared kernel." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Conclude with remaining uncertainty" }));

    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [
          {
            question_id: "question-1",
            status: "answered",
            value: "Neither — it is a shared kernel.",
          },
        ],
        true,
      ),
    );
  });

  it("does not hand the reviewer the model's sentence to edit", async () => {
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );
    fireEvent.click(screen.getByRole("radio", { name: /Something else/ }));

    expect(screen.getByLabelText("Who owns persistence?")).toHaveValue("");
  });

  it("scans the delta by name and opens what it names", async () => {
    const review = reviewFixture({
      status: "completed",
      questions: [],
      previous_review_id: "review-0",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Delta/ }));
    const panel = screen.getByRole("tabpanel");

    // The row is led by the candidate's name, not by its sentence, because the delta is
    // scanned for which things moved rather than read.
    const rows = within(panel).getAllByTitle("domain.orders");
    expect(rows).toHaveLength(3);
    // Split for the eye — the namespace is dimmed context, the leaf is the identity — and
    // kept whole for anything that has to read it back.
    expect(within(rows[0]).getByText("orders")).toBeInTheDocument();

    // And seeing it is the same action as opening it.
    fireEvent.click(rows[0]);
    expect(screen.getByRole("tab", { name: /Workbench/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("filters the delta by change rather than stacking a panel per state", async () => {
    const review = reviewFixture({
      status: "completed",
      questions: [],
      previous_review_id: "review-0",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Delta/ }));
    const panel = screen.getByRole("tabpanel");
    const list = within(panel).getByRole("list", { name: "Candidates by change" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);

    fireEvent.click(within(panel).getByRole("button", { name: /Unchanged 1/ }));
    expect(
      within(within(panel).getByRole("list", { name: "Candidates by change" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(1);
  });

  it("shows the team's decision on the row, and stops counting it as needing you", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "decisions").mockResolvedValue({
      branch_id: "branch-1",
      decisions: [
        {
          id: "decision-1",
          branch_id: "branch-1",
          candidate_id: "candidate-2",
          disposition: "waive",
          author: "reviewer",
          reasoning: "The trade-off is deliberate.",
          decided_at: "2026-01-02T00:00:00Z",
          review_id: "review-1",
          finding_verdict: "material",
          finding_model_identity: "fake:deterministic",
          finding_prompt_identity: "judge:v1",
          finding_retrieval_identity: "retrieval-1",
        },
      ],
    });

    render(wrap(<ReviewPage />));

    // A waived material finding is settled. The queue stops asking about it...
    const queue = await screen.findByRole("list", { name: "Candidates" });
    expect(within(queue).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Attention 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Settled 2/ })).toBeInTheDocument();

    // ...and says so where it was, rather than only inside the finding.
    fireEvent.click(screen.getByRole("button", { name: /^Settled 2/ }));
    const settled = await screen.findByRole("list", { name: "Candidates" });
    expect(within(settled).getByText("Waived by the team")).toBeInTheDocument();
  });

  it("widens the queue's filter when another surface hands it a candidate", async () => {
    const review = reviewFixture({
      status: "completed",
      questions: [],
      previous_review_id: "review-0",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    // candidate-3 is cleared, so the default Attention filter does not list it.
    fireEvent.click(await screen.findByRole("tab", { name: /Delta/ }));
    const panel = screen.getByRole("tabpanel");
    fireEvent.click(within(panel).getAllByTitle("domain.orders")[2]);

    expect(screen.getByRole("button", { name: /^Settled/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const queue = await screen.findByRole("list", { name: "Candidates" });
    expect(within(queue).getByText("The invoice boundary is appropriate")).toBeInTheDocument();
  });

  it("keeps the audit behind the judgement it audits", async () => {
    // Retrieval provenance was a surface of its own, sitting beside the queue as though a
    // reviewer working down a list might switch to reading corpus fingerprints. It answers
    // "why this candidate", so it belongs where that candidate is.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const queue = await screen.findByRole("list", { name: "Candidates" });
    fireEvent.click(within(queue).getAllByRole("button")[1]);
    fireEvent.click(await screen.findByRole("button", { name: "Judgement context" }));

    const drawer = await screen.findByRole("dialog", { name: "Judgement context" });
    fireEvent.click(within(drawer).getByRole("tab", { name: /Provenance/ }));
    expect(within(drawer).getByText(/dense-scoped/)).toBeInTheDocument();
    expect(within(drawer).getByText("corpus-fingerprint")).toBeInTheDocument();
    expect(within(drawer).getByText("ollama:nomic-embed-text")).toBeInTheDocument();
  });

  it("keeps the queue on screen while another surface is read", async () => {
    // The charter's first interface rule is that the queue is the product. It used to be
    // one of seven peer tabs, six of which unmounted it.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Delta/ }));
    expect(screen.getByRole("list", { name: "Candidates" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Ask/ }));
    expect(screen.getByRole("list", { name: "Candidates" })).toBeInTheDocument();
  });

  it("walks the queue with the keyboard and opens what it lands on", async () => {
    // The most repeated action in the product, and it was pointer-only.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const queue = await screen.findByRole("list", { name: "Candidates" });
    const first = within(queue).getAllByRole("button")[0];
    expect(first).toHaveAttribute("aria-current", "true");

    fireEvent.keyDown(first, { key: "j" });
    const moved = within(screen.getByRole("list", { name: "Candidates" })).getAllByRole("button");
    expect(moved[1]).toHaveAttribute("aria-current", "true");
    // And the column beside it is showing what the queue landed on.
    await waitFor(() =>
      expect(document.querySelector("#finding-candidate-1")).not.toBeNull(),
    );

    fireEvent.keyDown(moved[1], { key: "ArrowUp" });
    const back = within(screen.getByRole("list", { name: "Candidates" })).getAllByRole("button");
    expect(back[0]).toHaveAttribute("aria-current", "true");
  });

  it("puts what moved since the last review at the top of the queue", async () => {
    // The second visit is the important one: the sort used to be verdict rank and then the
    // summary alphabetically, which knew nothing about the delta at all.
    const review = reviewFixture({
      status: "completed",
      questions: [],
      sequence: 2,
      previous_review_id: "review-0",
      delta: {
        unchanged: ["candidate-1", "candidate-2"],
        changed: [],
        new: ["candidate-3"],
        addressed: [],
      },
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("button", { name: /^All/ }));
    const queue = await screen.findByRole("list", { name: "Candidates" });
    expect(within(queue).getByText("Moved since review 1 · 1")).toBeInTheDocument();
    expect(within(queue).getByText("Carried forward · 2")).toBeInTheDocument();
    // The one that moved leads, even though it came back cleared and two material and held
    // candidates were carried forward — the headings are what make that honest.
    const rows = within(queue).getAllByRole("button");
    expect(rows[0].textContent).toContain("The invoice boundary is appropriate");
  });

  it("marks a review that is worked through, rather than showing an empty list", async () => {
    // Reaching the bottom of the queue is the one moment in the product worth marking, and
    // it used to be an empty state reading "Nothing here".
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "decisions").mockResolvedValue({
      branch_id: "branch-1",
      decisions: ["candidate-1", "candidate-2"].map((candidate_id, index) => ({
        id: `decision-${index}`,
        branch_id: "branch-1",
        candidate_id,
        disposition: "accept",
        author: "user",
        reasoning: null,
        decided_at: "2026-01-01T00:00:00Z",
        review_id: "review-1",
        // Decided against exactly what this review says, so nothing is re-raised.
        finding_verdict: candidate_id === "candidate-1" ? "held" : "material",
        finding_model_identity: "fake:deterministic",
        finding_prompt_identity: "judge:v1",
        finding_retrieval_identity: "retrieval-1",
      })),
    });

    render(wrap(<ReviewPage />));

    expect(await screen.findByText("Worked through")).toBeInTheDocument();
    expect(screen.getByText(/Nothing in this review is waiting on a person/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Read the report/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Run the next review/ })).toBeInTheDocument();

    // And it is a way into the record, not a dead end.
    fireEvent.click(screen.getByRole("button", { name: /Read the report/ }));
    expect(screen.getByRole("tab", { name: /Report/ })).toHaveAttribute("aria-selected", "true");
  });

  it("re-raises a decision taken against a verdict that has since moved", async () => {
    // `StandingDecision` records the verdict it was decided against. Nothing read it, so a
    // team that accepted a material finding and saw it re-judged held was never told.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "decisions").mockResolvedValue({
      branch_id: "branch-1",
      decisions: [
        {
          id: "decision-1",
          branch_id: "branch-1",
          candidate_id: "candidate-1",
          disposition: "accept",
          author: "user",
          reasoning: null,
          decided_at: "2026-01-01T00:00:00Z",
          review_id: "review-0",
          finding_verdict: "material",
          finding_model_identity: "fake:deterministic",
          finding_prompt_identity: "judge:v1",
          finding_retrieval_identity: "retrieval-1",
        },
      ],
    });

    render(wrap(<ReviewPage />));

    // Still in the attention filter, which counts what wants a person, and saying why.
    const queue = await screen.findByRole("list", { name: "Candidates" });
    const stale = within(queue)
      .getAllByRole("button")
      .find((row) => row.textContent?.includes("Domain depends on an adapter"))!;
    expect(stale.textContent).toContain("against material");
    expect(stale.textContent).toContain("now held");

    fireEvent.click(stale);
    expect(
      await screen.findByText("Decided against a different verdict"),
    ).toBeInTheDocument();
  });

  it("keeps separate lines of questioning apart, and lets one be thrown away", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const threads = [
      {
        id: "conversation-1",
        review_id: "review-1",
        messages: [
          {
            question: "Why was the invoice boundary cleared?",
            answer: { text: "It matches the boundary policy.", supporting_candidate_ids: [] },
            asked_at: "2026-01-02T00:00:00Z",
          },
        ],
      },
      {
        id: "conversation-2",
        review_id: "review-1",
        messages: [
          {
            question: "Which policies were retrieved for the provider candidate?",
            answer: { text: "Dependency direction.", supporting_candidate_ids: [] },
            asked_at: "2026-01-02T00:01:00Z",
          },
        ],
      },
    ];
    vi.spyOn(api, "conversations").mockResolvedValue(threads);
    const remove = vi.spyOn(api, "deleteConversation").mockResolvedValue(undefined);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Ask/ }));
    const panel = screen.getByRole("tabpanel");

    // Nobody titles their own notes, so a thread is named by the question that opened it.
    const tabs = await within(panel).findByRole("tablist", { name: "Conversations" });
    expect(within(tabs).getAllByRole("tab")).toHaveLength(2);

    // One thread is shown at a time — reading two interleaved is worse than reading either.
    fireEvent.click(within(tabs).getByRole("tab", { name: /Why was the invoice boundary/ }));
    expect(within(panel).getByText("It matches the boundary policy.")).toBeInTheDocument();
    expect(within(panel).queryByText("Dependency direction.")).not.toBeInTheDocument();

    // Discarding is asked about, because there is nowhere to undo it to.
    fireEvent.click(within(panel).getByRole("button", { name: "Discard this conversation" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("conversation-1"));
  });

  it("opens the finding an answer cited, because the answer never saw the code", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "conversations").mockResolvedValue([
      {
        id: "conversation-1",
        review_id: "review-1",
        messages: [
          {
            question: "How would it be fixed?",
            answer: {
              text: "Resolve the provider at composition time.",
              supporting_candidate_ids: ["candidate-3"],
            },
            asked_at: "2026-01-02T00:00:00Z",
          },
        ],
      },
    ]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Ask/ }));
    const panel = screen.getByRole("tabpanel");

    fireEvent.click(await within(panel).findByText("The invoice boundary is appropriate"));
    expect(screen.getByRole("tab", { name: /Workbench/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const queue = await screen.findByRole("list", { name: "Candidates" });
    expect(within(queue).getByText("The invoice boundary is appropriate")).toBeInTheDocument();
  });

  it("moves the queue and the context into drawers on a phone", async () => {
    setViewportWidth(VIEWPORT.phone);
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const open = await screen.findByRole("button", { name: "Attention queue" });
    fireEvent.click(open);
    const drawer = await screen.findByRole("dialog", { name: "Attention queue" });
    expect(within(drawer).getByText("The provider abstraction carries one implementation"))
      .toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Attention queue" })).not.toBeInTheDocument(),
    );
  });

  it("shows the failure of a failed review without hiding the rest of it", async () => {
    const review = reviewFixture({
      status: "failed",
      questions: [],
      failure: "The embedding provider was unreachable",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The embedding provider was unreachable",
    );
    expect(screen.getByText("Domain depends on an adapter")).toBeInTheDocument();
  });

  it("shows the revision being made in the same rail as the ones that exist", async () => {
    // A run is filed under the same repository, branch and case a review is, and the
    // sequence it will carry is known from the newest review on the branch. So it is the
    // next entry of this lineage, addressable while it is still being made.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence + 1,
      }),
    ]);

    render(wrap(<ReviewPage />));

    const pending = await screen.findByRole("link", {
      name: new RegExp(`Review ${review.sequence + 1}`),
    });
    // A link, not a button: the run has its own address, and that page renders this same
    // head and rail around its progress rather than a job view with a thread id on it.
    expect(pending).toHaveAttribute("href", "/runs/thread-9");
    expect(within(pending).getByText("In progress")).toBeInTheDocument();
  });

  it("leaves the rail alone when the run in flight belongs to another case", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([runFixture({ case_id: "some-other-case" })]);

    render(wrap(<ReviewPage />));

    await screen.findByText("Review lineage");
    expect(screen.queryByText(/In progress/)).not.toBeInTheDocument();
  });
});
