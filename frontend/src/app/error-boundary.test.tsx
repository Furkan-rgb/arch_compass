import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { workspaceFixture } from "../test-fixtures";
import { ErrorBoundary } from "./error-boundary";
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
