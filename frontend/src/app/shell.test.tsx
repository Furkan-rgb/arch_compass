import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { coreApi } from "../api";
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
  vi.spyOn(coreApi, "workspace").mockResolvedValue(workspaceFixture());
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
