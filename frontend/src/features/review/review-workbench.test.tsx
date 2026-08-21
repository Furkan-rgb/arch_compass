import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type Decision } from "../../api";
import { VIEWPORT, setViewportWidth } from "../../test-setup";
import { investigationFixture, reviewFixture, runFixture } from "../../test-fixtures";
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

/**
 * The rows of the docket, and only the rows, in the order they are listed.
 *
 * Two things make `getAllByRole("button")` the wrong question here. A row opens in place, so
 * an open list also holds that finding's own buttons — a disclosure, "Judgement context", the
 * decision bar — which belong to the assessment rather than to the list. And the docket
 * splits into groups when something moved, which is genuinely two lists on the page.
 * `data-candidate` is what a row is, and reading them off the document is the same question
 * the eye asks: what is on this docket, top to bottom.
 */
const rows = () => Array.from(document.querySelectorAll<HTMLElement>("[data-candidate]"));

/** Wait for the docket to have listed the review, then hand back its rows. */
async function docket() {
  await screen.findAllByRole("list", { name: /^Candidates/ });
  return rows();
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

    // Said once. The docket lists the round as its first item, under a header naming it and
    // a sentence saying what answering does; the round used to restate both inside a second
    // card with its own border and its own heading.
    expect(await screen.findByText("1 question wants an answer")).toBeInTheDocument();
    expect(screen.queryByText("The repository cannot answer these")).not.toBeInTheDocument();
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
    const listed = (await docket()).map((item) => item.textContent ?? "");
    expect(listed[0]).toContain("The provider abstraction carries one implementation");
    expect(listed[1]).toContain("Domain depends on an adapter");
    expect(listed.join(" ")).not.toContain("The invoice boundary is appropriate");

    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    const all = (await docket()).map((item) => item.textContent ?? "");
    expect(all.at(-1)).toContain("The invoice boundary is appropriate");
  });

  it("carries each candidate's claim on its own row, so the list can be read", async () => {
    // The reason the rail and the workbench became one column. A rail of leaf names read
    // `Clock`, `ConfigLoader`, `IdGenerator` — you could not tell from it which of six rows
    // mattered, so you opened all six. A row that says what it claims is one most readers
    // never have to open.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    for (const row of await docket()) {
      const finding = review.findings.find((item) =>
        row.textContent?.includes(item.candidate.summary),
      );
      expect(finding, `a row read "${row.textContent}" and claims nothing`).toBeDefined();
    }
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

    // The identifier leads, because that is what a reviewer is looking for — and the claim
    // is in the heading with it, because two candidates in one package share a name and a
    // list of identical headings navigates nowhere.
    const heading = await screen.findByRole("heading", {
      name: "domain.orders — The provider abstraction carries one implementation",
    });
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

    const resolved = await screen.findByText(/of 1 resolved/);
    expect(resolved).toHaveTextContent("0 of 1 resolved");
    fireEvent.click(screen.getByRole("button", { name: "Skip explicitly" }));
    expect(screen.getByText(/of 1 resolved/)).toHaveTextContent("1 of 1 resolved");

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
    expect(screen.getByRole("tab", { name: /Docket/ })).toHaveAttribute(
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
    expect(await docket()).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Attention 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Settled 2/ })).toBeInTheDocument();

    // ...and says so where it was, rather than only inside the finding.
    fireEvent.click(screen.getByRole("button", { name: /^Settled 2/ }));
    expect(await screen.findByText("Waived by the team")).toBeInTheDocument();
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
    await docket();
    expect(screen.getByText("The invoice boundary is appropriate")).toBeInTheDocument();
  });

  it("keeps the audit behind the judgement it audits", async () => {
    // Retrieval provenance was a surface of its own, sitting beside the queue as though a
    // reviewer working down a list might switch to reading corpus fingerprints. It answers
    // "why this candidate", so it belongs where that candidate is.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click((await docket())[1]);
    fireEvent.click(await screen.findByRole("button", { name: "Judgement context" }));

    const drawer = await screen.findByRole("dialog", { name: "Judgement context" });
    fireEvent.click(within(drawer).getByRole("tab", { name: /Provenance/ }));
    expect(within(drawer).getByText(/dense-scoped/)).toBeInTheDocument();
    expect(within(drawer).getByText("corpus-fingerprint")).toBeInTheDocument();
    expect(within(drawer).getByText("ollama:nomic-embed-text")).toBeInTheDocument();
  });

  it("leads the case with the answers this candidate was actually judged against", async () => {
    // A question records the candidates it was asked about, and the case tab used to ignore
    // that: every review that had been through two clarification rounds showed the same
    // undifferentiated list under every finding, and a reader had to re-derive which answer
    // was about the thing in front of them. The other answers stay reachable, because the
    // judge is shown the whole case and a rail called Judgement context has to be true.
    const question = (id: string, text: string, candidateIds: string[]) => ({
      id,
      text,
      facet: "decision",
      candidate_ids: candidateIds,
      round: 1,
      equivalence_key: `decision:${candidateIds.join(",")}`,
      options: [],
    });
    const review = reviewFixture({
      status: "completed",
      questions: [],
      case: {
        id: "case-1",
        revision: 3,
        answers: [
          {
            question: question("q-1", "Who owns persistence?", ["candidate-1"]),
            status: "answered",
            value: "The domain owns it.",
            actor: "engineer",
            answered_at: "2026-01-02T00:00:00Z",
          },
          {
            question: question("q-2", "Is the second adapter planned?", ["candidate-2"]),
            status: "answered",
            value: "Yes, next quarter.",
            actor: "engineer",
            answered_at: "2026-01-02T00:00:00Z",
          },
        ],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      },
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click((await docket())[1]);
    fireEvent.click(await screen.findByRole("button", { name: "Judgement context" }));
    const drawer = await screen.findByRole("dialog", { name: "Judgement context" });

    expect(
      within(drawer).getByText("Who owns persistence?").closest("details"),
    ).toBeNull();
    const folded = within(drawer)
      .getByText("Is the second adapter planned?")
      .closest("details");
    expect(folded).not.toBeNull();
    expect(folded).not.toHaveAttribute("open");
  });

  it("keeps your place in the docket while another surface is read", async () => {
    // The charter's first interface rule is that the queue is the product, and the rule used
    // to be enforced as "the rail stays mounted": the queue was a column beside the work, so
    // it could be there while the work changed. It is the work now, and cannot be beside
    // itself — so what the rule protects is the thing it always meant. Reading the report is
    // not supposed to cost you the row you were on, the filter you set, or your scroll.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("button", { name: /^All/ }));
    fireEvent.click((await docket())[2]);
    const before = rows().map((row) => row.dataset.candidate);

    fireEvent.click(screen.getByRole("tab", { name: /Delta/ }));
    fireEvent.click(screen.getByRole("tab", { name: /Ask/ }));
    fireEvent.click(screen.getByRole("tab", { name: /Docket/ }));

    const after = await docket();
    expect(after.map((row) => row.dataset.candidate)).toEqual(before);
    expect(after[2]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /^All/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("walks the queue with the keyboard and opens what it lands on", async () => {
    // The most repeated action in the product, and it was pointer-only.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const first = (await docket())[0];
    expect(first).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(first, { key: "j" });
    const moved = rows();
    expect(moved[1]).toHaveAttribute("aria-expanded", "true");
    // And what it landed on is open under it, rather than painted into a column elsewhere.
    await waitFor(() =>
      expect(document.querySelector("#finding-panel-candidate-1")).not.toBeNull(),
    );

    fireEvent.keyDown(moved[1], { key: "ArrowUp" });
    expect(rows()[0]).toHaveAttribute("aria-expanded", "true");
  });

  it("hands you the next thing that wants you when you decide one", async () => {
    // The rhythm the two-pane version never had, and the two ways it can go wrong: sending
    // you back to the top of the list, and letting the row you just decided vanish from
    // under you so there is no way to check what you did.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const decisions: Decision[] = [];
    vi.spyOn(api, "decisions").mockImplementation(async () => ({
      branch_id: "branch-1",
      decisions: [...decisions],
    }));
    vi.spyOn(api, "decide").mockImplementation(async (_review, candidateId) => {
      const finding = review.findings.find((item) => item.candidate.id === candidateId)!;
      const decision: Decision = {
        id: `decision-${candidateId}`,
        branch_id: "branch-1",
        candidate_id: candidateId,
        disposition: "accept",
        author: "user",
        reasoning: null,
        decided_at: "2026-01-01T00:00:00Z",
        review_id: "review-1",
        finding_verdict: finding.verdict,
        finding_model_identity: "fake:deterministic",
        finding_prompt_identity: "judge:v1",
        finding_retrieval_identity: "retrieval-1",
      };
      decisions.push(decision);
      return decision;
    });

    render(wrap(<ReviewPage />));

    // Two candidates want a person; the docket opens on the first.
    const [first, second] = await docket();
    expect(first).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));

    // The one below it opens...
    await waitFor(() => expect(rows()[1]).toHaveAttribute("aria-expanded", "true"));
    expect(rows()[1].dataset.candidate).toBe(second.dataset.candidate);
    // ...and the one just decided is still listed, saying what was decided about it.
    expect(rows()[0].textContent).toContain("Accepted by the team");
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
    const listed = await docket();
    expect(screen.getByText("Moved since review 1")).toBeInTheDocument();
    expect(screen.getByText("Carried forward")).toBeInTheDocument();
    // The one that moved leads, even though it came back cleared and two material and held
    // candidates were carried forward — the headings are what make that honest.
    expect(listed[0].textContent).toContain("The invoice boundary is appropriate");
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

  it("leads the report with what the review comes to, and says it once", async () => {
    // The report used to open on counts. "1 material, 3 held" is how much there is, not
    // what it amounts to, and a reader arriving at a review of forty candidates wants the
    // second thing first. The document carries the paragraph too — it is downloaded and
    // attached to pull requests — so the page has to render the document without it or the
    // reader meets the same three sentences twice on one screen.
    const review = reviewFixture({
      status: "completed",
      questions: [],
      synopsis: "Both material findings reach past the ports layer to the same adapter.",
      synopsis_identity: "google:gemini-3-pro",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewReport").mockResolvedValue(
      [
        "# Architecture review — payments",
        "",
        "Four candidates judged: **1 material**, 3 held, 0 cleared.",
        "",
        "**In summary.** Both material findings reach past the ports layer to the same adapter.",
        "",
        "## Material — 1",
      ].join("\n"),
    );

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Report/ }));

    const summary = await screen.findAllByText(
      /Both material findings reach past the ports layer/,
    );
    expect(summary).toHaveLength(1);
    // In the model's voice: attributed, at the reading size, ahead of the document.
    expect(screen.getByText("In summary")).toBeInTheDocument();
    expect(screen.getByText(/google:gemini-3-pro/)).toBeInTheDocument();
    // And the rest of the document is untouched.
    expect(screen.getByText(/Four candidates judged/)).toBeInTheDocument();
  });

  it("opens the report on its counts when no model wrote a summary", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewReport").mockResolvedValue(
      "# Architecture review — payments\n\nFour candidates judged: **1 material**, 3 held, 0 cleared.",
    );

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Report/ }));

    expect(await screen.findByText(/Four candidates judged/)).toBeInTheDocument();
    expect(screen.queryByText("In summary")).not.toBeInTheDocument();
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
    const stale = (await docket()).find((row) =>
      row.textContent?.includes("Domain depends on an adapter"),
    )!;
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
            answer: {
              text: "It matches the boundary policy.",
              supporting_candidate_ids: [],
              investigation: null,
            },
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
            answer: { text: "Dependency direction.", supporting_candidate_ids: [], investigation: null },
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
              investigation: null,
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
    expect(screen.getByRole("tab", { name: /Docket/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await docket();
    expect(screen.getByText("The invoice boundary is appropriate")).toBeInTheDocument();
  });

  it("shows what an answer looked up in the repository", async () => {
    // An answer that says "nothing else implements it" has either checked or guessed, and
    // a reader with only the sentence cannot tell which. The transcript is the difference.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "conversations").mockResolvedValue([
      {
        id: "conversation-1",
        review_id: "review-1",
        messages: [
          {
            question: "Does anything else implement it?",
            answer: {
              text: "One implementation, in billing.sql.",
              supporting_candidate_ids: [],
              investigation: investigationFixture({ candidate_id: "" }),
            },
            asked_at: "2026-01-02T00:00:00Z",
          },
        ],
      },
    ]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Ask/ }));
    const panel = screen.getByRole("tabpanel");

    // Closed by default: the answer is what the reader came for.
    expect(await within(panel).findByText("2 lookups")).toBeInTheDocument();
    expect(within(panel).getByText(/asked what implementations node_a1/)).not.toBeVisible();
    fireEvent.click(within(panel).getByText("Looked up"));
    expect(within(panel).getByText(/asked what implementations node_a1/)).toBeVisible();
  });

  it("is the same one column on a phone as on a desk", async () => {
    // The two-pane version could not fit a phone, so it grew a phone version: the queue in a
    // drawer, the finding on the page, a back bar to get between them — a second interface
    // with its own navigation, its own bugs and nothing in common with the one people learn
    // on a laptop. One column is the same column at 390px. Nothing is behind a drawer, and
    // there is nothing to go "back" to, because opening a row never took you anywhere.
    setViewportWidth(VIEWPORT.phone);
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const [first] = await docket();
    expect(screen.queryByRole("button", { name: "Queue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Attention queue" })).not.toBeInTheDocument();

    // The row that is open shows its whole assessment under itself, with the list still there.
    expect(first).toHaveAttribute("aria-expanded", "true");
    const article = first.closest("article")!;
    expect(within(article).getByText("Judged")).toBeInTheDocument();
    expect(within(article).getByText(/Nobody has decided this/)).toBeInTheDocument();

    // And closing it leaves you exactly where you were, on the row you closed.
    fireEvent.click(first);
    expect(rows()[0]).toHaveAttribute("aria-expanded", "false");
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

  it("says what the review checked before it asked", async () => {
    // A hinge a reader cannot see the checking behind is a hinge they cannot weigh: "the
    // repository is silent on this" and "nothing looked" are opposite facts about a
    // question, and until this fold existed the screen said neither.
    const review = reviewFixture({ status: "completed", questions: [] });
    review.findings[1].investigation_identity = "investigation-1";
    review.investigation_manifest = [investigationFixture({ candidate_id: "candidate-1" })];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const heading = await screen.findByRole("heading", {
      name: "domain.orders — Domain depends on an adapter",
    });
    const article = heading.closest("article")!;
    // One row opens at a time and the queue leads with the material one, so this hinged
    // candidate has to be opened before its assessment is on screen.
    fireEvent.click(within(article).getByRole("button", { expanded: false }));
    // The closed state names the count and what came of it, because a fold that says only
    // "Looked up" makes a reader open it to find out whether it was worth opening.
    expect(within(article).getByText("2 lookups · settled the hinge")).toBeInTheDocument();
    // The transcript is in the DOM and folded, like the provenance beside it.
    expect(within(article).getByText(/asked what implementations node_a1/)).not.toBeVisible();
    fireEvent.click(within(article).getByText("Looked up"));
    expect(within(article).getByText(/asked what implementations node_a1/)).toBeVisible();
    expect(
      within(article).getByText("One implementation, and no test reaches it."),
    ).toBeVisible();
  });

  it("says why nothing could be looked up rather than showing an empty fold", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    review.investigation_manifest = [
      investigationFixture({
        candidate_id: "candidate-1",
        lookups: [],
        closing: "",
        resolved: false,
        withheld: "This repository has changed since the review ran; index it again.",
      }),
    ];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const heading = await screen.findByRole("heading", {
      name: "domain.orders — Domain depends on an adapter",
    });
    const article = heading.closest("article")!;
    // One row opens at a time and the queue leads with the material one, so this hinged
    // candidate has to be opened before its assessment is on screen.
    fireEvent.click(within(article).getByRole("button", { expanded: false }));
    expect(within(article).getByText("nothing could be looked up")).toBeInTheDocument();
    fireEvent.click(within(article).getByText("Looked up"));
    expect(within(article).getByText(/index it again/)).toBeVisible();
  });

  it("shows no fold at all for a finding nothing was looked up for", async () => {
    // An empty disclosure is a claim that something looked. Most findings never hinge.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const heading = await screen.findByRole("heading", {
      name: "domain.orders — Domain depends on an adapter",
    });
    const article = heading.closest("article")!;
    // One row opens at a time and the queue leads with the material one, so this hinged
    // candidate has to be opened before its assessment is on screen.
    fireEvent.click(within(article).getByRole("button", { expanded: false }));
    expect(within(article).queryByText("Looked up")).not.toBeInTheDocument();
  });
});
