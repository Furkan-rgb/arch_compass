import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { coreApi, type ReviewProgress } from "../../api";
import { reviewFixture, workspaceFixture } from "../../test-fixtures";
import { StartPage } from "./start-page";

function wrap(children: ReactNode, entry = "/start") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/start" element={children} />
          <Route path="/reviews/:reviewId" element={<div>Review workbench</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.spyOn(coreApi, "repositories").mockResolvedValue([
    {
      version_id: "version-1",
      repository_identity: "identity-1",
      root_path: "/work/payments-platform",
      git_commit_sha: "8f31c2a91b4d",
      repo_id: "repo-1",
      branch_name: "main",
      created_at: "2026-01-01T00:00:00Z",
      node_count: 128,
      edge_count: 214,
      signal_count: 3,
    },
  ]);
  vi.spyOn(coreApi, "examples").mockResolvedValue([]);
});

afterEach(() => vi.restoreAllMocks());

describe("starting a review", () => {
  it("will not run until both models are chosen, and says which is missing", async () => {
    vi.spyOn(coreApi, "workspace").mockResolvedValue(
      workspaceFixture({
        models: { reasoning: { provider: "fake", model: "deterministic" }, embedding: null },
      }),
    );

    render(wrap(<StartPage />));

    expect(await screen.findByText("not selected")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose models" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("button", { name: /Run review/ })).toBeDisabled();
  });

  it("takes a repository handed over by the repositories page", async () => {
    vi.spyOn(coreApi, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(await screen.findByText("/work/payments-platform")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run review" })).not.toBeDisabled(),
    );
  });

  it("names each stage of the run while it is still running", async () => {
    vi.spyOn(coreApi, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(coreApi, "startRepository").mockResolvedValue({
      case_id: "case-1",
      revision: 1,
      goal: "",
    });
    // The last event is held back, so the run is observed mid-flight rather than after it has
    // already navigated away.
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.spyOn(coreApi, "streamReview").mockImplementation(
      async function* (): AsyncGenerator<ReviewProgress> {
        yield { event: "repository_analyzed" };
        yield { event: "policies_retrieved" };
        await held;
        yield { event: "review_recorded", review: reviewFixture({ id: "review-9" }) };
      },
    );

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    const run = await screen.findByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    const progress = await screen.findByRole("list", { name: "Review progress" });
    await waitFor(() =>
      expect(within(progress).getByText("Relevant policies retrieved")).toBeInTheDocument(),
    );
    expect(within(progress).getByText("Repository analysed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review in progress/ })).toBeDisabled();

    release();
    expect(await screen.findByText("Review workbench")).toBeInTheDocument();
  });

  it("reports a failed run in place rather than navigating away", async () => {
    vi.spyOn(coreApi, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(coreApi, "startRepository").mockRejectedValue(
      new Error("That folder is not a repository"),
    );

    render(wrap(<StartPage />, "/start?root=%2Fnot%2Fa%2Frepository"));

    const run = await screen.findByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    expect(await screen.findByRole("alert")).toHaveTextContent("That folder is not a repository");
    expect(screen.queryByText("Review workbench")).not.toBeInTheDocument();
  });

  it("offers the indexed repositories without making anyone type a path", async () => {
    vi.spyOn(coreApi, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("button", { name: /payments-platform/ }));
    expect(screen.getByText("Selected")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run review" })).not.toBeDisabled(),
    );
  });
});
