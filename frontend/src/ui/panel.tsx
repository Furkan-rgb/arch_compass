import type { ElementType, ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * The one surface in the workbench. Everything else is composition: a header, a body, a
 * footer, and occasionally a tone. No boolean props for layout.
 */
export function Panel({
  children,
  className,
  as: Tag = "section",
  tone = "raised",
}: {
  children: ReactNode;
  className?: string;
  as?: ElementType;
  tone?: "raised" | "flat" | "sunken" | "marked";
}) {
  return (
    <Tag
      className={cn(
        "rounded-lg border",
        tone === "raised" && "border-rule bg-surface",
        tone === "flat" && "border-rule bg-surface",
        tone === "sunken" && "border-rule bg-sunken/60",
        tone === "marked" && "border-rule-strong bg-sunken",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function PanelHeader({
  title,
  description,
  actions,
  className,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 border-b border-rule px-4 py-3.5 sm:px-5",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 id={id} className="font-display text-[15px] font-semibold tracking-tight text-ink">
          {title}
        </h2>
        {description ? (
          // `wrap-anywhere` because this slot is where a workspace path ends up, and
          // `/Users/…/.archcompass/sources/audiobook_studio-4d76f8ca9623` is one word as far
          // as the line breaker is concerned — wider than a phone, and nothing a narrow box
          // can do about it. Breaking mid-path reads worse than truncating it, and better
          // than a page that scrolls sideways.
          <p className="mt-1 text-xs leading-5 text-ink-3 wrap-anywhere">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PanelBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("px-4 py-4 sm:px-5", className)}>{children}</div>;
}

/**
 * `rounded-b-lg` because the panel is no longer square.
 *
 * The footer is the only part of a panel that paints a background all the way to the edge,
 * so it is the only part that notices the 14px corner. Without it the tint squares off
 * outside the panel's own curve and the bottom two corners grow a small grey ear. The panel
 * cannot solve this with `overflow-hidden`: focus rings are drawn with `outline-offset`, and
 * a full-bleed row inside a panel would have half its ring clipped away.
 */
export function PanelFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn("rounded-b-lg border-t border-rule bg-sunken/40 px-4 py-3.5 sm:px-5", className)}
    >
      {children}
    </div>
  );
}

/** A label above a block of content. Used inside findings, context rails, and forms. */
export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "text-[10px] font-bold uppercase tracking-[0.14em] text-ink-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
