import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { RunProvider } from "../run";
import { StartPage } from "./StartPage";
import type { AtlasVersion, DirectoryListing, RepositorySummary } from "../types";

const HOME: DirectoryListing = {
  path: "/home/dev",
  parent: "/home",
  directories: [
    { name: "notes", path: "/home/dev/notes" },
    { name: "warehouse", path: "/home/dev/warehouse" },
  ],
};

const WAREHOUSE: DirectoryListing = {
  path: "/home/dev/warehouse",
  parent: "/home/dev",
  directories: [{ name: "picking", path: "/home/dev/warehouse/picking" }],
};

const INDEXED: RepositorySummary = {
  version_id: "atlas-1",
  repository_identity: "warehouse",
  root_path: "/home/dev/warehouse",
  created_at: "2026-07-30T10:00:00Z",
  node_count: 128,
  edge_count: 240,
  signal_count: 3,
};

/** A workspace that has chosen a model. The run button needs one, so most tests want it. */
function chosenModel(reasoning: { provider: string; model: string } | null) {
  vi.spyOn(api, "workspace").mockResolvedValue({
    workspace: "/home/dev/workspace",
    models: {
      reasoning,
      failure: "",
      pinned: false,
    },
  });
}

/** Every read the start step makes, with the repository listing under the test's control. */
function workspace(repositories: RepositorySummary[] = []) {
  const listed = { current: repositories };
  chosenModel({ provider: "fake", model: "deterministic-architecture-v4" });
  vi.spyOn(api, "repositories").mockImplementation(async () => listed.current);
  vi.spyOn(api, "reviews").mockResolvedValue([]);
  vi.spyOn(api, "examples").mockResolvedValue([]);
  vi.spyOn(api, "directories").mockImplementation(async (path?: string) =>
    path === "/home/dev/warehouse" ? WAREHOUSE : HOME,
  );
  return listed;
}

function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <RunProvider>
          <StartPage />
        </RunProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/* Awaited, because the field and its folder button appear once the workspace has answered
   whether this is a demo — before that there is nothing to click. */
const browse = async () =>
  fireEvent.click(await screen.findByRole("button", { name: /Browse local folders/ }));

afterEach(() => vi.restoreAllMocks());

describe("indexing a repository by browsing to it", () => {
  it("indexes the folder that was walked to, and selects what came back", async () => {
    const listed = workspace();
    const indexed = vi
      .spyOn(api, "indexRepository")
      .mockImplementation(async (root: string) => {
        listed.current = [INDEXED];
        return { root_path: root } as AtlasVersion;
      });

    open();
    await browse();

    await screen.findByRole("button", { name: /warehouse/ });
    fireEvent.click(screen.getByRole("button", { name: /warehouse/ }));
    await waitFor(() => expect(screen.getByLabelText("Folder path or git address")).toHaveValue(
      "/home/dev/warehouse",
    ));

    fireEvent.click(screen.getByRole("button", { name: "Index this folder" }));

    // The absolute path the server resolved, not a name the picker composed.
    await waitFor(() => expect(indexed).toHaveBeenCalledWith("/home/dev/warehouse"));
    await waitFor(() => expect(screen.queryByLabelText("Folder path or git address")).toBeNull());
    expect(
      await screen.findByText(/Judging every boundary in/),
    ).toHaveTextContent("warehouse");
  });

  it("goes to a pasted path, and stays open when the workspace refuses one", async () => {
    workspace();
    vi.spyOn(api, "indexRepository").mockRejectedValue(
      new ApiError("Repository does not exist: /nowhere", 422, "validation_error"),
    );

    open();
    await browse();
    await screen.findByLabelText("Folder path or git address");

    // Pasted before the home listing has landed: the field stops following the walk the
    // moment it is edited, so the arriving listing must not eat it.
    fireEvent.change(screen.getByLabelText("Folder path or git address"), {
      target: { value: "/home/dev/warehouse" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /picking/ })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Index this folder" }));

    expect(await screen.findByText("Repository does not exist: /nowhere")).toBeInTheDocument();
    expect(screen.getByLabelText("Folder path or git address")).toHaveValue("/home/dev/warehouse");
  });

  it("refuses to climb past the filesystem root", async () => {
    workspace();
    vi.spyOn(api, "directories").mockResolvedValue({
      path: "/",
      parent: null,
      directories: [{ name: "home", path: "/home" }],
    });

    open();
    await browse();

    const up = await screen.findByRole("button", { name: /parent folder/ });
    expect(up).toBeDisabled();
  });
});

describe("running needs a model as well as a repository", () => {
  it("names the missing model and refuses to run, once a repository is chosen", async () => {
    workspace([INDEXED]);
    chosenModel(null);

    open();

    expect(await screen.findByText(/No reasoning model is chosen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run review/ })).toBeDisabled();
  });

  it("runs once a model is there, with the same repository chosen", async () => {
    workspace([INDEXED]);

    open();

    await screen.findByText(/Judging every boundary in/);
    expect(screen.getByRole("button", { name: /Run review/ })).toBeEnabled();
  });
});

/** The hosted demo, with or without hosts it will fetch a repository from. */
function hostedWorkspace(sourceHosts: string[]) {
  workspace([]);
  vi.spyOn(api, "workspace").mockResolvedValue({
    workspace: "Hosted demo workspace",
    models: {
      reasoning: { provider: "fake", model: "deterministic-architecture-v4" },
      failure: "",
      pinned: false,
    },
    hosted: true,
    source_hosts: sourceHosts,
  });
}

describe("what the hosted demo offers", () => {
  it("offers the address field, naming the hosts it will fetch from", async () => {
    hostedWorkspace(["github.com"]);
    open();

    // By placeholder, so this waits for the hosted answer rather than catching the field
    // in the beat before the workspace query settles.
    await screen.findByPlaceholderText("https://github.com/owner/repository");
    expect(await screen.findByText(/Public repositories on github\.com/)).toBeInTheDocument();
    // Browsing is this machine's folders, and the hosted server refuses to list its own.
    expect(screen.queryByRole("button", { name: /Browse local folders/ })).toBeNull();
  });

  it("hides the address field when the demo was given no hosts to fetch from", async () => {
    hostedWorkspace([]);
    open();

    expect(await screen.findByText(/load an example above/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Repository address or path")).toBeNull();
    expect(screen.queryByRole("button", { name: /Browse local folders/ })).toBeNull();
  });

  it("shows the server's refusal verbatim when an address is not one it will fetch", async () => {
    hostedWorkspace(["github.com"]);
    vi.spyOn(api, "checkoutRepository").mockRejectedValue(
      new ApiError(
        "'https://evil.test/o/r' is not an address this workspace will fetch.",
        409,
        "checkout_failed",
      ),
    );
    open();

    fireEvent.change(await screen.findByLabelText("Repository address or path"), {
      target: { value: "https://evil.test/o/r" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText(/is not an address this workspace will fetch/)).toBeInTheDocument();
  });
});
