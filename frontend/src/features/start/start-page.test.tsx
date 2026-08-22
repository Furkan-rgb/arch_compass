import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { reviewSummaryFixture, runFixture, workspaceFixture } from "../../test-fixtures";
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
  vi.spyOn(api, "reviewSummaries").mockResolvedValue([]);
  // Nothing else in this workspace is running, which is the ordinary case and the one the
  // rest of these tests are about.
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
  vi.spyOn(api, "directories").mockResolvedValue({
    path: "/work",
    parent: "/",
    directories: [{ name: "payments-platform", path: "/work/payments-platform" }],
  });
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
  return [
    {
      version_id: "version-3",
      repository_identity: "identity-1",
      root_path: "/work/payments-platform",
      git_commit_sha: "8f31c2a91b4d",
      repo_id: "repo-1",
      branch_name: "main",
      created_at: "2026-01-03T00:00:00Z",
      snapshot_count: 3,
      node_count: 128,
      edge_count: 214,
      signal_count: 3,
    },
  ];
}

describe("choosing a repository", () => {
  // The branch probe is debounced, so the wait has to be controllable rather than real.
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("lists a repository once, however many times it has been indexed", async () => {
    vi.spyOn(api, "repositories").mockResolvedValue(indexedThreeTimes());

    render(wrap(<StartPage />));

    // One entry, not three. The listing groups now, so the three indexes arrive as one row
    // — and this chooser holds an eight-item cap, which eight copies of one repository used
    // to fill on their own.
    const chosen = await screen.findAllByText("payments-platform");
    expect(chosen).toHaveLength(1);
    // And what the workspace holds behind that row is stated rather than dropped.
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

  /**
   * A path being typed is not a path anybody has chosen yet.
   *
   * `PathField` called `onChange` per character, which re-keyed the repository tree query —
   * and that route walks the folder with `rglob("*")` and a `stat()` per file. So every
   * prefix that happened to be a real directory was walked in full on the way to the one the
   * reader meant, including their whole home folder as they typed past it, and the panel
   * flickered between "Reading the repository…" and "That repository could not be read".
   */
  it("does not walk a repository for every keystroke of the path being typed", async () => {
    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Browse/ }));
    const field = await screen.findByLabelText(/Repository path/);
    for (const value of ["/", "/w", "/wo", "/work", "/work/payments-platform"]) {
      fireEvent.change(field, { target: { value } });
    }

    expect(api.repositoryTree).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(700);
    await waitFor(() => expect(api.repositoryTree).toHaveBeenCalledTimes(1));
    expect(api.repositoryTree).toHaveBeenCalledWith(
      "/work/payments-platform",
      expect.anything(),
    );
  });

  it("takes a path the moment Enter is pressed, without waiting out the debounce", async () => {
    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Browse/ }));
    const field = await screen.findByLabelText(/Repository path/);
    fireEvent.change(field, { target: { value: "/work/payments-platform" } });
    fireEvent.keyDown(field, { key: "Enter" });

    await waitFor(() => expect(api.repositoryTree).toHaveBeenCalledTimes(1));
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

    // `aria-disabled`, not `disabled`, and the difference is the whole point: this is the one
    // action the page exists for, so it keeps its tab stop and stays reachable — a keyboard
    // user who tabs onto it hears that it is unavailable and hears why, from the sentence
    // `aria-describedby` names. A real `disabled` took it out of the tab order and told them
    // nothing at all. So both halves are asserted: it announces as off, and it does nothing.
    const started = vi.spyOn(api, "startRepository");
    const run = screen.getByRole("button", { name: /Run review/ });
    expect(run).toHaveAttribute("aria-disabled", "true");
    expect(run).toHaveAccessibleDescription(/repository|models/i);
    fireEvent.click(run);
    expect(started).not.toHaveBeenCalled();
  });

  it("takes a repository handed over by the repositories page", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(await screen.findByText("/work/payments-platform")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run review" })).not.toBeDisabled(),
    );
  });

  /**
   * A repository without its scope is half a hand-off.
   *
   * "Start again" on a failed run brought the path back and left the folders behind, so the
   * reader re-ticked by hand a choice the run page was already displaying — and a rerun made
   * with a different scope is a review of a different question, not a retry of the same one.
   */
  it("arrives with the folders the link named already left out", async () => {
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

    render(
      wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform&exclude=tests"),
    );

    expect(await screen.findByRole("checkbox", { name: "Leave out tests" })).toBeChecked();
    // And the count under the button is the count of what is actually going to be read.
    expect(screen.getByText("96", { selector: "strong" })).toBeInTheDocument();

    const run = screen.getByRole("button", { name: "Run review" });
    await waitFor(() => expect(run).not.toBeDisabled());
    fireEvent.click(run);

    await waitFor(() =>
      expect(started).toHaveBeenCalledWith("/work/payments-platform", false, ["tests"]),
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
    // Said twice on purpose — once over the folders, and once under the button that spends it.
    expect(await screen.findAllByText(/128 Python files/)).toHaveLength(2);
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

  /**
   * A second run of the same repository spends the model budget twice for two reviews of one
   * commit.
   *
   * Nothing stopped it: the page's own busy flag guards a double-click and nothing else, so
   * going back to `/start`, opening a second tab, or arriving from the repositories page with
   * `?root=` all left the primary button live for a repository already being reviewed.
   */
  it("points at the run already in flight rather than offering a second one", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(api, "reviewRuns").mockResolvedValue([
      runFixture({ run_id: "thread-3", repository_root: "/work/payments-platform" }),
    ]);

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(await screen.findByRole("link", { name: "Watch it" })).toHaveAttribute(
      "href",
      "/runs/thread-3",
    );
    // Demoted, not removed: reviewing the same commit twice is occasionally what somebody
    // means, and it must not be the unlabelled default click.
    expect(screen.queryByRole("button", { name: "Run review" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run another anyway" })).toBeInTheDocument();
  });
});

/**
 * The case sentence is a fact somebody takes a decision on, so it may not be a guess.
 *
 * It matched the newest review by exact string on the path while the workspace canonicalises
 * with `expanduser().resolve()`, and it did not filter by branch at all. So a trailing slash
 * produced "opens a new architecture case" while the workspace went on to continue revision
 * 4, and a feature branch was told `main`'s case revision and `main`'s answer count — with
 * "Start from an empty case instead" sitting directly under both.
 */
describe("which case a run will continue", () => {
  // The listing shape, because that is what this page reads now. Every fact the sentence
  // states is a column of the projection — the revision, the branch, and the answer count
  // that used to be the one reason the whole review had to travel.
  const priorOnMain = reviewSummaryFixture({
    id: "review-9",
    sequence: 3,
    status: "completed",
    case_id: "case-1",
    case_revision: 2,
    answer_count: 1,
    question_count: 0,
    started_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:07:00Z",
  });

  beforeEach(() => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(api, "reviewSummaries").mockResolvedValue([priorOnMain]);
  });

  it("finds the case behind a path spelled with a trailing slash", async () => {
    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform%2F"));

    expect(await screen.findByText(/Continues case revision/)).toHaveTextContent(
      /Continues case revision 2 on main — 1 answer/,
    );
  });

  it("does not give a feature branch the case and the answers of another branch", async () => {
    // The same checkout, indexed on a different branch. The reviews on record are `main`'s.
    vi.spyOn(api, "repositories").mockResolvedValue([
      {
        version_id: "version-2",
        repository_identity: "identity-1",
        root_path: "/work/payments-platform",
        git_commit_sha: "1c0ffee",
        repo_id: "repo-1",
        branch_name: "feature/ports",
        created_at: "2026-01-02T00:00:00Z",
        node_count: 128,
        edge_count: 214,
        signal_count: 3,
      },
    ]);

    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(await screen.findByText(/Opens a new architecture case/)).toBeInTheDocument();
    expect(screen.queryByText(/Continues case revision/)).not.toBeInTheDocument();
  });

  it("says it cannot tell, rather than claiming a new case for a path it has never indexed", async () => {
    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fsomewhere-else"));

    expect(await screen.findByText(/has not been indexed in this workspace/)).toBeInTheDocument();
    expect(screen.queryByText(/Opens a new architecture case/)).not.toBeInTheDocument();
    // And the other choice is still reachable, because starting clean is always available.
    expect(
      screen.getByRole("button", { name: "Start from an empty case instead" }),
    ).toBeInTheDocument();
  });

  /**
   * Step 2 measures Python files, and a review does not spend files — it spends candidates
   * and minutes. Both are on the record of the previous review, so both are read off it
   * rather than estimated, and the sentence is absent where there is no prior review.
   */
  it("says what the last review of this branch actually cost", async () => {
    render(wrap(<StartPage />, "/start?root=%2Fwork%2Fpayments-platform"));

    expect(
      await screen.findByText("Review 3 of this branch judged 3 candidates and took 7 minutes."),
    ).toBeInTheDocument();
  });
});

/**
 * A fresh install opened on an empty tab and was never told five example repositories ship.
 *
 * `Indexed` is the right first tab for anybody who has indexed something and the wrong one
 * for everybody else: on a first run it was a sentence with no buttons under it, while the
 * bundled examples — the shortest route in this product to a real finding — sat unmentioned
 * on the fourth tab.
 */
describe("a workspace with nothing in it", () => {
  const example = {
    name: "acme-shop",
    title: "Acme Shop",
    description: "A layered shop with one boundary worth arguing about.",
    repository_root: "/examples/acme-shop",
  };

  beforeEach(() => {
    vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
    vi.spyOn(api, "repositories").mockResolvedValue([]);
    vi.spyOn(api, "examples").mockResolvedValue([example]);
  });

  it("opens on the bundled examples rather than on an empty list", async () => {
    render(wrap(<StartPage />));

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Examples/ })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    expect(screen.getByRole("button", { name: /Acme Shop/ })).toBeInTheDocument();
  });

  it("gives the empty list two ways out instead of a sentence and nothing", async () => {
    render(wrap(<StartPage />));

    fireEvent.click(await screen.findByRole("tab", { name: /Indexed/ }));
    expect(screen.getByText("Nothing indexed yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse this machine" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open an example" }));
    expect(screen.getByRole("button", { name: /Acme Shop/ })).toBeInTheDocument();
  });

  it("says an example is being indexed, and stops offering the others while it is", async () => {
    vi.spyOn(api, "examples").mockResolvedValue([
      example,
      { ...example, name: "ledger", title: "Ledger", repository_root: "/examples/ledger" },
    ]);
    // Held open, because what is being asserted is the state during the load — which reached
    // the screen nowhere at all, so a click read as having done nothing and people clicked a
    // second example on top of the first.
    let finish = () => {};
    vi.spyOn(api, "loadExample").mockReturnValue(
      new Promise((resolve) => {
        finish = () => resolve({ repository_identity: "identity-1" } as never);
      }),
    );

    render(wrap(<StartPage />));

    const shop = await screen.findByRole("button", { name: /Acme Shop/ });
    fireEvent.click(shop);

    await waitFor(() => expect(shop).toHaveAttribute("aria-pressed", "true"));
    expect(within(shop).getByText("indexing…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ledger/ })).toBeDisabled();
    expect(shop).toBeDisabled();

    finish();
    await waitFor(() => expect(screen.getByRole("button", { name: /Ledger/ })).not.toBeDisabled());
  });
});
