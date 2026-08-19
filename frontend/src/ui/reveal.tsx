import type { ElementType, ReactNode } from "react";

import { cn } from "../lib/cn";
import { useReveal } from "../lib/motion";

/**
 * Content that arrives as it is scrolled to. Used on the landing page and for the entrance
 * of app lists; never for anything that changes while the reader is looking at it.
 */
export function Reveal({
  children,
  delay = 0,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  /** Milliseconds, or an index when used inside a list — see `stagger`. */
  delay?: number;
  className?: string;
  as?: ElementType;
}) {
  const { ref, revealed } = useReveal();
  return (
    <Tag
      ref={ref}
      data-revealed={revealed || undefined}
      style={delay ? { "--reveal-delay": `${delay}ms` } : undefined}
      className={cn("reveal", className)}
    >
      {children}
    </Tag>
  );
}
