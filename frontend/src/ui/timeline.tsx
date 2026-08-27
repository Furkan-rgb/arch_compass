import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * A vertical sequence with a rule running through it: case revisions, review lineage,
 * clarification rounds. The marker is drawn by the item so the current entry can carry a
 * different one without the list knowing about it.
 */
export function Timeline({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <ol
      className={cn(
        "relative grid gap-0 before:absolute before:bottom-4 before:left-[7px] before:top-4 before:w-px before:bg-rule",
        // A connector between one thing and nothing is a claim that a second revision exists.
        // The rail is drawn unconditionally on the list, so a lineage of one — which is what
        // most reviews are, under a heading that says "One immutable revision" — painted a
        // stub running out of the only dot into blank card.
        "[&:has(>li:only-child)]:before:hidden",
        className,
      )}
    >
      {children}
    </ol>
  );
}

export function TimelineItem({
  children,
  current,
  className,
}: {
  children: ReactNode;
  current?: boolean;
  className?: string;
}) {
  return (
    <li className={cn("relative pl-7", className)}>
      {/* The border is the knock-out that lets the dot cut the connector behind it, so it has
          to be the colour of what the dot is sitting on. `--canvas` is the page, and both
          timelines in the product sit inside a panel — so the knock-out painted `#f5f5f5`
          against `#ffffff` and read as a grey collar around every dot.

          No ring either. The current entry is already the only ink-filled dot on the rail,
          and a ring around a circle is the device the design system records as saying
          nothing — here it was a second grey ring outside the first. */}
      <span
        aria-hidden="true"
        className={cn(
          "absolute left-0 top-[calc(0.75rem+1px)] size-[15px] rounded-full border-[3px] border-surface",
          current ? "bg-ink" : "bg-rule-strong",
        )}
      />
      {children}
    </li>
  );
}
