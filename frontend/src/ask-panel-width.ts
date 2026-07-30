/**
 * How wide the ask panel is, as a measurement the reader owns.
 *
 * The panel holds a conversation about code, and every grounded answer carries an excerpt of the
 * reader's own file. What "wide enough" means is therefore a property of their repository rather
 * than of this design: a 60-character Python module reads fine in the default, and a file that
 * wraps its arguments across four indents does not. It was widened once already, from 360px to
 * `clamp(400px, 32vw, 560px)`, on exactly that argument — and a second guess at a number is a
 * worse answer than a handle.
 *
 * The plumbing is the part worth stating, because the obvious implementation breaks the phone.
 * Two rules read one token: the drawer takes `--ask-panel-width` and `<main>` gives back
 * exactly the same, which is what stops the panel floating over the ledger it is about. At 860px
 * and below a media query sets that token to `100%` and the drawer becomes the page.
 *
 * So the drag must not write `--ask-panel-width`. An inline custom property on the root element
 * outranks every rule in the sheet, media query or not, so a width chosen on a desktop would
 * follow the reader onto a narrow window and leave the drawer stuck at 480px with the page
 * padded for it. Instead the root declares
 *
 *     --ask-panel-width: var(--ask-panel-width-user, clamp(400px, 32vw, 560px));
 *
 * and the drag writes `--ask-panel-width-user`. The narrow-window rule keeps assigning
 * `--ask-panel-width` directly, so it wins on specificity of *cascade order* rather than having
 * to beat an inline style — and both the drawer and the page padding still follow one token,
 * live, as it is dragged.
 *
 * Everything here is pure so it can be tested without a pointer: the clamp, the storage round
 * trip, and the decision about what to write are the parts that can be wrong in a way a person
 * would only find by dragging.
 */

export const ASK_PANEL_WIDTH_STORAGE_KEY = "archcompass.ask-panel-width";

/** The custom property the drag writes. Never `--ask-panel-width`; see above. */
export const ASK_PANEL_WIDTH_PROPERTY = "--ask-panel-width-user";

/**
 * The narrowest the panel may be dragged, in pixels.
 *
 * 360 is not an arbitrary floor: it is the width this panel used to be, and the reason it was
 * widened is that a code excerpt read through a slot at that size. Someone who wants it back is
 * entitled to it — they may be asking about prose rather than about code — but nothing should
 * make it *narrower* than the size already found to be too narrow.
 */
export const MIN_ASK_PANEL_WIDTH = 360;

/**
 * The widest, as a fraction of the window rather than a number of pixels.
 *
 * Two thirds. The panel is non-modal because the point is to read the ledger while asking about
 * it, and a panel that can cover the ledger quietly removes that — so the limit is the one that
 * keeps a column of review on screen at any window size, which a pixel cap cannot promise.
 */
export const MAX_ASK_PANEL_WIDTH_FRACTION = 2 / 3;

/** The window width at and below which the drawer is the page, and a handle resizes nothing. */
export const ASK_PANEL_FIXED_BELOW = 860;

export function maxAskPanelWidth(windowWidth: number): number {
  // Never below the floor, however small the window: a max under the min would make the clamp
  // below depend on which of the two it applied first.
  return Math.max(MIN_ASK_PANEL_WIDTH, Math.round(windowWidth * MAX_ASK_PANEL_WIDTH_FRACTION));
}

/** A dragged width brought inside the range the panel is allowed to occupy. */
export function clampAskPanelWidth(width: number, windowWidth: number): number {
  if (!Number.isFinite(width)) return MIN_ASK_PANEL_WIDTH;
  return Math.min(Math.max(Math.round(width), MIN_ASK_PANEL_WIDTH), maxAskPanelWidth(windowWidth));
}

/** Whether a window is wide enough for the width to mean anything. */
export function askPanelIsResizable(windowWidth: number): boolean {
  return windowWidth > ASK_PANEL_FIXED_BELOW;
}

/**
 * The width the drag is aiming at, from where the pointer is.
 *
 * The panel is pinned to the right edge, so its width is the distance from the pointer to that
 * edge. Measured against `innerWidth` rather than the panel's own box: the box is what is being
 * changed, so reading it mid-drag would make each frame depend on the last and accumulate the
 * difference between where the pointer is and where the handle ended up.
 */
export function askPanelWidthFromPointer(clientX: number, windowWidth: number): number {
  return clampAskPanelWidth(windowWidth - clientX, windowWidth);
}

/** A stored width, or `null` where nothing usable was stored. */
export function storedAskPanelWidth(storage: Pick<Storage, "getItem">): number | null {
  const saved = Number(storage.getItem(ASK_PANEL_WIDTH_STORAGE_KEY));
  // `Number("")` is 0 and `Number(null)` is 0, so a missing key and a corrupt one both fail the
  // same check and both mean "no preference" — which is the default, not an error to report.
  return Number.isFinite(saved) && saved >= MIN_ASK_PANEL_WIDTH ? saved : null;
}

/**
 * Put a width on the document, or take the reader's choice off it again.
 *
 * `null` removes the property rather than writing the default into it, and that is the whole
 * point of the two-token arrangement: with nothing set, `--ask-panel-width` falls through to the
 * `clamp()` in its own declaration, so a reset restores a responsive default rather than
 * freezing today's computed value.
 */
export function applyAskPanelWidth(root: HTMLElement, width: number | null): void {
  if (width === null) root.style.removeProperty(ASK_PANEL_WIDTH_PROPERTY);
  else root.style.setProperty(ASK_PANEL_WIDTH_PROPERTY, `${width}px`);
}

export function saveAskPanelWidth(
  storage: Pick<Storage, "setItem" | "removeItem">,
  width: number | null,
): void {
  if (width === null) storage.removeItem(ASK_PANEL_WIDTH_STORAGE_KEY);
  else storage.setItem(ASK_PANEL_WIDTH_STORAGE_KEY, String(width));
}
