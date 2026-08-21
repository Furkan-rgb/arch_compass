import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { workspaceFixture } from "../../test-fixtures";
import { StartPage } from "./start-page";

/** Stands in for the run page, and reports the address the start page moved to. */
function RunAddress() {
  const { runId } = useParams();
  return <div>/runs/{runId}</div>;
}

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
          <Route path="/runs/:runId" element={<RunAddress />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.spyOn(api, "repositories").mockResolvedValue([
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
  vi.spyOn(api, "examples").mockResolvedValue([]);
  vi.spyOn(api, "repositoryTree").mockResolvedValue({
    root_path: "/work/payments-platform",
    folders: [
      { path: "src", python_files: 96, python_bytes: 240_000, suggested: false },
      { path: "src/vendor", python_files: 12, python_bytes: 40_000, suggested: false },
      { path: "tests", python_files: 32, python_bytes: 80_000, suggested: true },
    ],
    total_python_files: 128,
    total_python_bytes: 320_000,
  });
});

afterEach(() => vi.restoreAllMocks());

/** The same checkout, indexed three times, which is what testing against one repository does. */
function indexedThreeTimes() {
  return [1, 2, 3].map((n) => ({
    version_id: `version-${n}`,
    repository_identity: "identity-1",
    root_path: "/work/payments-platform",
    git_commit_sha: "8f31c2a91b4d",
    repo_id: "repo-1",
    branch_name: "main",
    created_at: `2026-01-0${4 - n}T00:00:00Z`,
    node_count: 128,
    edge_count: 214,
    signal_count: 3,
  }));
}

describe("choosing a repository", () => {
  // The branch probe is debounced, so the wait has to be controllable rather than real.
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("lists a repository once, however many times it has been indexed", async () => {
    vi.spyOn(api, "repositories").mockResolvedValue(indexedThreeTimes());

    render(wrap(<StartPage />));

    // One entry, not three. `/api/repositories` answers "which checkouts have been indexed",
    // and every re-index adds a row — right for a version listing, wrong for a chooser.
    const chosen = await screen.findAllByText("payments-platform");
    expect(chosen).toHaveLength(1);
    // And it says what it collapsed, rather than quietly dropping two records.
    expect(screen.getByText(/3 indexes/)).toBeInTheDocument();
  });

  it("offers the remote's branches rather than asking for one to be spelled", async () => {
    vi.spyOn(api, "remoteBranches").mockResolvedValue(["main", "release/2026-01"]);

    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Clone/ }));
    fireEvent.change(screen.getByLabelText(/Repository address/), {
      target: { value: "https://github.com/org/repository" },
    });

    // Typed, so nothing is asked yet: ls-remote is a round trip to somebody else's server
    // and a half-typed address is a request that was always going to fail.
    expect(api.remoteBranches).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(700);

    const chooser = await screen.findByRole("combobox", { name: /Branch/ });
    expect(within(chooser).getByRole("option", { name: "release/2026-01" })).toBeInTheDocument();
    // Nothing chosen means the remote's own default, which is a real answer and not a blank.
    expect(within(chooser).getByRole("option", { name: /default/ })).toBeInTheDocument();
  });

  it("lets a branch be named when the remote will not say what it has", async () => {
    // A private remote git has no credentials for answers with an empty list. That says
    // nothing about whether the branch the reader wants exists, so the field has to stay
    // fillable — refusing here would turn "I cannot offer a list" into "you may not clone".
    vi.spyOn(api, "remoteBranches").mockResolvedValue([]);

    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Clone/ }));
    fireEvent.change(screen.getByLabelText(/Repository address/), {
      target: { value: "https://github.com/org/private" },
    });
    await vi.advanceTimersByTimeAsync(700);

    await waitFor(() => expect(api.remoteBranches).toHaveBeenCalled());
    expect(screen.getByRole("textbox", { name: /Branch/ })).toBeInTheDocument();
  });
});

describe("starting a review", () => {
  it("will not run until both models are chosen, and says which is missing", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(
      workspaceFixture({
        models: { reasoning: { provider: "fake", model: "deterministic" }, embedding: null },
      }),
    );

    render(wrap(<StartPage />));

    expect(await screen.findByText("not chosen yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose models" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("button", { name: /Run review/ })).toBeDisabled();
  });

  it("takes a repository handed over by the repositories page", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(await screen.findByText("/work/payments-platform")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run review" })).not.toBeDisabled(),
    );
  });

  it("hands the review to the workspace rather than holding it open here", async () => {
    // The run used to live inside a streaming response owned by this page, so reloading
    // the tab abandoned it. Now the page asks for a run and goes to watch it by id.
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(api, "startRepository").mockResolvedValue({
      case_id: "case-1",
      revision: 1,
    });
    const started = vi.spyOn(api, "startReviewRun").mockResolvedValue({
      run_id: "thread-7",
      status: "running",
      review_id: null,
      stage: "load_context",
      stages: ["load_context"],
      failure: "",
    });

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    const run = await screen.findByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    await waitFor(() =>
      expect(started).toHaveBeenCalledWith("case-1", "/work/payments-platform"),
    );
    // The address it moves to is the run, which survives a reload.
    expect(await screen.findByText("/runs/thread-7")).toBeInTheDocument();
  });

  it("reports a failed run in place rather than navigating away", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(api, "startRepository").mockRejectedValue(
      new Error("That folder is not a repository"),
    );

    render(wrap(<StartPage />, "/start?root=%2Fnot%2Fa%2Frepository"));

    const run = await screen.findByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    expect(await screen.findByText(/That folder is not a repository/)).toBeInTheDocument();
    expect(screen.queryByText("Review workbench")).not.toBeInTheDocument();
  });

  it("reviews the whole repository until somebody says otherwise, and then only the rest", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    const started = vi.spyOn(api, "startRepository").mockResolvedValue({
      case_id: "case-1",
      revision: 1,
    });
    vi.spyOn(api, "startReviewRun").mockResolvedValue({
      run_id: "thread-7",
      status: "running",
      review_id: null,
      stage: "load_context",
      stages: ["load_context"],
      failure: "",
    });

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    // The count is the question the reader is answering: what would leaving this out save.
    expect(await screen.findByText(/128 Python files/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Leave out src" }));
    // A parent covers its children, so `src/vendor` is no longer a decision of its own.
    expect(screen.getByRole("checkbox", { name: "Leave out src/vendor" })).toBeDisabled();
    expect(screen.getByText("32", { selector: "strong" })).toBeInTheDocument();

    const run = screen.getByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    // Sent as a list every time, including empty: absent would mean "keep the last scope",
    // and what is on screen has to be what the review reads.
    await waitFor(() =>
      expect(started).toHaveBeenCalledWith("/work/payments-platform", false, ["src"]),
    );
  });

  it("offers the indexed repositories without making anyone type a path", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("button", { name: /payments-platform/ }));
    expect(screen.getByText("Selected")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run review" })).not.toBeDisabled(),
    );
  });
});
