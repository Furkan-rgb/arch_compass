import { NODE_HEIGHT, NODE_WIDTH } from "./layout";

/** The arithmetic the map is drawn and moved by: where an edge curves, and how far the camera may go. */

/**
 * Low enough that "fit to view" can actually fit a large graph. A map of a few hundred cards
 * is wider than any viewport, and a floor that stops short of it turns the fit control into a
 * control that shows the reader one corner and calls it the whole.
 */
export const MIN_ZOOM = 0.15;

/**
 * The sizes a card's two text rows are set at, and the smallest a reader should be asked to
 * read.
 *
 * The first two are `.atlas-node__label`'s and `.atlas-node__meta`'s own `font-size`; the
 * third is the floor the comment below has always named. They are here rather than in the
 * stylesheet because the fit control and the card's own truncation are arithmetic on them,
 * and a number the code cannot see is a number the code cannot honour. The two files are one
 * decision: move a size in `styles.css` and the constant beside it has to move with it.
 */
export const LABEL_SIZE = 13;
export const META_SIZE = 10;
export const MIN_LABEL_SIZE = 8;

/** `.atlas-node__meta`'s own `letter-spacing`, in em. Tracking is most of what a row costs. */
export const META_TRACKING = 0.06;

/** `.atlas-clusters text`, the same pair, for the same reason. */
export const CLUSTER_LABEL_SIZE = 14;
export const CLUSTER_LABEL_TRACKING = 0.13;

/**
 * The scale a card stops being readable below, and therefore the floor on the *automatic* fit.
 *
 * A card is 190 by 78 with a 13px label over a 10px meta row. Below about this the map becomes
 * a picture of where things are rather than of what they are — which is a legitimate thing to
 * want, and the zoom control goes there. It is not what a surface should choose on the
 * reader's behalf before they have looked at anything.
 *
 * Derived rather than asserted, and derived from the *smallest* row rather than the largest.
 * It was `0.45` under a comment naming seven pixels as the floor, which is 5.85; dividing
 * `MIN_LABEL_SIZE` by `LABEL_SIZE` fixed that drift but kept the assumption that the 13px
 * label is the smallest thing on a card. It is not — the meta row carries the namespace and
 * the *word half of the verdict*, and at 0.615 a 10px row landed at 6.2px, so the default
 * view of this surface had the hue carrying the verdict on its own. That is the one thing the
 * charter says a hue may never do. Against `META_SIZE` the smallest row on the card lands at
 * eight pixels and the label at 10.4. Fewer cards fit at rest, which is the trade the fit
 * control's own comment in `viewport.ts` already accepts in writing.
 */
export const READABLE_ZOOM = MIN_LABEL_SIZE / META_SIZE;
export const MAX_ZOOM = 1.8;
export const ZOOM_STEP = 0.15;

export function pointerDistance(
  first: { x: number; y: number },
  second: { x: number; y: number },
) {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

/** The curve from one card to another, leaving whichever side faces the other card. */
export function edgePath(
  source: { x: number; y: number },
  target: { x: number; y: number },
) {
  const sourceCenterX = source.x + NODE_WIDTH / 2;
  const sourceCenterY = source.y + NODE_HEIGHT / 2;
  const targetCenterX = target.x + NODE_WIDTH / 2;
  const targetCenterY = target.y + NODE_HEIGHT / 2;
  const vertical = Math.abs(targetCenterY - sourceCenterY) >= NODE_HEIGHT;
  if (vertical) {
    const downward = targetCenterY > sourceCenterY;
    const startY = source.y + (downward ? NODE_HEIGHT : 0);
    const endY = target.y + (downward ? 0 : NODE_HEIGHT);
    const middleY = (startY + endY) / 2;
    return `M ${sourceCenterX} ${startY} C ${sourceCenterX} ${middleY}, ${targetCenterX} ${middleY}, ${targetCenterX} ${endY}`;
  }
  const rightward = targetCenterX > sourceCenterX;
  const startX = source.x + (rightward ? NODE_WIDTH : 0);
  const endX = target.x + (rightward ? 0 : NODE_WIDTH);
  const middleX = (startX + endX) / 2;
  return `M ${startX} ${sourceCenterY} C ${middleX} ${sourceCenterY}, ${middleX} ${targetCenterY}, ${endX} ${targetCenterY}`;
}

export function distance(
  left: { x: number; y: number },
  right: { x: number; y: number },
) {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

export function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

/** How text is cut to fit a card, and how a relationship kind becomes a class name. */
export function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

/**
 * How wide one character of IBM Plex Mono is, in user units, at a size and a tracking.
 *
 * Every string drawn on the canvas is cut to a character count, and a count is only ever
 * right for the size it was chosen against. A cluster's name ran a hundred units past the
 * enclosure it was naming because `34` had been picked for a font-size that moved twice
 * afterwards, and the card's meta row overprinted itself for the same reason. So a budget is
 * measured rather than remembered: 0.6em is the family's advance, and mono is the property of
 * every glyph having the same one.
 */
export const MONO_ADVANCE = 0.6;

export function monoAdvance(size: number, tracking = 0) {
  return size * (MONO_ADVANCE + tracking);
}

/** How many characters fit in `width` user units at that size, never fewer than one. */
export function fitCharacters(width: number, size: number, tracking = 0) {
  return Math.max(1, Math.floor(width / monoAdvance(size, tracking)));
}

export function edgeKindClass(kind: string) {
  return kind.replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "").toLocaleLowerCase();
}
