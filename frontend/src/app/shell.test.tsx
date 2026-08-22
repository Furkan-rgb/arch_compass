import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { VIEWPORT, setViewportWidth } from "../test-setup";
import { workspaceFixture } from "../test-fixtures";
import { AppShell } from "./shell";

function wrap(entry = "/reviews") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <AppShell>
          <h1>Page content</h1>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  setViewportWidth(VIEWPORT.desktop);
  vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
  window.localStorage.clear();
});

afterEach(() => vi.restoreAllMocks());

describe("the application shell", () => {
  it("offers a skip link and a labelled main landmark", () => {
    render(wrap());
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });

  it("names the current section and the reasoning and embedding models", async () => {
    render(wrap("/policies"));

    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Policies" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await waitFor(() =>
      expect(screen.getAllByRole("link", { name: /Reasoning/ })[0]).toHaveTextContent(
        "deterministic",
      ),
    );
    expect(screen.getAllByRole("link", { name: /Reasoning/ })[0]).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(screen.getAllByRole("link", { name: /Embedding/ })[0]).toHaveTextContent(
      "nomic-embed-text",
    );
  });

  /**
   * The dot beside a model name is the only place the rail reports a state, and it reported
   * two of them in a colour that never changed: `held` resolved against the page, so on a
   * light theme "nothing is selected" drew `#0a0a0a` on the black rail and vanished.
   *
   * Asserted through the accessible name rather than through a class, because what a reader
   * has to be able to tell apart is the state, and the fill is `.on-band`'s job — the header
   * carrying that class is the second half, checked below.
   */
  it("says which state each model chip is in, and reports a recorded failure", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(
      workspaceFixture({
        models: {
          reasoning: { provider: "fake", model: "deterministic", thinking: null },
          embedding: null,
          failure: "anthropic refused the last call: 401",
          pinned: true,
          embedding_pinned: false,
        },
      }),
    );
    render(wrap());

    await waitFor(() =>
      expect(
        screen.getAllByRole("link", { name: /Reasoning model: deterministic — anthropic refused/ })[0],
      ).toBeInTheDocument(),
    );
    expect(
      screen.getAllByRole("link", { name: /Embedding model: not selected — not selected/ })[0],
    ).toBeInTheDocument();
  });

  it("scopes the verdict palette to the rail, which is dark on a light page too", () => {
    render(wrap());
    expect(screen.getByRole("banner")).toHaveClass("on-band");
  });

  it("puts navigation behind a drawer on a phone, and closes it with Escape", async () => {
    setViewportWidth(VIEWPORT.phone);
    render(wrap());

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const drawer = await screen.findByRole("dialog", { name: "ArchCompass" });
    expect(within(drawer).getByRole("link", { name: "Architecture cases" })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "ArchCompass" })).not.toBeInTheDocument(),
    );
  });

  it("cycles the theme preference and remembers it", async () => {
    render(wrap());

    const toggle = screen.getByRole("button", { name: /Theme: system/ });
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(window.localStorage.getItem("archcompass.theme")).toBe("light"),
    );
    expect(document.documentElement.dataset.theme).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: /Theme: light/ }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
  });
});
