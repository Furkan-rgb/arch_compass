/**
 * The width the reader chooses for the ask panel, and the plumbing that keeps it desktop-only.
 *
 * Two things can go wrong here and only one of them is arithmetic. The other is the cascade: the
 * drag must write `--ask-panel-width-user` and never `--ask-panel-width`, because an inline
 * custom property on the root outranks every rule in the sheet including the media query that
 * turns the drawer into the page below 860px — so a width chosen on a desktop would follow the
 * reader onto a phone and leave the panel stuck at 480px with the page padded for it.
 *
 * That failure is invisible on the machine it was written on, which is exactly the kind worth a
 * test naming it.
 */

import { afterEach, describe, expect, it } from "vitest";

import {
  applyAskPanelWidth,
  ASK_PANEL_FIXED_BELOW,
  ASK_PANEL_WIDTH_PROPERTY,
  ASK_PANEL_WIDTH_STORAGE_KEY,
  askPanelIsResizable,
  askPanelWidthFromPointer,
  clampAskPanelWidth,
  MIN_ASK_PANEL_WIDTH,
  maxAskPanelWidth,
  saveAskPanelWidth,
  storedAskPanelWidth,
} from "./ask-panel-width";

/** A storage stand-in, so a test never depends on what a previous one left behind. */
function storage(initial: Record<string, string> = {}) {
  const held = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => held.get(key) ?? null,
    setItem: (key: string, value: string) => void held.set(key, value),
    removeItem: (key: string) => void held.delete(key),
    held,
  };
}

afterEach(() => {
  document.documentElement.style.removeProperty(ASK_PANEL_WIDTH_PROPERTY);
  document.documentElement.style.removeProperty("--ask-panel-width");
});

describe("the property the drag writes", () => {
  it("is the user token, never the one the media query owns", () => {
    // The whole reason there are two tokens. `--ask-panel-width` is assigned directly by the
    // narrow-window rule; if the drag wrote that one, an inline style would beat the media query
    // and the panel would stay desktop-width on a phone.
    expect(ASK_PANEL_WIDTH_PROPERTY).toBe("--ask-panel-width-user");

    applyAskPanelWidth(document.documentElement, 480);

    expect(document.documentElement.style.getPropertyValue("--ask-panel-width-user")).toBe("480px");
    expect(document.documentElement.style.getPropertyValue("--ask-panel-width")).toBe("");
  });

  it("removes the choice rather than writing today's default into it", () => {
    // With nothing set, `--ask-panel-width` falls through to the `clamp()` in its own
    // declaration. Writing a number on reset would freeze whatever that clamp happened to
    // compute on this window and make the panel non-responsive for good.
    applyAskPanelWidth(document.documentElement, 480);

    applyAskPanelWidth(document.documentElement, null);

    expect(document.documentElement.style.getPropertyValue(ASK_PANEL_WIDTH_PROPERTY)).toBe("");
    expect(document.documentElement.getAttribute("style") ?? "").not.toContain("clamp");
  });
});

describe("clampAskPanelWidth", () => {
  it("will not go under the width the panel was already found to be too narrow at", () => {
    // 360 is what this panel used to be, and the reason it was widened is that a code excerpt
    // read through a slot at that size. Someone may want it back; nothing should go below it.
    expect(MIN_ASK_PANEL_WIDTH).toBe(360);
    expect(clampAskPanelWidth(200, 1440)).toBe(360);
    expect(clampAskPanelWidth(-40, 1440)).toBe(360);
  });

  it("keeps a column of review on screen, as a fraction rather than a pixel cap", () => {
    // The panel is non-modal because the point is to read the ledger while asking about it, so
    // the ceiling has to scale — a fixed cap that leaves room at 1440 covers the page at 900.
    expect(clampAskPanelWidth(2000, 1440)).toBe(960);
    expect(clampAskPanelWidth(2000, 900)).toBe(600);
    expect(maxAskPanelWidth(1440)).toBe(960);
  });

  it("never lets the ceiling fall below the floor", () => {
    // A window narrower than the minimum would otherwise produce a max under the min, and the
    // result would depend on which of the two clamps applied first.
    expect(maxAskPanelWidth(400)).toBe(MIN_ASK_PANEL_WIDTH);
    expect(clampAskPanelWidth(500, 400)).toBe(MIN_ASK_PANEL_WIDTH);
  });

  it("rounds to whole pixels and refuses a number that is not one", () => {
    expect(clampAskPanelWidth(480.6, 1440)).toBe(481);
    expect(clampAskPanelWidth(Number.NaN, 1440)).toBe(MIN_ASK_PANEL_WIDTH);
    expect(clampAskPanelWidth(Number.POSITIVE_INFINITY, 1440)).toBe(MIN_ASK_PANEL_WIDTH);
  });
});

describe("askPanelWidthFromPointer", () => {
  it("measures from the right edge, because that is the edge the panel is pinned to", () => {
    expect(askPanelWidthFromPointer(960, 1440)).toBe(480);
    expect(askPanelWidthFromPointer(1440, 1440)).toBe(MIN_ASK_PANEL_WIDTH);
  });

  it("is clamped, so a pointer dragged off the window does not take the panel with it", () => {
    expect(askPanelWidthFromPointer(-200, 1440)).toBe(960);
    expect(askPanelWidthFromPointer(2000, 1440)).toBe(MIN_ASK_PANEL_WIDTH);
  });
});

describe("askPanelIsResizable", () => {
  it("agrees with the measurement the sheet turns the drawer into the page at", () => {
    expect(ASK_PANEL_FIXED_BELOW).toBe(860);
    expect(askPanelIsResizable(861)).toBe(true);
    expect(askPanelIsResizable(860)).toBe(false);
    expect(askPanelIsResizable(390)).toBe(false);
  });
});

describe("the stored preference", () => {
  it("round-trips a width", () => {
    const held = storage();

    saveAskPanelWidth(held, 520);

    expect(held.held.get(ASK_PANEL_WIDTH_STORAGE_KEY)).toBe("520");
    expect(storedAskPanelWidth(held)).toBe(520);
  });

  it("reads nothing as no preference rather than as a width", () => {
    // `Number("")` and `Number(null)` are both 0, so a missing key and a corrupt one fail the
    // same check — and "no preference" is the default, not something to report.
    expect(storedAskPanelWidth(storage())).toBeNull();
    expect(storedAskPanelWidth(storage({ [ASK_PANEL_WIDTH_STORAGE_KEY]: "" }))).toBeNull();
    expect(storedAskPanelWidth(storage({ [ASK_PANEL_WIDTH_STORAGE_KEY]: "wide" }))).toBeNull();
    expect(storedAskPanelWidth(storage({ [ASK_PANEL_WIDTH_STORAGE_KEY]: "12" }))).toBeNull();
  });

  it("is cleared by a reset rather than set to the default number", () => {
    const held = storage({ [ASK_PANEL_WIDTH_STORAGE_KEY]: "520" });

    saveAskPanelWidth(held, null);

    expect(held.held.has(ASK_PANEL_WIDTH_STORAGE_KEY)).toBe(false);
    expect(storedAskPanelWidth(held)).toBeNull();
  });
});
