/**
 * The front door.
 *
 * Two things are defended here. Everything drawn on this page is fabricated, so every
 * fabricated region has to say so — a specimen verdict passed off as a real one falsifies the
 * exact claim the page makes. And the page reads nothing from the workspace, so it draws the
 * same argument on the first paint whatever this machine has judged.
 *
 * The rest is the replay: a run of five boundaries advancing on a timer, into the same ledger
 * and the same band a real run fills. It holds while it is being looked at, and a reader who
 * has asked for less motion gets it as a still.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { HomePage, REPLAY_INTERVAL_MS, REPLAY_STILL } from "./HomePage";

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

/** jsdom ships no `matchMedia`; stubbed here rather than guarded in the page, as
    `theme.test.tsx` does for the same reason. */
function prefers(reducedMotion: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: reducedMotion, addEventListener: vi.fn() }),
  });
}

const stack = () => document.querySelector('[data-slot="verdict-stack"]') as HTMLElement;
const replay = () => document.querySelector('[data-slot="run-replay"]') as HTMLElement;

beforeEach(() => prefers(false));
afterEach(() => vi.restoreAllMocks());

describe("the hero's verdict card", () => {
  it("says the specimens are specimens", () => {
    open();

    const hero = within(stack());
    expect(
      hero.getByText(/Specimen verdicts — run a bundled example to write your own/),
    ).toBeInTheDocument();
    expect(hero.getByText("Remove the boundary.")).toBeInTheDocument();
    expect(hero.getByText("avoid-pass-through-parameters")).toBeInTheDocument();
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

describe("every fabricated region", () => {
  it("is labelled as one", () => {
    open();

    for (const line of [
      /Specimen verdicts —/,
      /Specimen run —/,
      /Specimen question —/,
      /Specimen report —/,
    ]) {
      expect(screen.getByText(line)).toBeInTheDocument();
    }
  });
});

describe("the run, replayed", () => {
  it("advances a verdict at a time, and starts over once they have all landed", () => {
    vi.useFakeTimers();
    try {
      open();
      const rows = within(replay());
      expect(rows.getByText("1 of 5 judged")).toBeInTheDocument();

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS));
      expect(rows.getByText("2 of 5 judged")).toBeInTheDocument();

      // Three more steps reach the end, and the run is held there for a beat rather than
      // snapping straight back to the start: with nothing under the model there is a
      // finished ledger and a finished map, and they are worth a moment.
      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS * 3));
      expect(rows.getByText("5 of 5 judged")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS * 2));
      expect(rows.getByText("5 of 5 judged")).toBeInTheDocument();

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS));
      expect(rows.getByText("1 of 5 judged")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("draws the verdict that just landed, and the one under the model now", () => {
    vi.useFakeTimers();
    try {
      open();
      const rows = within(replay());
      expect(rows.getByText("The verdict that just landed")).toBeInTheDocument();
      expect(rows.getByText("Remove the boundary.")).toBeInTheDocument();
      expect(rows.getByText("judging…")).toBeInTheDocument();
      expect(rows.getAllByText("queued")).toHaveLength(3);
      // The bearings appear as each verdict lands and never before it: a policy count on a
      // boundary nothing has judged yet would be a number about nothing. Ledger rows only —
      // the map beside them writes the same count onto the node it belongs to.
      expect(rows.getAllByText(/^\d+\/53$/, { selector: "span" })).toHaveLength(1);

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS));
      expect(rows.getByText("Give this knowledge one owner.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("holds while the pointer is over it", () => {
    vi.useFakeTimers();
    try {
      open();
      const rows = within(replay());
      fireEvent.mouseEnter(replay());

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS * 3));
      expect(rows.getByText("1 of 5 judged")).toBeInTheDocument();

      fireEvent.mouseLeave(replay());
      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS));
      expect(rows.getByText("2 of 5 judged")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("holds while something inside it has focus", () => {
    vi.useFakeTimers();
    try {
      open();
      const rows = within(replay());
      fireEvent.focus(replay());

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS * 3));
      expect(rows.getByText("1 of 5 judged")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("is a still for a reader who has asked for less motion", () => {
    prefers(true);
    vi.useFakeTimers();
    try {
      open();
      const rows = within(replay());
      // Not step one frozen: the position that draws all four kinds of row at once.
      expect(rows.getByText(`${REPLAY_STILL} of 5 judged`)).toBeInTheDocument();

      act(() => vi.advanceTimersByTime(REPLAY_INTERVAL_MS * 5));
      expect(rows.getByText(`${REPLAY_STILL} of 5 judged`)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not announce itself", () => {
    // A loop with nothing at stake. A reader told every 2.7 seconds that another specimen
    // verdict has landed is being interrupted by a picture; the ledger is the accessible
    // text and it is read when the reader reaches it.
    open();

    expect(replay().querySelector("[aria-live]")).toBeNull();
    // The map says the same thing the ledger beside it does. A screen reader that read both
    // would hear the run twice.
    expect(replay().querySelector("svg[aria-hidden]")).toBeInTheDocument();
  });
});

describe("the page's own claims", () => {
  it("does not describe itself by where it runs", () => {
    open();

    // Nothing on this page positions the product as local, offline or bound to a port: it is
    // a workspace for architectural judgement, and the model behind it is the reader's.
    expect(document.body.textContent).not.toMatch(/local|127\.0\.0\.1|leaves your machine/i);
    expect(screen.getByText(/bring your own model — Gemini or Ollama/)).toBeInTheDocument();
  });
});
