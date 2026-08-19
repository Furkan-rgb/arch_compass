import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { coreApi } from "../../api";
import { VIEWPORT, setViewportWidth } from "../../test-setup";
import { reviewFixture } from "../../test-fixtures";
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
  vi.spyOn(coreApi, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
  setViewportWidth(VIEWPORT.desktop);
});

describe("the review workbench", () => {
  it("opens on the clarification when the review is waiting for a human", async () => {
    const review = reviewFixture();
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByText("The repository cannot answer these")).toBeInTheDocument();
    expect(screen.getByText("Who owns persistence?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Answer 1/ })).toBeInTheDocument();
  });

  it("orders the queue by what needs a human, cleared findings last", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

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

  it("shows the selected finding as a structured assessment, with provenance behind a disclosure", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    const heading = await screen.findByRole("heading", {
      name: "The provider abstraction carries one implementation",
    });
    const article = heading.closest("article")!;
    expect(within(article).getByText("Why this matters")).toBeInTheDocument();
    expect(within(article).getByText(/Recommended response/)).toBeInTheDocument();
    expect(within(article).getByText(/Dependencies point inward/)).toBeInTheDocument();
    expect(within(article).getByText("from adapters.db import Store")).toBeInTheDocument();

    // Model, prompt and retrieval identity are real, but they are not the argument.
    expect(within(article).queryByText("judge:v1")).not.toBeInTheDocument();
    fireEvent.click(within(article).getByRole("button", { name: /Technical detail/ }));
    expect(await within(article).findByText("judge:v1")).toBeInTheDocument();
  });

  it("keeps the standing decision separate from the model's verdict", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);
    const decide = vi.spyOn(coreApi, "decide").mockResolvedValue({
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

    expect(await screen.findByText(/ArchCompass does not decide this/)).toBeInTheDocument();
    // Waiving without a reason is refused by the form itself, not by the server.
    expect(screen.getByRole("button", { name: "Waive" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Accept the work" }));
    await waitFor(() =>
      expect(decide).toHaveBeenCalledWith("review-1", "candidate-2", "accept", null),
    );
  });

  it("records an explicit skip and resumes by review identity", async () => {
    const review = reviewFixture();
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(coreApi, "answer")
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
    const review = reviewFixture();
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);
    const answer = vi
      .spyOn(coreApi, "answer")
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

  it("exposes retrieval provenance on its own surface", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Retrieval/ }));
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", "tab-retrieval");
    expect(within(panel).getByText(/dense-scoped/)).toBeInTheDocument();
    expect(within(panel).getByText("corpus-fingerprint")).toBeInTheDocument();
    expect(within(panel).getByText("ollama:nomic-embed-text")).toBeInTheDocument();
  });

  it("moves the queue and the context into drawers on a phone", async () => {
    setViewportWidth(VIEWPORT.phone);
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

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
    vi.spyOn(coreApi, "review").mockResolvedValue(review);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([review]);

    render(wrap(<ReviewPage />));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The embedding provider was unreachable",
    );
    expect(screen.getByText("Domain depends on an adapter")).toBeInTheDocument();
  });
});
