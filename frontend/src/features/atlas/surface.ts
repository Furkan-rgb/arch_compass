import { clamp } from "./geometry";
import { NODE_HEIGHT, NODE_WIDTH, type AtlasLayout } from "./layout";

/**
 * How much surface the map draws, and where the graph sits in it.
 *
 * A graph smaller than the panel used to paint its ground and its grid over its own bounds
 * only, which left a hard edge partway across an otherwise empty canvas — the map appearing
 * to stop rather than the canvas continuing — with the graph pinned to the top-left corner of
 * whatever room was left. So the drawn surface is the graph or the canvas, whichever is
 * larger, and the graph is centred in what it did not need.
 *
 * The origin moves but the scale does not: `viewport.ts` maps a world point to a scroll
 * offset by multiplying by the zoom, and an offset here is non-zero only on an axis where the
 * surface is exactly the canvas — an axis with nothing to scroll, where every one of those
 * sums already clamps to zero. That is what makes moving the origin safe.
 */
export type AtlasSurface = {
  width: number;
  height: number;
  /** How far right and down the whole world is shifted, in world units. Never negative. */
  offsetX: number;
  offsetY: number;
};

export function surfaceFor(
  layout: AtlasLayout,
  canvas: { width: number; height: number },
  zoom: number,
): AtlasSurface {
  const width = Math.max(layout.width, canvas.width / zoom);
  const height = Math.max(layout.height, canvas.height / zoom);
  const drawn = drawnBounds(layout);
  return {
    width,
    height,
    // Clamped to the room the layout box left over, so the box itself is never pushed off
    // the surface by a graph that sits far from its own origin.
    offsetX: clamp((width - drawn.width) / 2 - drawn.x, 0, width - layout.width),
    offsetY: clamp((height - drawn.height) / 2 - drawn.y, 0, height - layout.height),
  };
}

/**
 * The rectangle the reader can actually see: every card, and every cluster region round them.
 *
 * `layout.width` and `layout.height` are the surface the placement claimed, floored at a
 * minimum so a two-card graph is never a postage stamp. That floor is empty space on one
 * side, so it is not what a graph is centred on.
 */
export function drawnBounds(layout: AtlasLayout): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  const include = (x: number, y: number, width: number, height: number) => {
    left = Math.min(left, x);
    top = Math.min(top, y);
    right = Math.max(right, x + width);
    bottom = Math.max(bottom, y + height);
  };
  layout.positions.forEach((position) =>
    include(position.x, position.y, NODE_WIDTH, NODE_HEIGHT),
  );
  layout.clusters.forEach((cluster) =>
    include(cluster.x, cluster.y, cluster.width, cluster.height),
  );
  if (left === Infinity) return { x: 0, y: 0, width: layout.width, height: layout.height };
  return { x: left, y: top, width: right - left, height: bottom - top };
}
