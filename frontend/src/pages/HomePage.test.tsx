import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { HomePage } from "./HomePage";

function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // jsdom ships no `matchMedia`; stubbed here rather than guarded in the page, as
  // `theme.test.tsx` does for the same reason.
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn() }),
  });
});

afterEach(() => vi.restoreAllMocks());

describe("the hero's verdict card", () => {
  it("says the specimens are specimens", () => {
    open();

    expect(
      screen.getByText(/Specimen verdicts — run a bundled example to write your own/),
    ).toBeInTheDocument();
    expect(screen.getByText("Remove the boundary.")).toBeInTheDocument();
    expect(screen.getByText("avoid-pass-through-parameters")).toBeInTheDocument();
  });

  it("reads nothing from the workspace to draw them", () => {
    const listed = vi.spyOn(api, "reviews");
    const read = vi.spyOn(api, "review");

    open();

    expect(listed).not.toHaveBeenCalled();
    expect(read).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: /latest review/ })).toBeNull();
  });
});
