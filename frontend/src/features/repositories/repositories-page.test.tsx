import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type RepositorySummary } from "../../api";
import { reviewSummaryFixture } from "../../test-fixtures";
import { ToastProvider } from "../../ui/toast";
import { RepositoriesPage } from "./repositories-page";

function version(overrides: Partial<RepositorySummary> = {}): RepositorySummary {
  return {
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
    ...overrides,
  };
}

/** The address bar, so a test can read what the page put in it. */
function Address() {
  const location = useLocation();
  return <output data-testid="address">{`${location.pathname}${location.search}`}</output>;
}

function wrap(children: ReactNode, at = "/repositories") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[at]}>
          <Address />
          <Routes>
            <Route path="/repositories" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("the repositories page", () => {
  /**
   * The page is handed the index history, not a list of repositories.
   *
   * `GET /api/repositories` is `list_versions` with no `GROUP BY`, and the store inserts a
   * fresh version on every index — so one repository indexed three times arrives as three
   * rows that differ only in when they were built. The real workspace had 65 of these for 7
   * repositories, on a page 14,157px tall.
   */
  it("draws one card per repository, however many atlases have been built of it", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([
      version({ version_id: "v-old", created_at: "2026-01-01T00:00:00Z", node_count: 4 }),
      version({
        version_id: "v-new",
        created_at: new Date(Date.now() - 60_000).toISOString(),
        git_commit_sha: "aa11bb22cc33",
        node_count: 128,
      }),
      version({ version_id: "v-mid", created_at: "2026-02-01T00:00:00Z", node_count: 40 }),
      version({
        version_id: "other",
        root_path: "/work/billing-service",
        repository_identity: "identity-2",
        created_at: "2026-03-01T00:00:00Z",
      }),
    ]);

    render(wrap(<RepositoriesPage />));

    await screen.findByText("payments-platform");
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getAllByText("payments-platform")).toHaveLength(1);

    // The newest version is the one the card describes, and the rest are a count.
    const card = screen.getByText("payments-platform").closest("article")!;
    expect(within(card).getByText("3 snapshots")).toBeInTheDocument();
    expect(within(card).getByText("aa11bb22")).toBeInTheDocument();
    expect(within(card).getByText("128 nodes")).toBeInTheDocument();
  });

  /**
   * The other half of the same defect: the cards were keyed on `version_id` while the
   * selection compared `root_path`, so every duplicate of a repository lit up as selected at
   * once — and the atlas beside them resolved to the newest whichever card was pressed.
   */
  it("selects one repository at a time, and says which in the URL", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([
      version({ version_id: "v-1" }),
      version({ version_id: "v-2", created_at: "2026-01-01T00:00:00Z" }),
      version({
        version_id: "other",
        root_path: "/work/billing-service",
        repository_identity: "identity-2",
        created_at: "2026-03-01T00:00:00Z",
      }),
    ]);

    render(wrap(<RepositoriesPage />));

    const card = (await screen.findByText("billing-service")).closest("article")!;
    fireEvent.click(within(card).getByText("billing-service"));

    await waitFor(() =>
      expect(screen.getByTestId("address")).toHaveTextContent(
        "/repositories?root=%2Fwork%2Fbilling-service",
      ),
    );
  });

  /**
   * The command palette lists every repository and could only ever link to `/repositories`,
   * because the selection had no URL representation. Searching `billing-service` and
   * pressing Enter landed on `payments-platform` selected, which is indistinguishable from
   * the palette not working.
   */
  it("opens on the repository the URL names", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    const hotspots = vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([
      version(),
      version({
        version_id: "other",
        root_path: "/work/billing-service",
        repository_identity: "identity-2",
        created_at: "2026-01-01T00:00:00Z",
      }),
    ]);

    render(
      wrap(<RepositoriesPage />, "/repositories?root=%2Fwork%2Fbilling-service"),
    );

    // The atlas panel beside the list is the whole point of the selection, so it is what the
    // assertion reads: it must be the named repository's, not the newest one's.
    await waitFor(() =>
      expect(hotspots).toHaveBeenCalledWith("/work/billing-service"),
    );
    expect(hotspots).not.toHaveBeenCalledWith("/work/payments-platform");
  });

  it("re-indexes in place, and says what it found", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    const repositories = vi
      .spyOn(api, "repositories")
      .mockResolvedValue([version({ version_id: "v-1" })]);
    const index = vi.spyOn(api, "indexRepository").mockImplementation(async () => {
      // The re-index adds a version rather than replacing one, which is the reason the page
      // collapses at all — the card the reader pressed has to update, not multiply.
      repositories.mockResolvedValue([
        version({ version_id: "v-1" }),
        version({
          version_id: "v-2",
          created_at: new Date().toISOString(),
          git_commit_sha: "cc44dd55ee66",
        }),
      ]);
      return {
        repository_identity: "identity-1",
        root_path: "/work/payments-platform",
        git_commit_sha: "cc44dd55ee66",
        content_fingerprint: "fingerprint",
        parser_version: "1",
        analysis_config_hash: "hash",
      };
    });

    render(wrap(<RepositoriesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Re-index/ }));
    await waitFor(() => expect(index).toHaveBeenCalledWith("/work/payments-platform"));

    // Still one card, now describing the atlas that was just built, and it said so.
    await waitFor(() => expect(screen.getByText("cc44dd55")).toBeInTheDocument());
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("2 snapshots")).toBeInTheDocument();
    expect(await screen.findByText(/Re-indexed payments-platform at cc44dd55/)).toBeInTheDocument();
  });

  /**
   * `CheckoutRefresh.updated` has been on the wire the whole time and nothing read it, so a
   * fetch that pulled thirty commits said exactly as much as one that pulled none — and left
   * the card claiming an atlas that no longer matched the checkout.
   */
  it("says what a fetch pulled, and that the atlas is now behind it", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([version()]);
    vi.spyOn(api, "refreshRepository").mockResolvedValue({
      root_path: "/work/payments-platform",
      managed: true,
      updated: true,
      branch_name: "main",
    });

    render(wrap(<RepositoriesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Fetch/ }));

    expect(await screen.findByText(/Fetched new commits on main/)).toBeInTheDocument();
    const card = screen.getByText("payments-platform").closest("article")!;
    expect(within(card).getByText(/New commits landed since this atlas was built/)).toBeInTheDocument();
    // The freshness badge stops being about the clock the moment there is a better answer.
    expect(within(card).getByText("Atlas behind the checkout")).toBeInTheDocument();
  });

  /**
   * A stale index is not an alarm. `atlasFreshness` used to answer with a verdict tone, and
   * `material` is the one hue in the product — it means the evidence supports a concern worth
   * acting on. It now answers with a step on a scale, which is what a week-old atlas is, and
   * this holds the card to it from the outside: whatever the helper returns, no verdict hue
   * reaches the badge.
   */
  it("states atlas age without spending a verdict's hue on it", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([
      version({ created_at: "2020-01-01T00:00:00Z" }),
    ]);

    render(wrap(<RepositoriesPage />));

    const badge = await screen.findByText("Atlas Stale");
    expect(badge.className).not.toMatch(/material|held|cleared/);
  });

  /**
   * Nodes, edges and signals are three measurements of the atlas and none of them is a
   * number anybody plans around. What a review costs is, and the newest review carries it.
   */
  it("says what a review of this repository costs", async () => {
    vi.spyOn(api, "repositoryHotspots").mockResolvedValue({
      query: { kind: "hotspots", metric: "reverse_dependency_reach" },
      metric_values: [],
      node_summaries: [],
    });
    vi.spyOn(api, "repositories").mockResolvedValue([version()]);
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([
      reviewSummaryFixture({
        finding_count: 34,
        started_at: "2026-01-01T00:00:00Z",
        finished_at: "2026-01-01T00:06:00Z",
      }),
    ]);

    render(wrap(<RepositoriesPage />));

    expect(await screen.findByText("Last review: 34 candidates, 6 minutes")).toBeInTheDocument();
  });

  it("keeps the page when the list fails, and offers the way back", async () => {
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
    const repositories = vi
      .spyOn(api, "repositories")
      .mockRejectedValueOnce(new Error("workspace unreachable"))
      .mockResolvedValue([version()]);

    render(wrap(<RepositoriesPage />));

    expect(await screen.findByText(/workspace unreachable/)).toBeInTheDocument();
    // The header and the clone form are still there, which is the whole complaint about a
    // page that replaces itself with its own error message.
    expect(screen.getByRole("heading", { name: "Repositories" })).toBeInTheDocument();
    expect(screen.getByLabelText("Repository address")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("payments-platform")).toBeInTheDocument();
    expect(repositories).toHaveBeenCalledTimes(2);
  });
});
