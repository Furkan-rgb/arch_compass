/**
 * The handle on the ask panel's edge.
 *
 * What is checked here is the part jsdom can actually answer: that the control exists and
 * announces itself, that it writes the token the media query can still beat, that a keyboard
 * reaches the same widths a mouse does, and that none of it is offered on a window where the
 * drawer is the page. The gesture itself — capture, cursor, live reflow — is not something jsdom
 * has, and the arithmetic behind it is tested without a pointer in `ask-panel-width.test.ts`.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { AskPanel } from "./ask-panel";
import {
  ASK_PANEL_WIDTH_PROPERTY,
  ASK_PANEL_WIDTH_STORAGE_KEY,
  MIN_ASK_PANEL_WIDTH,
} from "./ask-panel-width";

/** jsdom reports 1024 by default; these tests state the width they mean. */
function windowWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
  fireEvent(window, new Event("resize"));
}

function renderPanel() {
  vi.spyOn(api, "reviewConversations").mockResolvedValue([]);
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AskPanel reviewId="rev-1" open onClose={() => undefined} />
    </QueryClientProvider>,
  );
}

const handle = () => screen.getByRole("separator", { name: "Resize the question panel" });
const applied = () =>
  document.documentElement.style.getPropertyValue(ASK_PANEL_WIDTH_PROPERTY);

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  window.localStorage.clear();
  document.documentElement.style.removeProperty(ASK_PANEL_WIDTH_PROPERTY);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  document.documentElement.style.removeProperty(ASK_PANEL_WIDTH_PROPERTY);
});

describe("the ask panel's resize handle", () => {
  it("is a separator with an orientation, a range and a label", () => {
    renderPanel();

    // A resizer between two regions is what it is: it separates the conversation from the review
    // it is about. Not a slider — nothing here is a value chosen from a range for its own sake.
    const grip = handle();
    expect(grip.getAttribute("aria-orientation")).toBe("vertical");
    expect(grip.getAttribute("aria-valuemin")).toBe(String(MIN_ASK_PANEL_WIDTH));
    expect(grip.getAttribute("aria-valuemax")).toBe("960");
    expect(grip.tabIndex).toBe(0);
  });

  it("reports no current value until the reader has chosen one", () => {
    renderPanel();

    // Before a drag the width is a responsive expression, not a number. Announcing whatever it
    // computes to today would claim a precision that is not there.
    expect(handle().hasAttribute("aria-valuenow")).toBe(false);
  });

  it("widens with the left arrow, because that is where the handle travels", () => {
    renderPanel();

    fireEvent.keyDown(handle(), { key: "ArrowLeft" });

    // Started from the panel's measured width, which jsdom reports as 0, so the first press
    // lands on the floor plus a step — clamped either way. What matters is the direction and
    // that the value is now announced.
    expect(applied()).not.toBe("");
    expect(handle().hasAttribute("aria-valuenow")).toBe(true);
  });

  it("takes the two limits from Home and End", () => {
    renderPanel();

    fireEvent.keyDown(handle(), { key: "End" });
    expect(applied()).toBe(`${MIN_ASK_PANEL_WIDTH}px`);
    expect(handle().getAttribute("aria-valuenow")).toBe(String(MIN_ASK_PANEL_WIDTH));

    fireEvent.keyDown(handle(), { key: "Home" });
    expect(applied()).toBe("960px");
  });

  it("narrows towards the floor and stops there", () => {
    renderPanel();

    fireEvent.keyDown(handle(), { key: "Home" });
    for (let press = 0; press < 40; press += 1) {
      fireEvent.keyDown(handle(), { key: "ArrowRight", shiftKey: true });
    }

    expect(applied()).toBe(`${MIN_ASK_PANEL_WIDTH}px`);
  });

  it("writes the user token and leaves the one the media query owns alone", () => {
    // The failure this exists to stop is invisible on a desktop: an inline `--ask-panel-width`
    // outranks the 860px rule, so a width chosen here would follow the reader onto a phone.
    renderPanel();

    fireEvent.keyDown(handle(), { key: "Home" });

    expect(document.documentElement.style.getPropertyValue("--ask-panel-width-user")).toBe("960px");
    expect(document.documentElement.style.getPropertyValue("--ask-panel-width")).toBe("");
  });

  it("follows the pointer live, and only stores where the edge came to rest", () => {
    // The drag writes the custom property every frame — the drawer's width and the page column's
    // padding both read the token it feeds, so one declaration reflows both — and touches storage
    // once, at the end. Sixty synchronous writes a second to move an edge would be sixty writes
    // too many.
    renderPanel();
    const grip = handle();

    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 960 });
    fireEvent.pointerMove(grip, { pointerId: 1, clientX: 940 });
    expect(applied()).toBe("500px");
    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBeNull();

    fireEvent.pointerMove(grip, { pointerId: 1, clientX: 900 });
    expect(applied()).toBe("540px");

    fireEvent.pointerUp(grip, { pointerId: 1 });
    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBe("540");
    expect(handle().getAttribute("aria-valuenow")).toBe("540");
  });

  it("clamps a pointer dragged past either limit", () => {
    renderPanel();
    const grip = handle();

    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 960 });
    fireEvent.pointerMove(grip, { pointerId: 1, clientX: -400 });
    expect(applied()).toBe("960px");

    fireEvent.pointerMove(grip, { pointerId: 1, clientX: 2000 });
    expect(applied()).toBe(`${MIN_ASK_PANEL_WIDTH}px`);
    fireEvent.pointerUp(grip, { pointerId: 1 });
  });

  it("suppresses selection for the length of the drag and no longer", () => {
    // Without it the gesture selects the conversation behind the handle and the reader finishes a
    // resize with half a thread highlighted. A standing `select-none` would instead cost them
    // copying an answer, which is a thing people do with these.
    renderPanel();
    const grip = handle();

    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 960 });
    expect(document.body.style.userSelect).toBe("none");

    fireEvent.pointerUp(grip, { pointerId: 1 });
    expect(document.body.style.userSelect).toBe("");
  });

  it("ignores a press that is not the primary button", () => {
    renderPanel();
    const grip = handle();

    fireEvent.pointerDown(grip, { button: 2, pointerId: 1, clientX: 960 });
    fireEvent.pointerMove(grip, { pointerId: 1, clientX: 900 });

    expect(applied()).toBe("");
  });

  it("stores nothing for a press that never moved", () => {
    // Which is what keeps a double-click a reset: the second press of it would otherwise store
    // whatever width the pointer happened to be over and undo the reset a moment later.
    renderPanel();
    const grip = handle();

    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 960 });
    fireEvent.pointerUp(grip, { pointerId: 1 });

    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBeNull();
    expect(applied()).toBe("");
  });

  it("remembers the width and restores it on the next visit", () => {
    const first = renderPanel();
    fireEvent.keyDown(handle(), { key: "End" });
    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBe(
      String(MIN_ASK_PANEL_WIDTH),
    );

    first.unmount();
    document.documentElement.style.removeProperty(ASK_PANEL_WIDTH_PROPERTY);
    renderPanel();

    expect(applied()).toBe(`${MIN_ASK_PANEL_WIDTH}px`);
  });

  it("gives back the responsive default on a double-click, storage and all", () => {
    renderPanel();
    fireEvent.keyDown(handle(), { key: "End" });

    fireEvent.doubleClick(handle());

    // Removed, not set to a number: with nothing here the token falls through to its own
    // `clamp()`, so the panel is responsive again rather than frozen at today's computed width.
    expect(applied()).toBe("");
    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBeNull();
    expect(handle().hasAttribute("aria-valuenow")).toBe(false);
  });

  it("refits an applied width when the window shrinks, without forgetting the choice", () => {
    renderPanel();
    fireEvent.keyDown(handle(), { key: "Home" });
    expect(applied()).toBe("960px");

    windowWidth(1000);

    // Clipped to what fits. The preference in storage is untouched, so widening the window again
    // gives back what they picked rather than the ceiling it was clipped to.
    expect(applied()).toBe("667px");
    expect(window.localStorage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY)).toBe("960");
  });

  it("keeps the announced maximum in step with the window", () => {
    // The ceiling is a fraction of the window, so a handle that only re-rendered when the
    // resizable threshold was crossed would tell a screen reader the maximum for whatever size
    // the window was when the panel opened.
    renderPanel();
    expect(handle().getAttribute("aria-valuemax")).toBe("960");

    windowWidth(1200);

    expect(handle().getAttribute("aria-valuemax")).toBe("800");
  });

  it("is not offered at all where the drawer is the page", () => {
    // The sheet hides it below the same measurement. This is what stops a focused handle
    // answering arrow keys there and writing a width the narrow-window rule correctly ignores —
    // a control quietly doing nothing is worse than one that is not there.
    renderPanel();
    expect(handle()).toBeTruthy();

    windowWidth(720);

    expect(screen.queryByRole("separator", { name: "Resize the question panel" })).toBeNull();
  });
});
