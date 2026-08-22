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
  reviewSummaryFixture,
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
    // The card reads a path, a status, a start, a finish and a finding count off the newest
    // review, and every one of those is on the summary — so this page never asks for the
    // reviews themselves.
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([reviewSummaryFixture()]);
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
      policy_context: {},
      answers: [
        {
          question: "Is the single implementation deliberate?",
          status: "answered",
          value: "Yes — a second provider is expected next quarter.",
          actor: "architect",
          answered_at: "2026-01-01T00:00:00Z",
        },
      ],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(api, "cases").mockResolvedValue([{ ...base, revision: 2 }]);
    vi.spyOn(api, "caseHistory").mockResolvedValue([
      { ...base, revision: 1 },
      { ...base, revision: 2 },
    ]);
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([reviewSummaryFixture()]);

    render(wrap(<CasesPage />));

    const history = (await screen.findByText("Revision 1")).closest("ol")!;
    expect(within(history).getByText("Revision 2")).toBeInTheDocument();
    // A revision is what it added, not a restated title — and what it adds is an answer,
    // which is the only way anything reaches a case.
    expect(
      within(history).getAllByText("Yes — a second provider is expected next quarter."),
    ).toHaveLength(2);
  });

  /**
   * F33. `PolicyContext` decides applicability — a non-general policy whose subject does not
   * match the case's user, organisation or repository never enters the mandatory lane — and
   * `domain/case.py` calls it "the one thing here a person still sets directly". Nothing set
   * it, so every scoped policy in the corpus was unreachable.
   */
  it("sets the policy scope, which is the one thing on a case a person states", async () => {
    const base = {
      case_id: "case-1",
      revision: 1,
      answers: [],
      policy_context: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.spyOn(api, "cases").mockResolvedValue([base]);
    vi.spyOn(api, "caseHistory").mockResolvedValue([base]);
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([reviewSummaryFixture()]);
    const rescope = vi
      .spyOn(api, "rescopeCase")
      .mockResolvedValue({ ...base, policy_context: { organisation: "acme" } });

    render(wrap(<CasesPage />));

    expect(
      await screen.findByText("No scope pinned, so only general policies can be retrieved."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set scope" }));

    // Each field says what it does, because a value that is nearly right retrieves nothing.
    expect(
      screen.getByText(/An organisation-scoped policy is retrieved only when its subject/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Organisation"), { target: { value: "acme" } });
    fireEvent.click(screen.getByRole("button", { name: "Save scope" }));

    await waitFor(() =>
      expect(rescope).toHaveBeenCalledWith("case-1", {
        user: null,
        organisation: "acme",
        repository: null,
      }),
    );
  });

  /**
   * F34. The empty state promised "an empty case that reviews will fill in", and
   * `POST /api/repositories/start` picks the case itself — *which case that is, is the
   * application's to decide and not the client's*. A case created here was never selectable
   * and sat in the list for ever labelled "Not yet reviewed".
   */
  it("does not offer to create a case nothing can use", async () => {
    vi.spyOn(api, "cases").mockResolvedValue([]);
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    const create = vi.spyOn(api, "createCase");

    render(wrap(<CasesPage />));

    expect(await screen.findByText("No architecture case yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New case" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a review" })).toHaveAttribute("href", "/start");
    expect(create).not.toHaveBeenCalled();
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

    expect(await screen.findByRole("heading", { name: /Google/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reasoning model" })).toBeInTheDocument();
    expect(screen.getByText("Judges the evidence")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Embedding model" })).toBeInTheDocument();
    expect(screen.getByText("Retrieves the policy")).toBeInTheDocument();

    // A provider that is not reachable cannot be selected, and the reason sits on the
    // section rather than on each tile inside it — said once, where the absence is.
    const unavailable = screen.getByRole("button", { name: /gemini-3.5-flash-lite/ });
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

  /**
   * F15. `is_selected` is computed per candidate from the live probe, so an unreachable
   * provider returns no models, the selected model has no tile, and nothing on the page wears
   * the Selected chip — while the answer sits unrendered in `workspace.models`. The reader
   * saw a page of unmarked tiles and no statement of what the workspace was set to.
   */
  it("says what the workspace is set to when its provider has stopped answering", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(
      workspaceFixture({
        models: {
          ...workspaceFixture().models,
          reasoning: { provider: "ollama", model: "qwen3:8b", thinking: true },
        },
      }),
    );
    vi.mocked(api.models).mockResolvedValue({
      providers: [
        {
          provider: "ollama",
          label: "Ollama",
          available: false,
          detail: "Nothing is listening on http://localhost:11434",
          probed_at: new Date(Date.now() - 40 * 60_000).toISOString(),
        },
      ],
      candidates: [],
    });
    const clear = vi.spyOn(api, "clearModelSelection").mockResolvedValue(undefined);

    render(wrap(<SettingsPage />));

    const identity = await screen.findByText("ollama:qwen3:8b");
    const section = identity.closest("section")!;
    expect(within(section).getByText(/Ollama is not answering/)).toBeInTheDocument();
    expect(within(section).queryByText("Selected")).not.toBeInTheDocument();
    // When the probe ran, which is the difference between "Ollama is off" and "Ollama was
    // off when this page was built".
    expect(within(section).getByText(/checked .* ago/)).toBeInTheDocument();

    // The way back out of a choice that turned out to be wrong, and the state it exists for:
    // there is no tile to click away from.
    fireEvent.click(within(section).getByRole("button", { name: "Clear selection" }));
    await waitFor(() => expect(clear).toHaveBeenCalled());
  });

  it("re-checks the providers without a browser reload", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<SettingsPage />));

    await screen.findByRole("heading", { name: /Groq/ });
    const before = vi.mocked(api.models).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Re-check providers/ }));
    await waitFor(() =>
      expect(vi.mocked(api.models).mock.calls.length).toBeGreaterThan(before),
    );
  });

  it("leads a tile with the variant, and says the model id once", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.mocked(api.models).mockResolvedValue({
      providers: [
        {
          provider: "google",
          label: "Google",
          available: true,
          detail: "",
          probed_at: "2026-01-01T00:00:00Z",
        },
      ],
      candidates: (["minimal", "low", "medium", "high"] as const).map((thinking) => ({
        provider: "google",
        model: "gemini-3.5-flash-lite",
        thinking,
        label: "hosted",
        input_token_limit: 1_048_576,
        output_token_limit: 65_536,
        is_selected: false,
      })),
    });

    render(wrap(<SettingsPage />));

    // Four tiles, one model id. It used to be printed four times in the loudest line of four
    // tiles whose only difference was a small quiet tag.
    expect(await screen.findAllByText("gemini-3.5-flash-lite")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "gemini-3.5-flash-lite high thinking" })).toBeInTheDocument();
    // On the wire since the catalog existed, and never shown.
    expect(screen.getAllByText("context 1,048,576 · output 65,536")).toHaveLength(4);
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
