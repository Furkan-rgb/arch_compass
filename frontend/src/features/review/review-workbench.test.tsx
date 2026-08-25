import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type Decision } from "../../api";
import { VIEWPORT, setHasKeyboard, setViewportWidth } from "../../test-setup";
import {
  investigationFixture,
  reviewFixture,
  reviewSummaryFixture,
  runFixture,
} from "../../test-fixtures";
import { ReviewPage } from "./review-page";

function CurrentPath() {
  const { pathname, search } = useLocation();
  return <span data-testid="path">{`${pathname}${search}`}</span>;
}

function wrap(children: ReactNode, path = "/reviews/review-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/reviews/:reviewId" element={children} />
          {/* Answering a clarification hands the rejudgement to a run and follows it there,
              so the router needs somewhere for it to land. */}
          <Route path="/runs/:runId" element={<span>The run</span>} />
        </Routes>
        {/* A memory router never touches `window.location`, so the URL a test asserts on has
            to be read from the router itself. */}
        <CurrentPath />
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
const rows = () =>
  Array.from(document.querySelectorAll<HTMLElement>("[data-candidate]"));

/** Wait for the docket to have listed the review, then hand back its rows. */
async function docket() {
  await screen.findAllByRole("list", { name: /^Candidates/ });
  return rows();
}

/**
 * The progress strip's marks, and how many of them are filled.
 *
 * Read off the class rather than through a hook of its own: the strip is `aria-hidden`
 * decoration beside a sentence that carries the same fact in words, and a `data-` attribute
 * added to it would exist for this test and for nothing else.
 */
function progress() {
  const marks = Array.from(
    document.querySelectorAll<HTMLElement>('span[class*="w-[5px]"]'),
  );
  return {
    total: marks.length,
    filled: marks.filter((mark) => mark.className.includes("bg-ink")).length,
  };
}

/** A review with more candidates than the docket's own devices are sized for. */
function wideReview(count: number, cleared: number) {
  const base = reviewFixture({ status: "completed", questions: [] });
  const [template] = base.findings;
  const findings = Array.from({ length: count }, (_, index) => ({
    ...template,
    verdict: index < cleared ? "cleared" : "material",
    candidate: {
      ...template.candidate,
      id: `wide-${index}`,
      summary: `Candidate ${index} claims something`,
      participants: [
        { qualified_name: `domain.wide.Thing${index}`, role: "source", node_id: null },
      ],
    },
  }));
  return {
    ...base,
    findings,
    delta: {
      unchanged: [],
      changed: [],
      new: findings.map((finding) => finding.candidate.id),
      addressed: [],
    },
  };
}

/** A workspace that records what it is told, so a second decision sees the first. */
function recordDecisions(review: ReturnType<typeof reviewFixture>) {
  const recorded: Decision[] = [];
  vi.spyOn(api, "decisions").mockImplementation(async () => ({
    branch_id: "branch-1",
    decisions: [...recorded],
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
    recorded.push(decision);
    return decision;
  });
  return recorded;
}

beforeEach(() => {
  setViewportWidth(VIEWPORT.desktop);
  vi.spyOn(api, "decisions").mockResolvedValue({
    branch_id: "branch-1",
    decisions: [],
  });
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
  // The lineage rail reads the listing rather than the reviews themselves — a stored review
  // is most of a repository's atlas, and the rail draws a number and a date off each entry.
  vi.spyOn(api, "reviewSummaries").mockResolvedValue([reviewSummaryFixture()]);
});

afterEach(() => {
  vi.restoreAllMocks();
  setViewportWidth(VIEWPORT.desktop);
  setHasKeyboard(true);
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
    expect(
      await screen.findByText("1 question wants an answer"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("The repository cannot answer these"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Who owns persistence?")).toBeInTheDocument();
    // And exactly one way to answer it. The chrome used to carry an "Answer 1" button while
    // the queue listed the clarification and the finding offered it again under "Hinges on" —
    // one action with four affordances, which reads as nagging rather than as confident. The
    // queue keeps its row, because the queue is the list of things needing a person; a button
    // in the header is not.
    expect(
      screen.queryByRole("button", { name: /^Answer \d/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/waiting on 1 unanswered question/),
    ).toBeInTheDocument();
  });

  it("orders the queue by what needs a human, cleared findings last", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    // The default filter is "attention", so the cleared candidate is deliberately not listed.
    const listed = (await docket()).map((item) => item.textContent ?? "");
    expect(listed[0]).toContain(
      "The provider abstraction carries one implementation",
    );
    expect(listed[1]).toContain("Domain depends on an adapter");
    expect(listed.join(" ")).not.toContain(
      "The invoice boundary is appropriate",
    );

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
      expect(
        finding,
        `a row read "${row.textContent}" and claims nothing`,
      ).toBeDefined();
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
    expect(
      within(article).getByText(/Nobody has decided this/),
    ).toBeInTheDocument();
    expect(
      within(article).getByText(
        "The provider abstraction carries one implementation",
      ),
    ).toBeInTheDocument();
    expect(
      within(article).getByText(/Recommended response/),
    ).toBeInTheDocument();
    expect(
      within(article).getByText(/Dependencies point inward/),
    ).toBeInTheDocument();
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

    expect(
      await screen.findByText(/Nobody has decided this/),
    ).toBeInTheDocument();

    // Waiving without a reason is still refused by the form rather than by the server — but
    // the refusal moved to where the reason is. Waive is a disclosure now: the field it needs
    // does not exist until it is pressed, because it was the widest control in the bar and
    // empty in the two states that do not want it.
    const waive = screen.getByRole("button", { name: "Waive" });
    expect(waive).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(waive);
    expect(waive).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: /Record waiver/ }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));
    await waitFor(() =>
      expect(decide).toHaveBeenCalledWith(
        "review-1",
        "candidate-2",
        "accept",
        null,
      ),
    );
  });

  it("records an explicit skip and hands the rejudgement to a run", async () => {
    // Answering rejudges every extant candidate, which is minutes of model work. It used to
    // be held inside one POST, so the browser tab was the thing keeping it alive: a reload, a
    // closed laptop or a proxy timeout left a person unable to tell whether their answers had
    // been recorded at all. The run is somewhere to come back to.
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());

    render(wrap(<ReviewPage />));

    const resolved = await screen.findByText(/of 1 resolved/);
    expect(resolved).toHaveTextContent("0 of 1 resolved");
    // The round is a stack, so there is nothing to step with — no Previous, no Next, and no
    // position to report. What is left is the counter, which says how much is left to do.
    expect(
      screen.queryByRole("button", { name: /^Next/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Previous/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Skip explicitly" }));
    expect(screen.getByText(/of 1 resolved/)).toHaveTextContent(
      "1 of 1 resolved",
    );

    fireEvent.click(screen.getByRole("button", { name: "Save and rejudge" }));
    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [{ question_id: "question-1", status: "skipped", value: null }],
        false,
      ),
    );
    // And the page stays where it is. It used to navigate to the run's own address, which
    // swapped the heading, the findings and the surface for a progress list and discarded
    // the scroll position, the open finding and the filter on the way — for a review the
    // reader was already on, being rejudged.
    await waitFor(() =>
      expect(screen.getByTestId("path")).toHaveTextContent("/reviews/review-1"),
    );
  });

  it("keeps the round on screen as the record of what was just answered", async () => {
    // The item that had just been worked on used to leave the screen entirely: the page
    // navigated away, and nothing said the answers had landed or what they had set going.
    // The round stays, as the record of what was said and the work it started.
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());
    // The refetch a client makes after answering: the round has been taken, so the snapshot
    // is no longer the one anybody can answer, and the run is in flight against the lineage.
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence,
        candidates_to_judge: 46,
        candidates_judged: 4,
      }),
    ]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Skip explicitly" }));
    vi.spyOn(api, "review").mockResolvedValue({ ...review, answerable: false });
    fireEvent.click(screen.getByRole("button", { name: "Save and rejudge" }));

    expect(await screen.findByText(/Round 1 answered/)).toBeInTheDocument();
    // What it set going, said where the button was pressed rather than on a page you have to
    // scroll to: this is the moment half an hour of model work is committed to.
    expect(await screen.findByText(/Judging 46 candidates again/)).toBeInTheDocument();
    expect(screen.getByText(/you can close it/)).toBeInTheDocument();
    // And the form is gone with the round it belonged to.
    expect(
      screen.queryByRole("button", { name: "Save and rejudge" }),
    ).not.toBeInTheDocument();
  });

  it("stacks the round, and opens the next question when one is answered", async () => {
    // The round used to be a slideshow: one question, a stepper, Previous and Next. Answering
    // took the question away, which is the decision all three were paying for. The docket
    // beside this had already settled it — a decision opens the next row that wants a person
    // while the row you just decided stays listed — and this is that, for questions.
    const first = reviewFixture().questions[0];
    const review = reviewFixture({
      questions: [
        first,
        {
          ...first,
          id: "question-2",
          text: "Is the second adapter planned?",
          candidate_ids: ["candidate-2"],
          equivalence_key: "decision:candidate-2",
          options: [],
        },
      ],
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());

    render(wrap(<ReviewPage />));

    // Both questions are on screen from the start — the second as a row, not as a form, so
    // nothing further down the round is a surprise waiting to happen.
    expect(
      await screen.findByText("Who owns persistence?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Is the second adapter planned?"),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Is the second adapter planned?"),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );

    // Answering opens the next one, and leaves the first listed as the answer it was given.
    expect(
      screen.getByLabelText("Is the second adapter planned?"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Who owns persistence\? — answered: The domain owns it/,
      }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Is the second adapter planned?"), {
      target: { value: "Yes, next quarter." },
    });

    // Both answers are submitted, including the one whose question is now a closed row. That
    // is the whole reason the round holds the values rather than the questions.
    fireEvent.click(screen.getByRole("button", { name: "Save and rejudge" }));
    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith(
        "review-1",
        [
          {
            question_id: "question-1",
            status: "answered",
            value: "The domain owns it and adapters implement its ports",
          },
          {
            question_id: "question-2",
            status: "answered",
            value: "Yes, next quarter.",
          },
        ],
        false,
      ),
    );
  });

  it("carries the keyboard to the question it opened", async () => {
    // The control that was just clicked unmounts with its row, so focus lands on `<body>`
    // and a keyboard is nowhere at all. The round moved; whoever is working it has to move
    // with it, and that is not something a mouse-only reading of "opens the next one" covers.
    const first = reviewFixture().questions[0];
    const review = reviewFixture({
      questions: [
        first,
        {
          ...first,
          id: "question-2",
          text: "Is the second adapter planned?",
          options: [],
        },
      ],
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );

    const opened = screen.getByLabelText("Is the second adapter planned?");
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement?.contains(opened)).toBe(true);
  });

  it("leaves the last question open, because nothing opened to close it", async () => {
    // A row closes because another one opened. The round of one is the common shape, and
    // folding its only question on the pick would read as the form swallowing the answer.
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );

    expect(
      screen.getByRole("radiogroup", {
        name: /Answers to: Who owns persistence/,
      }),
    ).toBeInTheDocument();
  });

  it("says where each question in the round stands, and reopens one", async () => {
    const first = reviewFixture().questions[0];
    const review = reviewFixture({
      questions: [
        first,
        {
          ...first,
          id: "question-2",
          text: "Is the second adapter planned?",
          options: [],
        },
        {
          ...first,
          id: "question-3",
          text: "Which team owns the gateway?",
          options: [],
        },
      ],
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const round = await screen.findByRole("list", {
      name: /Questions in clarification/,
    });
    expect(within(round).getAllByRole("listitem")).toHaveLength(3);

    // A skip is a decision, so it moves the round on the way an answer does — and the row it
    // left says it was skipped rather than that it is still waiting.
    fireEvent.click(screen.getByRole("button", { name: "Skip explicitly" }));
    expect(
      screen.getByLabelText("Is the second adapter planned?"),
    ).toBeInTheDocument();
    const skippedRow = screen.getByRole("button", {
      name: /Who owns persistence\? — skipped explicitly/,
    });

    // A closed row is a way back into the question, not just a picture of one.
    fireEvent.click(skippedRow);
    expect(
      screen.getByRole("radiogroup", {
        name: /Answers to: Who owns persistence/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Is the second adapter planned?"),
    ).not.toBeInTheDocument();
  });

  it("carries an answer through as answered rather than skipped", async () => {
    // A question with nothing proposed is answered by writing, which is the shape every
    // question had before the model started offering answers.
    const review = reviewFixture({
      questions: [{ ...reviewFixture().questions[0], options: [] }],
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const answer = vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());

    render(wrap(<ReviewPage />));

    fireEvent.change(await screen.findByLabelText("Who owns persistence?"), {
      target: { value: "  The platform team owns it.  " },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Conclude with remaining uncertainty",
      }),
    );

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
    const answer = vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());

    render(wrap(<ReviewPage />));

    // The model proposed these, so the reviewer's whole job here is one click.
    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Conclude with remaining uncertainty",
      }),
    );

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
    const answer = vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());

    render(wrap(<ReviewPage />));

    // There is no box while the offered answers stand — the menu is the shorter path, and
    // two ways to answer the same question at once is a worse question.
    expect(
      screen.queryByLabelText("Who owns persistence?"),
    ).not.toBeInTheDocument();

    fireEvent.click(
      await screen.findByRole("radio", { name: /Something else/ }),
    );
    fireEvent.change(screen.getByLabelText("Who owns persistence?"), {
      target: { value: "Neither — it is a shared kernel." },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Conclude with remaining uncertainty",
      }),
    );

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
    const list = within(panel).getByRole("list", {
      name: "Candidates by change",
    });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);

    fireEvent.click(within(panel).getByRole("button", { name: /Unchanged 1/ }));
    expect(
      within(
        within(panel).getByRole("list", { name: "Candidates by change" }),
      ).getAllByRole("listitem"),
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
    expect(
      screen.getByRole("button", { name: /^Attention 1/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Settled 2/ }),
    ).toBeInTheDocument();

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
    expect(
      screen.getByText("The invoice boundary is appropriate"),
    ).toBeInTheDocument();
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
    fireEvent.click(
      await screen.findByRole("button", { name: "Judgement context" }),
    );

    const drawer = await screen.findByRole("dialog", {
      name: "Judgement context",
    });
    fireEvent.click(within(drawer).getByRole("tab", { name: /Provenance/ }));
    expect(within(drawer).getByText(/dense-scoped/)).toBeInTheDocument();
    expect(within(drawer).getByText("corpus-fingerprint")).toBeInTheDocument();
    expect(
      within(drawer).getByText("ollama:nomic-embed-text"),
    ).toBeInTheDocument();
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
            question: question("q-2", "Is the second adapter planned?", [
              "candidate-2",
            ]),
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
    fireEvent.click(
      await screen.findByRole("button", { name: "Judgement context" }),
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Judgement context",
    });

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
    expect(screen.getByRole("button", { name: /^All/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps the surface strip on screen while a long docket is read", async () => {
    // jsdom does no layout, so this asserts the two properties that make it stick rather than
    // the stuck position: the strip is pinned below the 48px rail, and a row walked to leaves
    // room for both. The pair is the whole rule — pinning the strip without moving the row's
    // scroll margin puts the row it just walked to underneath the thing that was pinned to
    // help it, which is worse than not pinning at all.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const strip = (await screen.findAllByRole("tablist"))[0].parentElement?.parentElement;
    expect(strip?.className).toContain("sticky");
    expect(strip?.className).toContain("top-12");

    // `scroll-margin-top` applies to the element that is scrolled into view, so the margin
    // and the `scrollIntoView` call have to land on the same element. They did not: the
    // margin was on the article and the call was on the button inside it, which made the
    // clearance inert from the day it was written and invisible to every test that only
    // looked for the class. jsdom implements no `scrollIntoView`, so the receiver is the
    // only thing there is to assert on — and it is the thing that was wrong.
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(this);
    };

    const listed = await docket();
    for (const row of listed) {
      expect(row.closest("article")?.className).toContain("scroll-mt-24");
    }

    fireEvent.click(listed[1]);
    expect(scrolled.at(-1)?.tagName).toBe("ARTICLE");
    expect((scrolled.at(-1) as HTMLElement).className).toContain("scroll-mt-24");
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
      expect(
        document.querySelector("#finding-panel-candidate-1"),
      ).not.toBeNull(),
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
      const finding = review.findings.find(
        (item) => item.candidate.id === candidateId,
      )!;
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
    await waitFor(() =>
      expect(rows()[1]).toHaveAttribute("aria-expanded", "true"),
    );
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
    expect(listed[0].textContent).toContain(
      "The invoice boundary is appropriate",
    );
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
    expect(
      screen.getByText(/Nothing in this review is waiting on a person/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Read the report/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Run the next review/ }),
    ).toBeInTheDocument();

    // And it is a way into the record, not a dead end.
    fireEvent.click(screen.getByRole("button", { name: /Read the report/ }));
    expect(screen.getByRole("tab", { name: /Report/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
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
      synopsis:
        "Both material findings reach past the ports layer to the same adapter.",
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

    expect(
      await screen.findByText(/Four candidates judged/),
    ).toBeInTheDocument();
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
            question:
              "Which policies were retrieved for the provider candidate?",
            answer: {
              text: "Dependency direction.",
              supporting_candidate_ids: [],
              investigation: null,
            },
            asked_at: "2026-01-02T00:01:00Z",
          },
        ],
      },
    ];
    vi.spyOn(api, "conversations").mockResolvedValue(threads);
    const remove = vi
      .spyOn(api, "deleteConversation")
      .mockResolvedValue(undefined);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Ask/ }));
    const panel = screen.getByRole("tabpanel");

    // Nobody titles their own notes, so a thread is named by the question that opened it.
    const tabs = await within(panel).findByRole("tablist", {
      name: "Conversations",
    });
    expect(within(tabs).getAllByRole("tab")).toHaveLength(2);

    // One thread is shown at a time — reading two interleaved is worse than reading either.
    fireEvent.click(
      within(tabs).getByRole("tab", { name: /Why was the invoice boundary/ }),
    );
    expect(
      within(panel).getByText("It matches the boundary policy."),
    ).toBeInTheDocument();
    expect(
      within(panel).queryByText("Dependency direction."),
    ).not.toBeInTheDocument();

    // Discarding is asked about, because there is nowhere to undo it to.
    fireEvent.click(
      within(panel).getByRole("button", { name: "Discard this conversation" }),
    );
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

    fireEvent.click(
      await within(panel).findByText("The invoice boundary is appropriate"),
    );
    expect(screen.getByRole("tab", { name: /Docket/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await docket();
    expect(
      screen.getByText("The invoice boundary is appropriate"),
    ).toBeInTheDocument();
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
    expect(
      within(panel).getByText(/asked what implementations billing.gateway.PersistenceGateway/),
    ).not.toBeVisible();
    fireEvent.click(within(panel).getByText("Looked up"));
    expect(
      within(panel).getByText(/asked what implementations billing.gateway.PersistenceGateway/),
    ).toBeVisible();
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
    expect(
      screen.queryByRole("button", { name: "Queue" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("dialog", { name: "Attention queue" }),
    ).not.toBeInTheDocument();

    // The row that is open shows its whole assessment under itself, with the list still there.
    expect(first).toHaveAttribute("aria-expanded", "true");
    const article = first.closest("article")!;
    expect(within(article).getByText("Judged")).toBeInTheDocument();
    expect(
      within(article).getByText(/Nobody has decided this/),
    ).toBeInTheDocument();

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
    expect(
      screen.getByText("Domain depends on an adapter"),
    ).toBeInTheDocument();
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

  it("keeps a revision to one row while the run continuing it is in flight", async () => {
    // Answering a clarification carries on under the sequence the waiting snapshot already
    // occupies. Appended unconditionally, that listed review 1 twice — once as the snapshot
    // that asked, once as the work now judging — which is the entry this rail's contract
    // says never to add. It is one revision doing something, and the row says what.
    const review = reviewFixture({ answerable: false });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence,
        stage: "judge_candidate",
      }),
    ]);

    render(wrap(<ReviewPage />));

    await screen.findByText("Review lineage");
    const rows = screen.getAllByRole("link", {
      name: new RegExp(`Review ${review.sequence}`),
    });
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText("In progress")).toBeInTheDocument();
    // To the review, not to the run: the snapshot is still readable, and it is the run's
    // own progress that is now shown beneath the rail rather than on another page.
    expect(rows[0]).toHaveAttribute("href", `/reviews/${review.id}`);
    expect(await screen.findByLabelText("Review progress")).toBeInTheDocument();
  });

  it("stops offering the form once the round it belongs to has been answered", async () => {
    // A review is immutable, so this snapshot says `awaiting_answers` for ever — and that is
    // the only thing the page used to have. It kept the form up after the round had been
    // answered and was being judged, and submitting it did nothing, because the server
    // refuses a submission written against a superseded snapshot.
    const review = reviewFixture({ answerable: false });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    // The record is intact: the question it asked is still on it.
    expect(review.status).toBe("awaiting_answers");
    expect(review.questions).toHaveLength(1);
    // What is gone is the offer to answer it.
    await screen.findByText("Review lineage");
    expect(screen.queryByText("1 question wants an answer")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Save and rejudge|Answer/ }),
    ).not.toBeInTheDocument();
  });

  it("does not read another review's run as this round having been answered", async () => {
    // `pendingRun` matches the lineage — branch and case — which is what the rail wants and
    // not what the round wants. A second review of the same repository continues the branch's
    // newest case, so its run matched every completed review on that branch: the docket drew
    // "Round 1 answered" over an empty list on a review that had never asked anything, and
    // took the docket's opening row with it.
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

    await screen.findByText("Review lineage");
    expect(screen.queryByText(/answered$/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Every candidate is being judged again/),
    ).not.toBeInTheDocument();
    // And the docket still opens on the thing that wants a person, which the fabricated card
    // had taken.
    expect(
      await screen.findByText("The provider abstraction carries one implementation"),
    ).toBeInTheDocument();
  });

  it("does not read another review's run as this one, even when this one asked", async () => {
    // The sibling of the test above, and the half it could not hold. A completed review can
    // still carry the questions it asked: `_after_case_revision` seals a `stop_requested`
    // round without passing through `generate_questions`, and `_after_questions` seals at the
    // round ceiling and in CI, so the questions travel into the final draft. On such a review
    // the "did it ask anything" clause is satisfied, and only the sequence tells this
    // review's rejudgement from a second review of the same repository.
    const review = reviewFixture({ status: "completed", answerable: false });
    expect(review.questions).toHaveLength(1);
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

    await screen.findByText("Review lineage");
    expect(screen.queryByText(/Round 1 answered/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Every candidate is being judged again/),
    ).not.toBeInTheDocument();
  });

  it("does not call a round you just answered one that was never answered", async () => {
    // A waiting snapshot is filed before `revise_case` writes the round's answers to the
    // case, so it can never hold the answers to its own questions. Reading their absence as
    // "never answered" said the opposite of what happened, on the record a reader is looking
    // at for the whole of the rejudgement they just started.
    const review = reviewFixture({ answerable: false, superseded_by: null });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    expect(screen.queryByText(/never answered/)).not.toBeInTheDocument();
    // And no claim that it was answered, or that anything is being judged. Three endings
    // leave exactly this shape — sealing without rejudging, stopping the run, and a killed
    // process — and two of them are permanent. Closed is all this record can support.
    expect(await screen.findByText(/This round is closed/)).toBeInTheDocument();
    expect(
      screen.queryByText(/being judged again/),
    ).not.toBeInTheDocument();
  });

  it("does not tell somebody who stopped a review that it was answered", async () => {
    // Cancelling files a second snapshot and binds it, so the record a reader goes back to is
    // superseded with nothing ever answered. Told only that a successor exists, both surfaces
    // guessed "answered" — to the one person who knows it was not.
    const review = reviewFixture({
      answerable: false,
      superseded_by: "review-9",
      superseded_by_status: "cancelled",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();
    const row = rows().find((item) => item.dataset.candidate === "candidate-1");
    if (row?.getAttribute("aria-expanded") === "false") fireEvent.click(row);
    // Neither surface may claim it was answered. Neither may claim it was stopped either:
    // `superseded_by_status` is what became of the *review*, and for round one of a review
    // cancelled at round two it says `cancelled` over an answer that was given. What is
    // knowable from this record is where to look.
    expect(screen.queryByText(/has since been answered/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/what became of it is on the record that replaced this one/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Rounds/ }));
    expect(screen.queryByText(/never answered/)).not.toBeInTheDocument();
    expect(
      await screen.findByText(/What became of it is on the record that replaced this one/),
    ).toBeInTheDocument();
  });

  it("does not draw a round it has the answers to as still open", async () => {
    // `review.questions` is not "the open round" — it is whatever the snapshot was carrying.
    // Concluding with remaining uncertainty seals without passing through
    // `generate_questions`, so the review keeps the round it has just answered, and taking
    // that as open drew the same round twice: once with the answers, once beneath it with
    // every question marked "Asked, and never answered."
    const review = reviewFixture({ status: "completed", answerable: false });
    const asked = review.questions[0];
    review.case.revision = 2;
    review.case.answers = [
      {
        question: asked,
        status: "answered",
        value: "The domain owns it",
        actor: "furkan",
        answered_at: "2026-01-02T00:00:00Z",
        case_revision: 2,
      },
    ];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    expect(await screen.findByText("The domain owns it")).toBeInTheDocument();
    expect(screen.queryByText(/Asked, and never answered/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Round 1/)).toHaveLength(1);
    expect(screen.getByText(/One round of questions/)).toBeInTheDocument();
  });

  it("reads back a round answered entirely by skipping as skipped", async () => {
    // A skip is an answer — the deliberate kind, and what "Conclude with remaining
    // uncertainty" produces for every question at once — and it carries no text. Asking
    // "did anybody type something" to decide whether the round is readable meant an all-skip
    // round reported itself unreadable and called every deliberate skip "Answered".
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "answerRun").mockResolvedValue(runFixture());
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence,
      }),
    ]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Skip explicitly" }));
    vi.spyOn(api, "review").mockResolvedValue({ ...review, answerable: false });
    fireEvent.click(screen.getByRole("button", { name: "Save and rejudge" }));

    expect(await screen.findByText(/Round 1 answered/)).toBeInTheDocument();
    expect(await screen.findByText("Recorded as skipped")).toBeInTheDocument();
    expect(
      screen.queryByText(/Recorded on this review's case revision/),
    ).not.toBeInTheDocument();
  });

  it("lists every round of questions with what was said to each", async () => {
    // The whole clarification history had no surface at all. Answers were on the review, each
    // carrying the question it replies to, and the only place that rendered them was the
    // per-candidate judgement drawer — which shows the ones bearing on the candidate you have
    // open. Everywhere else they were a count, so a reviewer asked twice could not see what
    // the first round asked, what they had said, or that this was a second round.
    const review = reviewFixture();
    const asked = review.questions[0];
    review.case.revision = 2;
    review.case.answers = [
      {
        question: { ...asked, id: "question-r1a", text: "Who owns persistence?", round: 1 },
        status: "answered",
        value: "The domain owns it and adapters implement its ports",
        actor: "furkan",
        answered_at: "2026-01-02T00:00:00Z",
        case_revision: 2,
      },
      {
        question: { ...asked, id: "question-r1b", text: "Is a second store planned?", round: 1 },
        status: "skipped",
        value: null,
        actor: "furkan",
        answered_at: "2026-01-02T00:00:00Z",
        case_revision: 2,
      },
    ];
    review.questions = [{ ...asked, id: "question-r2", text: "Which layer owns retries?", round: 2 }];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    // Round 1, closed, with both of its answers — including the skip, which is a decision and
    // not an absence.
    expect(await screen.findByText("Round 1 · case revision 2")).toBeInTheDocument();
    expect(
      screen.getByText("The domain owns it and adapters implement its ports"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Recorded as skipped/)).toBeInTheDocument();
    // And round 2, which is where this reviewer is now, said as a round rather than as an
    // unexplained second form.
    // No revision on the open round: it has not opened one. `revise_case` opens a review's
    // revision when it records an answer, so until then `review.case.revision` is still the
    // number of the review before it — printed here it headed the open round with a label
    // identical to a group already on screen.
    expect(screen.getByText("Round 2")).toBeInTheDocument();
    expect(screen.getByText("Which layer owns retries?")).toBeInTheDocument();
    // The ceiling, which lived only in the charter: a review asks at most twice.
    expect(screen.getByText(/at most twice/)).toBeInTheDocument();
  });

  it("does not say a review is judging again when concluding it judged nothing", async () => {
    // "Conclude with remaining uncertainty" seals: `_after_case_revision` routes a
    // `stop_requested` round to `seal_case`, so `select_candidates_for_rejudgement` never
    // runs and not one candidate is judged again. The run is listed all the same, so the card
    // said every candidate was being judged directly above a progress panel correctly reading
    // "Writing this review's case revision" — two sentences about one run, one of them false.
    const review = reviewFixture({ answerable: false });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence,
        // What a sealing run reports: `_after_case_revision` sends a stopped round straight
        // to `seal_case`, so no candidate is selected and none of the judging stages is ever
        // entered.
        candidates_to_judge: 0,
        candidates_judged: 0,
        stage: "seal_case",
        stages: ["load_context", "await_answers", "revise_case", "seal_case"],
      }),
    ]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByText(/Round 1 answered/)).toBeInTheDocument();
    expect(screen.queryByText(/being judged again/)).not.toBeInTheDocument();
    // `/Judging .* again/` was too loose: it let "Judging again." through, which is exactly
    // the assumed sentence this test exists to forbid.
    expect(screen.queryByText(/Judging/)).not.toBeInTheDocument();
    // It says what the run says it is doing — as does the rail entry beside it, which is the
    // agreement that was missing: the note and the progress panel used to contradict.
    expect(
      (await screen.findAllByText(/Writing this review's case revision/)).length,
    ).toBeGreaterThan(0);
  });

  it("says what became of a review without claiming what it is doing now", async () => {
    // A snapshot that asked says `awaiting_answers` for ever, so reading the successor's
    // status as a present state — "is waiting on that round" — is the same mistake one level
    // along: it is true only until that round is answered, and false for ever after.
    const review = reviewFixture({
      answerable: false,
      superseded_by: "review-9",
      superseded_by_status: "awaiting_answers",
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByText(/asked again since/)).toBeInTheDocument();
    expect(screen.queryByText(/is waiting on that round/)).not.toBeInTheDocument();
  });

  it("does not tell a review that failed after being answered that nobody was asked", async () => {
    // A review can fail *after* a round has been asked and answered: `revise_case` puts the
    // answers on the case, and a raise anywhere downstream files a failed snapshot carrying
    // them. The footnote read off `status` alone and said the uncertainty was never put to
    // anyone, in the same line as the answer count that contradicts it.
    const review = reviewFixture({
      status: "failed",
      failure: "The provider stopped",
      round: 2,
      answerable: false,
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();
    const row = rows().find((item) => item.dataset.candidate === "candidate-1");
    if (row?.getAttribute("aria-expanded") === "false") fireEvent.click(row);

    expect(screen.queryByText(/never put to anyone/)).not.toBeInTheDocument();
    expect(screen.getByText(/had already asked a round/)).toBeInTheDocument();
  });

  it("does not claim a review settled everything while it is still holding a hinge", async () => {
    // A question generator that cannot phrase a hinge degrades to no questions at all, and
    // `_after_questions` seals on that — so a review completes with held findings and nothing
    // asked. `docs/known-defects.md` carries this exact case; the empty state was asserting
    // its opposite, a few pixels under a head counting the held candidate.
    const review = reviewFixture({ status: "completed", questions: [], answerable: false });
    review.case.answers = [];
    expect(review.findings.some((finding) => finding.hinge)).toBe(true);
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    expect(
      screen.queryByText(/settled every candidate on the evidence/),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText(/uncertainty that never became a question/),
    ).toBeInTheDocument();
  });

  it("keeps the answered round on the keyboard walk it is still listed on", async () => {
    // The card is rendered on `waiting || rejudging` and the docket opens it in both, but the
    // walk listed it only while waiting. With the round answered, `indexOf("clarification")`
    // was -1, so ArrowUp took the nothing-is-open branch and jumped to the bottom of the list.
    const review = reviewFixture({ answerable: false });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({
        branch_id: review.repository.branch_id,
        case_id: review.case.id,
        sequence: review.sequence,
      }),
    ]);

    render(wrap(<ReviewPage />));
    expect(await screen.findByText(/Round 1 answered/)).toBeInTheDocument();

    // Upward is the direction that showed it. The round is the open row, so there is nothing
    // above it and `k` should do nothing. Unlisted, `indexOf` answered -1, the walk read that
    // as "nothing is open", and the cursor jumped to the last finding on the docket.
    fireEvent.keyDown(document, { key: "k" });
    expect(rows().map((row) => row.getAttribute("aria-expanded"))).not.toContain("true");

    // And downward still steps off it onto the first finding.
    fireEvent.keyDown(document, { key: "j" });
    expect(rows()[0].getAttribute("aria-expanded")).toBe("true");
  });

  it("does not tell a failed review it settled everything on the evidence", async () => {
    // `_record_failure` files its snapshot with no questions, so a failed review reaches the
    // empty state. It asked nothing because it stopped, not because nothing needed asking.
    const review = reviewFixture({
      status: "failed",
      failure: "The provider stopped",
      questions: [],
      answerable: false,
    });
    review.case.answers = [];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    expect(await screen.findByText(/Nothing has been asked/)).toBeInTheDocument();
    expect(
      screen.queryByText(/settled every candidate on the evidence/),
    ).not.toBeInTheDocument();
  });

  it("presents the rounds as the case's history, not as this review's", async () => {
    // A case carries its answers forward across revisions — a second review of the same
    // repository continues the branch's newest case — so this list holds rounds that belong
    // to the reviews that asked them. Calling it "every round this review has been through"
    // put "3 rounds" directly above its own sentence saying a review asks at most twice, with
    // the list on screen contradicting it.
    const review = reviewFixture();
    const asked = review.questions[0];
    review.case.revision = 1;
    review.case.answers = [
      {
        question: { ...asked, id: "q-r1-a", text: "Who owned it before?", round: 1 },
        status: "answered",
        value: "The domain did",
        actor: "furkan",
        answered_at: "2026-01-01T00:00:00Z",
        case_revision: 1,
      },
      {
        question: { ...asked, id: "q-r2-a", text: "And the retries?", round: 2 },
        status: "answered",
        value: "The adapter owns them",
        actor: "furkan",
        answered_at: "2026-01-01T00:00:00Z",
        case_revision: 1,
      },
    ];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    fireEvent.click(await screen.findByRole("tab", { name: /Rounds/ }));

    // Three rounds on one case, and the sentence beside the count no longer contradicts it.
    expect(await screen.findByText(/3 rounds of questions on this case/)).toBeInTheDocument();
    expect(screen.getByText(/A review asks at most twice/)).toBeInTheDocument();
    // And the open round does not repeat a header already on screen: it has opened no
    // revision, so it is labelled by its round alone.
    expect(screen.getAllByText("Round 1 · case revision 1")).toHaveLength(1);
    expect(screen.getByText("Round 1")).toBeInTheDocument();
  });

  it("says when a snapshot has been replaced, and points at the one that replaced it", async () => {
    // A revision is recorded once per round it waits in and once more when it finishes, and
    // the listing keeps only the newest. That left the earlier records reachable by a URL
    // somebody was holding and by nothing else: a review waiting on questions answered an
    // hour before, over a report composed before the answers existed, with nothing saying so.
    const review = reviewFixture({ answerable: false, superseded_by: "review-9" });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(
      await screen.findByText(/This is an earlier record of review 1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/its report are all that moment/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read the current record/ })).toHaveAttribute(
      "href",
      "/reviews/review-9",
    );
  });

  it("leaves the rail alone when the run in flight belongs to another case", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({ case_id: "some-other-case" }),
    ]);

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
    review.investigation_manifest = [
      investigationFixture({ candidate_id: "candidate-1" }),
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
    // The closed state names the count and what came of it, because a fold that says only
    // "Looked up" makes a reader open it to find out whether it was worth opening.
    // The closed state says how much looking there was and how it ended — not whether the
    // hinge was settled, which is the finding's business and not the transcript's.
    expect(
      within(article).getByText("2 lookups · the pass stopped looking"),
    ).toBeInTheDocument();
    // The transcript is in the DOM and folded, like the provenance beside it.
    expect(
      within(article).getByText(/asked what implementations billing.gateway.PersistenceGateway/),
    ).not.toBeVisible();
    fireEvent.click(within(article).getByText("Looked up"));
    expect(
      within(article).getByText(/asked what implementations billing.gateway.PersistenceGateway/),
    ).toBeVisible();
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
        termination: null,
        withheld:
          "This repository has changed since the review ran; index it again.",
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
    expect(
      within(article).getByText("nothing could be looked up"),
    ).toBeInTheDocument();
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

  it("fills the progress strip by proportion, not by counting segments", async () => {
    // The strip is capped at 24 marks and the fill compared a mark's *index* against the raw
    // settled count, so any review larger than the strip read as finished the moment 24
    // things were settled. It is the first thing on the docket, on exactly the reviews where
    // knowing how far through you are matters most.
    const review = wideReview(30, 12);
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();

    const marks = progress();
    expect(marks.total).toBe(24);
    // Twelve of thirty, drawn on a scale of twenty-four. The old arithmetic filled twelve of
    // twenty-four, which is half the strip for 40% of the work — and every mark at 24.
    expect(marks.filled).toBe(Math.round((12 / 30) * 24));
    expect(marks.filled).toBeLessThan(marks.total);
    // The sentence beside it is exact whatever the strip rounds to.
    expect(screen.getByText(/settled$/)).toHaveTextContent("12 of 30 settled");
  });

  it("marks the review worked through in the session that worked through it", async () => {
    // `WorkedThrough` rendered only when the list was empty, and the list deliberately keeps
    // every row that settled under you — so deciding the last outstanding candidate left it
    // non-empty and the one moment in the product worth marking was skipped in the very
    // session that earned it. You got a list of settled rows and silence.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    recordDecisions(review);

    render(wrap(<ReviewPage />));

    await docket();
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));
    await waitFor(() => expect(rows()[1]).toHaveAttribute("aria-expanded", "true"));
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));

    const marked = await screen.findByText("Worked through");
    // Above the rows it is about, which are still listed: they are what it counts.
    expect(rows()).toHaveLength(2);
    expect(
      marked.compareDocumentPosition(rows()[0]) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps a clarification's answers through the gestures that unmount the round", async () => {
    // The round's answers were state inside a component rendered as `{open ? <round/> : null}`
    // inside a card on a docket — so collapsing the card, pressing `j`, and reading another
    // surface each wiped every answer typed into it. "Never navigate away from unsaved input."
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(
      await screen.findByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
      }),
    );
    /**
     * The answer, in whichever of its two shapes the round happens to be showing.
     *
     * A question that is open shows it as the option that is chosen; one that is closed shows
     * it as the answer on the row, which is the shape the doc asks a settled question to take.
     * Both are the answer still being there, which is the claim.
     */
    const held = () =>
      screen.queryByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
        checked: true,
      }) ??
      screen.queryByRole("button", {
        name: /Who owns persistence\? — answered: The domain owns it/,
      });
    expect(held()).toBeInTheDocument();

    // Collapsing the card that holds the round.
    const card = screen.getByRole("button", { name: /1 question wants an answer/ });
    fireEvent.click(card);
    fireEvent.click(card);
    expect(held()).toBeInTheDocument();

    // Walking the docket, which closes the round and opens a finding.
    fireEvent.keyDown(document.body, { key: "j" });
    expect(screen.queryByText("Who owns persistence?")).not.toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "k" });
    expect(held()).toBeInTheDocument();

    // And reading another surface, which unmounts the whole docket.
    fireEvent.click(screen.getByRole("tab", { name: /Delta/ }));
    fireEvent.click(screen.getByRole("tab", { name: /Docket/ }));
    expect(held()).toBeInTheDocument();

    // Reopening the question hands back what was chosen, rather than a blank menu.
    fireEvent.click(held()!);
    expect(
      screen.getByRole("radio", {
        name: "The domain owns it and adapters implement its ports",
        checked: true,
      }),
    ).toBeInTheDocument();
  });

  it("walks the list from the keyboard when focus is nowhere near it", async () => {
    // The walk keys were a React `onKeyDown` on the docket's own div, so they only fired
    // while focus was inside it — and recording a decision unmounts the button that was
    // pressed, dropping focus on `<body>`. `A` went on working and `j` did not, which is a
    // half-dead keyboard with nothing on screen to explain it.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const listed = await docket();
    expect(listed[0]).toHaveAttribute("aria-expanded", "true");

    document.body.focus();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(rows()[1]).toHaveAttribute("aria-expanded", "true");

    // And Escape closes what is open, which is the only key on the docket that was missing.
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(rows()[1]).toHaveAttribute("aria-expanded", "false");
  });

  it("carries the keyboard to the row it opened, the way the round does", async () => {
    // The docket's twin of "carries the keyboard to the question it opened". The control
    // that was pressed unmounts with its row, so focus fell to `<body>` and the next Tab
    // restarted at "Skip to content" — while the newly opened row was scrolled into view.
    // The visual cursor and the keyboard cursor were in two different places, on the one
    // surface `docs/experience.md` says is worked from the keyboard.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const recorded: Decision[] = [];
    vi.spyOn(api, "decisions").mockImplementation(async () => ({
      branch_id: "branch-1",
      decisions: [...recorded],
    }));
    vi.spyOn(api, "decide").mockImplementation(async (_review, candidateId) => {
      const judged = review.findings.find((item) => item.candidate.id === candidateId)!;
      const decision: Decision = {
        id: `decision-${candidateId}`,
        branch_id: "branch-1",
        candidate_id: candidateId,
        disposition: "accept",
        author: "user",
        reasoning: null,
        decided_at: "2026-01-01T00:00:00Z",
        review_id: "review-1",
        finding_verdict: judged.verdict,
        finding_model_identity: "fake:deterministic",
        finding_prompt_identity: "judge:v1",
        finding_retrieval_identity: "retrieval-1",
      };
      recorded.push(decision);
      return decision;
    });

    render(wrap(<ReviewPage />));

    const [first, second] = await docket();
    expect(first).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));

    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-candidate",
        second.dataset.candidate!,
      ),
    );
    expect(document.activeElement).toHaveAttribute("aria-expanded", "true");
  });

  it("says what was recorded when a decision is changed rather than taken", async () => {
    // The docket's live region fires on the transition into settled, which a row that was
    // already settled never makes. This bar's own region was `{success ? <LiveRegion/> : null}`
    // — created in the same DOM mutation as its text, which is the shape three other files
    // in this repository name as the one a screen reader does not read.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const existing: Decision = {
      id: "decision-1",
      branch_id: "branch-1",
      candidate_id: "candidate-1",
      disposition: "accept",
      author: "user",
      reasoning: null,
      decided_at: "2026-01-01T00:00:00Z",
      review_id: "review-1",
      finding_verdict: "held",
      finding_model_identity: "fake:deterministic",
      finding_prompt_identity: "judge:v1",
      finding_retrieval_identity: "retrieval-1",
    };
    vi.spyOn(api, "decisions").mockResolvedValue({
      branch_id: "branch-1",
      decisions: [existing],
    });
    vi.spyOn(api, "decide").mockResolvedValue({ ...existing, disposition: "park" });

    const { container } = render(wrap(<ReviewPage />));
    await docket();
    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    const row = rows().find((item) => item.dataset.candidate === "candidate-1")!;
    if (row.getAttribute("aria-expanded") === "false") fireEvent.click(row);

    // The region has to be on screen *before* the decision, or it is the shape being fixed.
    const regions = () => container.querySelectorAll("[aria-live]").length;
    const before = regions();
    expect(before).toBeGreaterThan(0);

    fireEvent.click(await screen.findByRole("button", { name: "Park" }));
    expect(await screen.findByText("Parked recorded.")).toBeInTheDocument();
    expect(regions()).toBe(before);
  });

  it("leaves a half-written waiver alone when the docket's keys are pressed beside it", async () => {
    // Escape from one Tab past the reason box closed the whole row. `DecisionBar` unmounts
    // with it and the reason is component state, so the sentence went with no warning and
    // nothing to undo it with — `docs/experience.md`, never navigate away from unsaved input,
    // broken by the key the shortcut sheet advertises as "close what is open". `j` walks off
    // the row just as destructively and was never reported.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const listed = await docket();
    expect(listed[0]).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("button", { name: "Waive" }));
    const reason = screen.getByLabelText("Why the team waives this");
    fireEvent.change(reason, { target: { value: "The team owns this deliberately." } });

    // Focus is on the button after the textarea, which is where the reveal's own handler
    // stops applying and the document-bound one takes over.
    screen.getByRole("button", { name: /Record waiver/ }).focus();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(rows()[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Why the team waives this")).toHaveValue(
      "The team owns this deliberately.",
    );

    fireEvent.keyDown(document, { key: "j" });
    expect(rows()[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Why the team waives this")).toHaveValue(
      "The team owns this deliberately.",
    );

    // And `A` does not record an accept out from under it either.
    const decide = vi.spyOn(api, "decide");
    fireEvent.keyDown(document, { key: "A" });
    expect(decide).not.toHaveBeenCalled();
  });

  it("does not claim a cancelled round was concluded", async () => {
    // One ternary answered two questions — is there a question naming this candidate on an
    // `awaiting_answers` review — and every no printed "the round was concluded with the
    // uncertainty preserved". `cancel()` keeps every question, so on a cancelled review both
    // clauses were false at once: there is an open question covering it, and nothing was
    // concluded.
    const review = reviewFixture({ status: "cancelled" });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();
    // The held candidate the round's one question names. A row that is not open renders no
    // footnote at all, and a test that asserts on an absent sentence proves nothing.
    const row = rows().find((item) => item.dataset.candidate === "candidate-1");
    if (row?.getAttribute("aria-expanded") === "false") fireEvent.click(row);

    expect(screen.queryByText(/round was concluded/)).not.toBeInTheDocument();
    expect(screen.getByText(/cancelled before the question was answered/)).toBeInTheDocument();
  });

  it("does not tell a superseded record that nothing was asked about this candidate", async () => {
    // The footnote branched on `status`, and a snapshot is immutable — so a record that had
    // asked said `awaiting_answers` for ever. On a superseded one it therefore claimed no
    // question had been asked about a candidate whose question is rendered directly above it,
    // and offered to answer a round `_resume_command` refuses. Both clauses false at once,
    // which is the exact failure this footnote was written to stop making.
    const review = reviewFixture({ answerable: false, superseded_by: "review-9" });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();
    const row = rows().find((item) => item.dataset.candidate === "candidate-1");
    if (row?.getAttribute("aria-expanded") === "false") fireEvent.click(row);

    expect(screen.queryByText(/No question was asked about this candidate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/round was concluded/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/what became of it is on the record that replaced this one/),
    ).toBeInTheDocument();
    // And no offer to answer a round the server would refuse.
    expect(screen.queryByRole("button", { name: /Answer the open question/ })).not.toBeInTheDocument();
  });

  it("says a failed review never put the question, rather than that it decided not to", async () => {
    const review = reviewFixture({ status: "failed", failure: "The provider stopped" });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();
    // The held candidate the round's one question names. A row that is not open renders no
    // footnote at all, and a test that asserts on an absent sentence proves nothing.
    const row = rows().find((item) => item.dataset.candidate === "candidate-1");
    if (row?.getAttribute("aria-expanded") === "false") fireEvent.click(row);

    expect(screen.queryByText(/round was concluded/)).not.toBeInTheDocument();
    expect(screen.getByText(/did not finish, so the uncertainty was never put/)).toBeInTheDocument();
  });

  it("says answering judges every candidate again, which is what the backend does", async () => {
    // Four surfaces said "re-judges what it touches" or "the affected candidates".
    // `select_rejudgements_node` returns `state["candidates"]` — all of them — because an
    // answer is about intent and intent bears on every candidate. Understating that
    // understates what pressing the button costs.
    const review = reviewFixture();
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();

    expect(screen.queryByText(/re-judges what it touches/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/judges every candidate again/).length).toBeGreaterThan(0);
  });

  it("does not teach a keyboard to a screen that has none", async () => {
    // The hints were gated on nothing at all, so a phone got eleven key caps and four verbs
    // as the densest thing above the list, describing keys that are not there. Gated on the
    // input rather than on the width: a laptop window dragged narrow still has a keyboard.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    setHasKeyboard(false);
    render(wrap(<ReviewPage />));
    await docket();

    expect(screen.queryByText("walk")).not.toBeInTheDocument();
    expect(screen.queryByText("all keys")).not.toBeInTheDocument();
    // The decisions themselves stay — it is the caps on them that go.
    expect(screen.getByRole("button", { name: "Accept and act" })).toBeInTheDocument();
  });

  it("settles a row before the request comes back, and says what happened", async () => {
    // A decision used to be two blocking round trips — the POST, then a refetch of every
    // standing decision on the branch — with three buttons fading to 45% as the only signal.
    // Pressed from the keyboard while scrolled away there was no signal at all.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const branch = vi.spyOn(api, "decisions").mockResolvedValue({
      branch_id: "branch-1",
      decisions: [],
    });
    // Never answers, so everything asserted below happens while the request is still open.
    vi.spyOn(api, "decide").mockImplementation(() => new Promise(() => {}));

    render(wrap(<ReviewPage />));

    await docket();
    const reads = branch.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));

    await waitFor(() =>
      expect(rows()[0].textContent).toContain("Accepted by the team"),
    );
    // And the cursor has moved on, which is the other half of what a reader has to be told.
    expect(rows()[1]).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText(/^Accepted\. Now on domain\.orders, held\.$/),
    ).toBeInTheDocument();
    // Nothing was re-read to learn one row.
    expect(branch.mock.calls.length).toBe(reads);
  });

  it("takes a decision back when the request refuses it", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "decide").mockRejectedValue(new Error("The workspace is not answering"));

    render(wrap(<ReviewPage />));

    await docket();
    fireEvent.click(screen.getByRole("button", { name: "Accept and act" }));

    // The row returns to the attention filter, because nothing was recorded...
    await screen.findByRole("alert");
    expect(rows()[0].textContent).not.toContain("Accepted by the team");
    // ...and the failure says so where the reader is, with the way to try it again.
    expect(
      screen.getByRole("button", { name: "Record it again" }),
    ).toBeInTheDocument();
  });

  it("opens the finding a link names, and never writes one as you walk", async () => {
    // `?tab=` is in the URL by design and the open row is page state, also by design. That
    // reasoning is about walking the list; it does not cover handing a colleague one finding,
    // which without this means "open review 4, set the filter to All, and scroll to it".
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />, "/reviews/review-1?candidate=candidate-3"));

    // candidate-3 is cleared, so the default Attention filter would have hidden it.
    await docket();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Settled/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    const named = rows().find((row) => row.dataset.candidate === "candidate-3")!;
    expect(named).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: "Copy link to this finding" }),
    ).toBeInTheDocument();

    // Walking away from it does not rewrite the parameter — a link that followed the cursor
    // would put an entry in the reader's history for every row they open.
    fireEvent.keyDown(document.body, { key: "j" });
    expect(screen.getByTestId("path")).toHaveTextContent(
      "/reviews/review-1?candidate=candidate-3",
    );
  });

  it("keeps the verdict word on a settled row, and withdraws only the hue", async () => {
    // Under the Settled filter — the surface for "what did we decide, and about what" — a
    // waived material finding was visually identical to a cleared one: the word was dropped,
    // the glyph greyed and the edge made transparent. A verdict is a glyph, a word and a hue.
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

    fireEvent.click(await screen.findByRole("button", { name: /^Settled 2/ }));
    const waived = (await docket()).find(
      (row) => row.dataset.candidate === "candidate-2",
    )!;
    expect(waived.textContent).toContain("Material");
    expect(waived.textContent).toContain("Waived by the team");
    // The word, in the settled ink rather than in the verdict's own hue.
    const word = within(waived).getByText("Material");
    expect(word.className).toContain("text-ink-3");
    expect(word.className).not.toContain("text-material");
  });

  it("decides a run of candidates at once, and refuses to waive them that way", async () => {
    // `/api/decisions/bulk` and `decide_many` have existed all along and had never been
    // called. The doc's blocker is real and narrower than it looks: a reason that fits twelve
    // findings is usually not a reason — which is an argument about waiving and nothing else.
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    const bulk = vi.spyOn(api, "decideMany").mockResolvedValue({
      recorded: 2,
      decisions: [],
    });

    render(wrap(<ReviewPage />));

    const listed = await docket();
    // The open row from the keyboard, and the other one with its box.
    fireEvent.keyDown(document.body, { key: "x" });
    fireEvent.click(screen.getAllByRole("checkbox")[1]);

    expect(await screen.findByText("2 candidates selected")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Waive all/ }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accept all" }));
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith(
        "review-1",
        [listed[0].dataset.candidate, listed[1].dataset.candidate],
        "accept",
      ),
    );
  });

  it("finds a candidate by name, and groups a first review by what it detected", async () => {
    // Three filters was the whole of the navigation on a review of any size, and none of them
    // is "the one about SqlAlchemy". The grouping is the other half: a first review has no
    // movement to group on and always has a pattern, which is the machine-measured fact the
    // experience doc names as the way out of a first-review wall.
    const review = wideReview(10, 0);
    review.findings.forEach((finding, index) => {
      finding.candidate.pattern = index < 4 ? "dependency_direction" : "sole_implementation";
    });
    review.findings[7].candidate.participants = [
      { qualified_name: "domain.orders.InvoiceGateway", role: "source", node_id: null },
    ];
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();

    // No predecessor, so the groups are the patterns rather than what moved — and two lists
    // called the same thing are one list to anything reading the page, so each names itself.
    expect(
      screen.getByRole("list", { name: "Candidates dependency direction" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Candidates sole implementation" }),
    ).toBeInTheDocument();

    const box = screen.getByRole("searchbox", {
      name: "Find a candidate in this review",
    });
    fireEvent.change(box, { target: { value: "invoicegateway" } });

    const found = rows();
    expect(found).toHaveLength(1);
    expect(found[0].dataset.candidate).toBe(review.findings[7].candidate.id);
    // A count on the control that produced it, rather than a number nobody can act on.
    expect(box.parentElement).toHaveTextContent("1 of 10");
    // One row is not a wall, so it is not grouped into headings of one either.
    expect(
      screen.queryByRole("list", { name: "Candidates sole implementation" }),
    ).not.toBeInTheDocument();
  });

  it("reads the delta once for the whole list rather than once per comparison", async () => {
    // `orderedFindings`' comparator called `movedSincePrevious`, which walked all three delta
    // arrays — three linear scans inside a sort, on a 35KB delta. Neither call site memoised
    // it, so the head's counts and the docket each re-sorted the whole review on every render
    // of the page: every keystroke, every filter press and every four-second run poll.
    const review = wideReview(16, 4);
    let reads = 0;
    const delta = review.delta;
    Object.defineProperty(review, "delta", {
      get() {
        reads += 1;
        return delta;
      },
    });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));
    await docket();

    // Once for the order and once for the rows' own delta states. The comparator alone used
    // to reach three figures on a list this size.
    const settled = reads;
    expect(settled).toBeLessThan(8);

    // And re-rendering the page does not ask again: the sort is the page's, and both the
    // counts in the head and the docket read the one answer.
    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Attention/ }));
    fireEvent.keyDown(document.body, { key: "j" });
    expect(reads).toBe(settled);
  });
});

/**
 * Which document about the review is on screen is part of where you are, not part of what
 * the page happens to remember. A tab held only in memory cannot be refreshed onto, linked
 * to, or opened in a second window beside the first.
 */
describe("the surface in the URL", () => {
  beforeEach(() => {
    const review = reviewFixture({ status: "completed" });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
  });

  it("opens on the surface the link names", async () => {
    render(wrap(<ReviewPage />, "/reviews/review-1?tab=delta"));

    expect(await screen.findByRole("tab", { name: /Delta/, selected: true })).toBeInTheDocument();
  });

  it("opens on the docket for a bare review link, and leaves the link bare", async () => {
    // No redirect on mount: the docket is what a review *is*, so saying so in the URL would
    // put a second entry in the reader's history for every review they open.
    render(wrap(<ReviewPage />, "/reviews/review-1"));

    expect(await screen.findByRole("tab", { name: /Docket/, selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("path")).toHaveTextContent("/reviews/review-1");
  });

  it("shows the review rather than nothing when the parameter names no surface", async () => {
    // A mistyped link still asked for this review. The tab strip says where they landed.
    render(wrap(<ReviewPage />, "/reviews/review-1?tab=atals"));

    expect(await screen.findByRole("tab", { name: /Docket/, selected: true })).toBeInTheDocument();
  });

  it("keeps the reader's place in the docket across a trip to another surface", async () => {
    // The surface is where you are; the open row, the filter and the scroll are what you were
    // doing there. Putting the first in the URL must not cost the second — which it does the
    // moment the page is remounted, and a route whose shape changes between two URLs remounts
    // it. This is the test that catches that, because nothing about the URL looks wrong.
    render(wrap(<ReviewPage />, "/reviews/review-1"));

    const listed = await docket();
    fireEvent.click(listed[1]);
    expect(listed[1]).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("tab", { name: /Delta/ }));
    await screen.findByRole("tab", { name: /Delta/, selected: true });
    fireEvent.click(screen.getByRole("tab", { name: /Docket/ }));
    await screen.findByRole("tab", { name: /Docket/, selected: true });

    const after = rows().find((row) => row.dataset.candidate === listed[1].dataset.candidate);
    expect(after).toHaveAttribute("aria-expanded", "true");
  });

  it("puts the surface in the URL when a tab is chosen", async () => {
    render(wrap(<ReviewPage />, "/reviews/review-1"));

    fireEvent.click(await screen.findByRole("tab", { name: /Report/ }));

    expect(await screen.findByRole("tab", { name: /Report/, selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("path")).toHaveTextContent("/reviews/review-1?tab=report");
  });
});
