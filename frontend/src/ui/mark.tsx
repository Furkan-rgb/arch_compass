import type { SVGProps } from "react";

import { cn } from "../lib/cn";
import type { MarkShape } from "../lib/format";

/**
 * The five shapes a descriptor can wear, drawn rather than typed.
 *
 * These were characters — `▲ ◆ ● ○ ◐` — and the reason they had to stop being characters is
 * that neither Onest nor IBM Plex Mono ships the Geometric Shapes block. Every one of them
 * fell back to whatever the operating system had, which is why they arrived at three
 * different optical sizes on three different baselines: a triangle sitting low and running
 * wide, a circle a third smaller than it, a diamond taller than both. Beside a word set in
 * 11px uppercase that reads as a rendering accident rather than as a mark.
 *
 * So they are one family now, drawn in one box: same optical area, same centre, same
 * softened corner from a rounded join. The shapes themselves are unchanged, because the
 * shape is the part that carries meaning without colour — a triangle for something to act
 * on, a diamond for something waiting, a circle for something settled, a ring for something
 * set aside, a half for something still running.
 *
 * Sized in `em` so a mark is always a fixed fraction of the text it sits beside, and
 * `aria-hidden` because in every one of these places the descriptor's own word is right
 * next to it.
 */

/** One 16×16 box, one centre, and three shapes tuned to the same optical weight in it. */
const PATHS: Record<MarkShape, string> = {
  // Matched by eye, not by area. With the 1.2 stroke around them these come out 9.9 wide by
  // 8.8 tall, 10.0 across the diagonal, and 9.2 across — which is the ratio a set of shapes
  // has to hold to look like one size, because points read as further out than they measure
  // and a circle reads as smaller than it is. The triangle also sits 0.35 low, so its
  // optical centre lands on the line rather than its bounding box.
  triangle: "M8 4.7 12.35 12.0H3.65Z",
  diamond: "M8 3.6 12.4 8 8 12.4 3.6 8Z",
  circle: "M8 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z",
  ring: "M8 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z",
  half: "M8 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z",
};

export function Mark({
  shape,
  className,
  ...props
}: { shape: MarkShape; className?: string } & SVGProps<SVGSVGElement>) {
  const hollow = shape === "ring" || shape === "half";
  return (
    <svg
      viewBox="0 0 16 16"
      // The same 1.2 stroke on every shape, joined round. On a filled shape it is what puts
      // the same small radius on a triangle's point and a diamond's corner; on the ring it
      // is the whole drawing. Without it the triangle is the only shape in the set with a
      // sharp vertex, and at 9px one sharp vertex among curves reads as a different family.
      fill={hollow ? "none" : "currentColor"}
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={cn("inline-block size-[1em] shrink-0", className)}
      {...props}
    >
      <path d={PATHS[shape]} />
      {shape === "half" ? (
        // The left half filled: a state that is under way rather than arrived at.
        <path d="M8 4a4 4 0 0 0 0 8Z" fill="currentColor" stroke="none" />
      ) : null}
    </svg>
  );
}
