import { NODE_HEIGHT, NODE_WIDTH } from "./layout";

/** The arithmetic the map is drawn and moved by: where an edge curves, and how far the camera may go. */

/**
 * Low enough that "fit to view" can actually fit a large graph. A map of a few hundred cards
 * is wider than any viewport, and a floor that stops short of it turns the fit control into a
 * control that shows the reader one corner and calls it the whole.
 */
export const MIN_ZOOM = 0.15;

/**
 * The size the label on a card is set at, and the smallest a reader should be asked to read it.
 *
 * The first is `.atlas-node__label`'s own `font-size`; the second is the floor the comment
 * below has always named. They are here rather than in the stylesheet because the fit control
 * is arithmetic on them, and a number the code cannot see is a number the code cannot honour.
 */
export const LABEL_SIZE = 13;
export const MIN_LABEL_SIZE = 8;

/**
 * The scale a card stops being readable below, and therefore the floor on the *automatic* fit.
 *
 * A card is 190 by 78 with a 13px label. Below about this the map becomes a picture of where
 * things are rather than of what they are — which is a legitimate thing to want, and the zoom
 * control goes there. It is not what a surface should choose on the reader's behalf before
 * they have looked at anything.
 *
 * Derived rather than asserted. This was `0.45` under a comment naming seven pixels as the
 * floor, which is 5.85 — the number and the reason for it had drifted apart, and since a
 * review's neighbourhood lays out larger than the canvas, that drifted number *was* the
 * default view of the Atlas on a desktop. Dividing one constant by the other is what stops
 * them drifting again: move either size and the floor follows.
 */
export const READABLE_ZOOM = MIN_LABEL_SIZE / LABEL_SIZE;
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

export function edgeKindClass(kind: string) {
  return kind.replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "").toLocaleLowerCase();
}
