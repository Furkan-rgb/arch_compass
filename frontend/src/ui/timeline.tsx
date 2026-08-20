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
      <span
        aria-hidden="true"
        className={cn(
          "absolute left-0 top-[calc(0.75rem+1px)] size-[15px] rounded-full border-[3px] border-canvas",
          current ? "bg-ink ring-2 ring-rule-strong" : "bg-rule-strong",
        )}
      />
      {children}
    </li>
  );
}
