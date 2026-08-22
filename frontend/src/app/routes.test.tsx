import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { api } from "../api";
import { workspaceFixture } from "../test-fixtures";

function wrap(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
  // jsdom defines `window.scrollTo` and refuses to do it. `ScrollToTop` runs on every route
  // change, so without this every assertion here arrives behind a stack trace.
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("the routes", () => {
  /**
   * An unknown URL used to `<Navigate to="/start" replace />`, silently. So a stale link — a
   * review that has since been deleted, a bookmark from before a rename — landed somebody on
   * a form with no explanation and no way to tell whether they had mistyped or the thing was
   * gone. The address is the one piece of information the reader does not have.
   */
  it("names the address that is not a screen, rather than redirecting without a word", () => {
    render(wrap("/reviews/deleted-review/report"));

    expect(screen.getByText("No screen at that address")).toBeInTheDocument();
    expect(screen.getByText("/reviews/deleted-review/report")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Your reviews" })).toHaveAttribute("href", "/reviews");
  });

  /**
   * The landing page is the one route guaranteed to be somebody's first, and it sat behind a
   * lazy import with a `null` fallback — the HTML, then the entry bundle, then a second round
   * trip, and a blank white page for all of it. It is imported statically now, so it paints
   * with no suspension at all: no fallback, nothing to wait for.
   */
  it("paints the landing page without waiting for a second chunk", () => {
    render(wrap("/"));
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });
});
