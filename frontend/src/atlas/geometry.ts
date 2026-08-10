/** The arithmetic the map is drawn and moved by: where an edge curves, and how far the camera may go. */

import { NODE_HEIGHT, NODE_WIDTH } from "../atlas-layout";

/**
 * Low enough that "fit to view" can actually fit a large graph. A map of a few hundred cards
 * is wider than any viewport, and a floor that stops short of it turns the fit control into a
 * control that shows the reader one corner and calls it the whole.
 */
export const MIN_ZOOM = .15;
export const MAX_ZOOM = 1.8;
export const ZOOM_STEP = .15;

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
