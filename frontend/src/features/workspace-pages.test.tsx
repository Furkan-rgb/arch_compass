import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import {
  embeddingCatalogFixture,
  modelCatalogFixture,
  reviewFixture,
  runFixture,
  workspaceFixture,
} from "../test-fixtures";
import { CasesPage } from "./cases/cases-page";
import { RepositoriesPage } from "./repositories/repositories-page";
import { ReviewsPage } from "./reviews/reviews-page";
import { SettingsPage } from "./settings/settings-page";

function wrap(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const repository = {
  version_id: "version-1",
  repository_identity: "identity-1",
  root_path: "/work/payments-platform",
  git_commit_sha: "8f31c2a91b4d",
  repo_id: "repo-1",
  branch_name: "main",
  created_at: new Date(Date.now() - 20 * 60_000).toISOString(),
  node_count: 128,
  edge_count: 214,
  signal_count: 3,
};

afterEach(() => vi.restoreAllMocks());

describe("the repositories page", () => {
  beforeEach(() => {
    vi.spyOn(api, "repositories").mockResolvedValue([repository]);
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    vi.spyOn(api, "repositorySummary").mockResolvedValue({
      query: { kind: "repository_summary" },
      summary: "Six packages, one of which owns the payment boundary.",
      node_ids: ["node-1"],
      relationships: [],
      signals: [],
    });
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [
        { node_id: "node-1", metric: "reverse_dependency_reach", value: 12 },
      ],
      node_summaries: [
        {
          node_id: "node-1",
          qualified_name: "payments.gateway",
          node_type: "module",
          path: "payments/gateway.py",
        },
      ],
    });
  });

  it("shows the branch, the commit, atlas freshness and the latest review", async () => {
    render(wrap(<RepositoriesPage />));

    const card = (await screen.findByText("payments-platform")).closest("article")!;
    expect(within(card).getByText("Atlas Fresh")).toBeInTheDocument();
    expect(within(card).getByText("main")).toBeInTheDocument();
    expect(within(card).getByText("8f31c2a9")).toBeInTheDocument();
    expect(within(card).getByText(/indexed .* ago/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Latest review" })).toHaveAttribute(
      "href",
      "/reviews/review-1",
    );
  });

  it("re-indexes a repository in place", async () => {
    const index = vi.spyOn(api, "indexRepository").mockResolvedValue({
      repository_identity: "identity-1",
      root_path: repository.root_path,
      content_fingerprint: "fingerprint",
      parser_version: "1",
      analysis_config_hash: "hash",
    });

    render(wrap(<RepositoriesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Re-index/ }));
    await waitFor(() => expect(index).toHaveBeenCalledWith("/work/payments-platform"));
  });
});

describe("the reviews page", () => {
  it("lists a review that is still being made, so navigating away does not lose it", async () => {
    // A run used to be reachable only by an id somebody was already holding. Batch judging
    // takes as long as a batch takes, which makes "look at something else meanwhile" the
    // ordinary way to use this, not the careless one.
    vi.spyOn(api, "reviews").mockResolvedValue([]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([runFixture()]);

    render(wrap(<ReviewsPage />));

    // Under the line of work it belongs to, not in a separate list of jobs above the
    // history: a run is filed under the same repository, branch and case a review is.
    const lineage = (await screen.findByText("payments-platform")).closest("article")!;
    const entry = within(lineage).getByRole("link");
    expect(entry).toHaveAttribute("href", "/runs/thread-9");
    expect(within(entry).getByText("In progress")).toBeInTheDocument();
    expect(within(entry).getByText(/Judging candidates/)).toBeInTheDocument();
    // A page holding only a run must not also claim there is nothing here.
    expect(screen.queryByText("No reviews yet")).not.toBeInTheDocument();
  });

  it("filters history by status and by search", async () => {
    const base = reviewFixture();
    vi.spyOn(api, "reviews").mockResolvedValue([
      base,
      reviewFixture({
        id: "review-2",
        sequence: 2,
        status: "completed",
        questions: [],
        // A review is identified by the code it reviewed; there is no case title to search.
        repository: { ...base.repository, path: "/work/billing-service" },
      }),
    ]);

    render(wrap(<ReviewsPage />));

    expect(await screen.findByText("billing-service")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Completed" }));
    expect(screen.queryByText("repository")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Search reviews"), { target: { value: "billing" } });
    expect(screen.getByText("billing-service")).toBeInTheDocument();
    expect(
      screen.queryByText("Keep the domain independent of delivery mechanisms"),
    ).not.toBeInTheDocument();
  });

  it("asks before deleting an immutable review", async () => {
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
    const remove = vi.spyOn(api, "deleteReview").mockResolvedValue(undefined);

    render(wrap(<ReviewsPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Delete review 1" }));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("review-1"));
  });
});

describe("the cases page", () => {
  it("shows the case as a sequence of revisions rather than a form", async () => {
    const base = {
      case_id: "case-1",
      constraints: [{ text: "Stripe is the only provider", facet: "constraint" as const }],
      decisions: [],
      policy_context: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(api, "cases").mockResolvedValue([{ ...base, revision: 2 }]);
    vi.spyOn(api, "caseHistory").mockResolvedValue([
      { ...base, revision: 1 },
      { ...base, revision: 2 },
    ]);
    vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);

    render(wrap(<CasesPage />));

    const history = (await screen.findByText("Revision 1")).closest("ol")!;
    expect(within(history).getByText("Revision 2")).toBeInTheDocument();
    // A revision is what it added, not a restated title.
    expect(within(history).getAllByText("Stripe is the only provider")).toHaveLength(2);
  });
});

describe("the models page", () => {
  beforeEach(() => {
    vi.spyOn(api, "models").mockResolvedValue(modelCatalogFixture());
    vi.spyOn(api, "embeddings").mockResolvedValue(embeddingCatalogFixture());
  });

  it("separates architecture judgement from policy retrieval", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<SettingsPage />));

    expect(await screen.findByRole("heading", { name: "Reasoning model" })).toBeInTheDocument();
    expect(screen.getByText("Judges the evidence")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Embedding model" })).toBeInTheDocument();
    expect(screen.getByText("Retrieves the policy")).toBeInTheDocument();

    // A provider that is not reachable cannot be selected, and the reason sits on the
    // section rather than on each tile inside it — said once, where the absence is.
    const unavailable = screen.getByRole("button", { name: /gemini-3.6-flash/ });
    expect(unavailable).toBeDisabled();
    const section = unavailable.closest("section")!;
    expect(within(section).getByRole("heading", { name: /Google/ })).toBeInTheDocument();
    expect(within(section).getByText("Unavailable")).toBeInTheDocument();
  });

  it("selects a reasoning model without touching the embedding selection", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    const select = vi.spyOn(api, "selectModel").mockResolvedValue(workspaceFixture());
    const selectEmbedding = vi.spyOn(api, "selectEmbedding");

    render(wrap(<SettingsPage />));

    fireEvent.click(await screen.findByRole("button", { name: /qwen3:8b/ }));
    await waitFor(() => expect(select).toHaveBeenCalledWith("ollama", "qwen3:8b", true));
    expect(selectEmbedding).not.toHaveBeenCalled();
  });

  it("explains a pinned embedding rather than silently disabling it", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(
      workspaceFixture({
        models: { ...workspaceFixture().models, embedding_pinned: true },
      }),
    );

    render(wrap(<SettingsPage />));

    expect(await screen.findByText(/Pinned by environment configuration/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nomic-embed-text/ })).toBeDisabled();
  });
});
