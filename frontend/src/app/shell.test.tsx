import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { VIEWPORT, setViewportWidth } from "../test-setup";
import { runFixture, workspaceFixture } from "../test-fixtures";
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
  vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
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
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    expect(within(drawer).getByRole("link", { name: "Architecture cases" })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument(),
    );
  });

  /**
   * The 256 pixels between the hamburger going and the chips arriving.
   *
   * `lg:hidden` on the drawer button and `xl:flex` on the chips left a band — 1024 to
   * 1279, an ordinary window width — where there was no drawer to open and no chips, so
   * nothing on any page said which repository root the workspace pointed at or which two
   * models it ran. The two breakpoints are the same one now.
   *
   * Asserted at the class rather than through visibility, because jsdom applies no
   * stylesheet: what is being checked is which breakpoint the element was given.
   */
  it("still names the two models at a width with no navigation drawer", async () => {
    setViewportWidth(VIEWPORT.tablet);
    render(wrap());

    const chip = (await screen.findAllByRole("link", { name: /Reasoning/ }))[0];
    const chips = chip.parentElement;
    expect(chips).toHaveClass("lg:flex");
    expect(chips).not.toHaveClass("xl:flex");

    // The drawer's own trigger goes at exactly the width the chips arrive at, so no width
    // has neither.
    expect(screen.getByRole("button", { name: "Open navigation" })).toHaveClass("lg:hidden");
  });

  /** The dead `stacked` prop had no call site, so below `lg` the drawer named nothing. */
  it("names them again inside the navigation drawer, where the rail cannot", async () => {
    setViewportWidth(VIEWPORT.phone);
    render(wrap());

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const drawer = await screen.findByRole("dialog", { name: "Navigation" });
    await waitFor(() =>
      expect(within(drawer).getByRole("link", { name: /Reasoning model/ })).toHaveTextContent(
        "deterministic",
      ),
    );
    expect(within(drawer).getByRole("link", { name: /Embedding model/ })).toBeInTheDocument();
  });

  /**
   * Two controls on the dark rail drew their focus ring in ink, and ink on a light page is
   * near-black — so the first thing a keyboard reaches on every screen, and the one button
   * that starts a review, both rang black on black. The band's own ink is white in both
   * themes, which is the only value that reads on this ground.
   */
  it("draws the rail's focus rings in a colour the rail can show", () => {
    render(wrap());
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveClass(
      "focus-visible:outline-band-ink",
    );
    expect(screen.getByRole("link", { name: "New review" })).toHaveClass(
      "focus-visible:outline-band-ink",
    );
  });

  /**
   * A run is minutes long and the run page says you can leave. Leaving used to remove every
   * trace of it: no badge, no count, nothing anywhere else in the product.
   */
  it("says a review is running wherever you are, and says nothing when none is", async () => {
    render(wrap("/policies"));
    await waitFor(() => expect(api.reviewRuns).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /review running/ })).not.toBeInTheDocument();

    vi.mocked(api.reviewRuns).mockResolvedValue([runFixture()]);
    render(wrap("/policies"));

    const indicator = await screen.findByRole("link", { name: /1 review running/ });
    expect(indicator).toHaveAttribute("href", "/runs/thread-9");
  });

  /**
   * The dot is the accent, and the thing worth guarding is that it is not the verdict scale.
   *
   * `bg-material-edge` resolves to the same red, so the two are indistinguishable on screen and
   * a swap would pass every hue guard there is — `ui/badge.tsx` is allowed to say either. What
   * it would cost is the rail's other red: `material` there means a recorded provider failure,
   * and two identical dots a few centimetres apart stop meaning two different things. So this
   * asserts the class, which is the only place the distinction survives.
   *
   * The tier moved and the distinction did not. A dot is a graphic, so all five hue-bearing
   * tones in `StatusDot` are painted from the `-edge` half of their signal now; the accent
   * needed a second name at that tier to come with them, and `styles.css` declares
   * `--accent-edge: var(--material-edge)` for this one dot. Asserting the bare `bg-accent` here
   * would now pass on a class that paints nothing.
   */
  it("paints the running dot in the accent rather than in a verdict's hue", async () => {
    vi.mocked(api.reviewRuns).mockResolvedValue([runFixture()]);
    render(wrap("/policies"));

    const indicator = await screen.findByRole("link", { name: /1 review running/ });
    const dot = indicator.querySelector("span[aria-hidden]");
    expect(dot).toHaveClass("bg-accent-edge", "animate-breathe");
    expect(dot).not.toHaveClass("bg-material-edge");
  });

  it("opens the shortcut sheet from the rail and from the ? key", async () => {
    render(wrap());

    fireEvent.click(screen.getByRole("button", { name: "Keyboard shortcuts" }));
    const sheet = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    expect(within(sheet).getByText("Accept and act on the open finding")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).not.toBeInTheDocument(),
    );

    fireEvent.keyDown(document, { key: "?" });
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });

  it("refuses ? while something is being typed into", async () => {
    render(wrap());
    const search = screen.getByRole("button", { name: "Search everything" });
    fireEvent.click(search);
    const field = await screen.findByRole("combobox");

    fireEvent.keyDown(field, { key: "?", target: field });
    expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).not.toBeInTheDocument();
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
