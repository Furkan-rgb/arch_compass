import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QuestionsPanel } from "./components/questions-panel";
import { RevisionRail } from "./components/revision-rail";
import { coreApi } from "./api";
import { ReviewPage } from "./pages/ReviewPage";
import { reviewFixture } from "./test-fixtures";

function queryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

afterEach(() => vi.restoreAllMocks());

describe("clean-break review workbench", () => {
  it("shows immutable review lineage with the current revision selected", () => {
    const current = reviewFixture({ id: "review-2", sequence: 2, previous_review_id: "review-1" });
    render(<MemoryRouter><RevisionRail current={current} reviews={[reviewFixture(), current]} /></MemoryRouter>);
    expect(screen.getByText("Review 1")).toBeInTheDocument();
    expect(screen.getByText("Review 2").closest("a")).toHaveClass("ring-1");
  });

  it("records explicit skips and resumes by review identity", async () => {
    const waiting = reviewFixture();
    const answer = vi.spyOn(coreApi, "answer").mockResolvedValue(reviewFixture({ id: "review-2", status: "completed", questions: [] }));
    render(<QueryClientProvider client={queryClient()}><MemoryRouter><QuestionsPanel review={waiting} /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Skip explicitly"));
    expect(screen.getByText("1/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save and continue review" }));
    await waitFor(() => expect(answer).toHaveBeenCalledWith("review-1", [{ question_id: "question-1", status: "skipped", value: null }], false));
  });

  it("exposes findings, evidence, retrieval audit, and waiting state from one review", async () => {
    const waiting = reviewFixture();
    vi.spyOn(coreApi, "review").mockResolvedValue(waiting);
    vi.spyOn(coreApi, "reviews").mockResolvedValue([waiting]);
    render(<QueryClientProvider client={queryClient()}><MemoryRouter initialEntries={["/reviews/review-1"]}><Routes><Route path="/reviews/:reviewId" element={<ReviewPage />} /></Routes></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText("The code cannot answer these")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Retrieval/ }));
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "tab-provenance");
    expect(await screen.findByText(/dense-scoped/)).toBeInTheDocument();
    expect(screen.getByText(/dependency-direction/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Findings/ }));
    expect(await screen.findByText("Domain depends on an adapter")).toBeInTheDocument();
    expect(screen.getByText("Import crosses the boundary")).toBeInTheDocument();
  });
});
