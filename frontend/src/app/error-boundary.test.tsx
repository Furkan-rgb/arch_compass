import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { workspaceFixture } from "../test-fixtures";
import { ErrorBoundary, isChunkLoadError } from "./error-boundary";
import { AppShell } from "./shell";

/**
 * There was no boundary anywhere in the application: no `componentDidCatch`, no router
 * `errorElement`. React unmounts the tree on an uncaught render error, so a reviewer part
 * way down a docket got a blank canvas that kept the URL — the open row, the filter and any
 * half-typed waiver reason gone, with nothing on screen saying what had happened.
 */
function Thrower({ boom }: { boom: boolean }): React.ReactElement {
  if (boom) throw new Error("Cannot read properties of undefined (reading 'verdict')");
  return <p>The review</p>;
}

/** What Chrome rejects a `lazy()` loader with when the chunk it names is no longer served. */
const CHUNK_MESSAGE =
  "Failed to fetch dynamically imported module: http://127.0.0.1:8765/assets/review-page-KnL_iWzE.js";

function ChunkThrower(): React.ReactElement {
  throw new Error(CHUNK_MESSAGE);
}

function wrap(boom: boolean, entry = "/reviews") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <AppShell>
          <ErrorBoundary>
            <Routes>
              <Route path="/reviews" element={<Thrower boom={boom} />} />
              <Route path="/policies" element={<p>The policies</p>} />
            </Routes>
          </ErrorBoundary>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspaceFixture());
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
  // React prints the caught error and its component stack. That is the point of the
  // boundary, and it is noise in a test that is asserting the boundary works.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("the error boundary", () => {
  it("keeps the rail, says what happened, and offers a way on", () => {
    render(wrap(true));

    expect(screen.getByRole("alert")).toHaveTextContent("reading 'verdict'");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to your reviews" })).toHaveAttribute(
      "href",
      "/reviews",
    );
  });

  /**
   * A boundary that latches for ever turns one broken screen into a broken application: the
   * reader navigates away, the URL changes, and the fallback is still there because nothing
   * told it the subject had changed.
   */
  it("clears itself when the reader goes somewhere else", () => {
    render(wrap(true));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Policies" })[0]);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("The policies")).toBeInTheDocument();
  });
});

/**
 * The two `lazy()` routes in `App.tsx` are the whole population of this fallback, and it exists
 * because the generic one is wrong twice over about them. They are not the only chunks fetched
 * by name — `/` fetches its own docket that way — but the landing page catches that failure in
 * `ExhibitBoundary` and it never reaches this screen. "This screen stopped part way through" describes a render that threw; this screen
 * never started. And "Try this screen again" cannot work: React records a rejected `lazy()`
 * payload and re-throws it without calling the loader again, so the button that leads here has
 * to be the reload.
 */
describe("a chunk that never arrived", () => {
  function chunkWrap() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/reviews"]}>
          <AppShell>
            <ErrorBoundary>
              <ChunkThrower />
            </ErrorBoundary>
          </AppShell>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it("says the tab is running an older build, and does not offer the button that cannot work", () => {
    render(chunkWrap());

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("This page is running an older copy of the workbench");
    expect(alert).toHaveTextContent(CHUNK_MESSAGE);
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try this screen again" })).not.toBeInTheDocument();
  });

  /**
   * Four wordings for one fault, because the browsers disagree and none of them offers an
   * error type to match on instead. They are quoted from the engines and from Vite's preload
   * helper; the last case is the one that matters most, since reading an ordinary render error
   * as a stale chunk would tell a reader their tab is out of date when it is not, and would
   * take away the retry that for that fault is the button that works.
   */
  it.each([
    ["Chrome", CHUNK_MESSAGE],
    ["Firefox", "error loading dynamically imported module"],
    ["Safari", "Importing a module script failed."],
    ["Vite's preload helper", "Unable to preload CSS for /assets/index-4IIXmz-r.css"],
  ])("is recognised from what %s says", (_engine, message) => {
    expect(isChunkLoadError(new Error(message))).toBe(true);
  });

  it("is not confused with a render error, which keeps the retry the reload would waste", () => {
    expect(isChunkLoadError(new TypeError("x.map is not a function"))).toBe(false);
    expect(isChunkLoadError(new SyntaxError("Unexpected end of JSON input"))).toBe(false);
  });
});
