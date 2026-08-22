import type { ElementType, HTMLAttributes, ReactNode } from "react";

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
        // The rim is one inset hairline of light along the top edge — no blur, no offset,
        // nothing lifted off the page. On a black ground a hairline border alone loses the
        // top of a panel, because the border and the void meet at almost the same value;
        // the rim is the light that says where the surface starts. It is invisible in light
        // mode by design: `--rim` is transparent there, because a white panel on grey has
        // no edge to lose. `flat` is the same surface without it.
        tone === "raised" && "border-rule bg-surface shadow-rim",
        tone === "flat" && "border-rule bg-surface",
        // A sunken or marked region is set *into* a panel, so it gets no rim: a rim on an
        // inset would say the opposite of what the tone is for.
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

/**
 * A label above a block of content. Used inside findings, context rails, and forms.
 *
 * `0.13em` is the value the design system's type scale names, and this component is the
 * reason the value is written down once. The recipe — 10px, bold, uppercase, letterspaced —
 * was hand-rolled twenty-one times across fourteen files at five different tracking values,
 * including here, so the one element that is meant to look identical everywhere was the one
 * that drifted. `ui/design-system.test.ts` carries the rule that would catch the next copy.
 */
export function Label({
  children,
  className,
  as: Tag = "div",
  ...props
}: HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  className?: string;
  /**
   * The element to render as, because a `div` is not always valid where a label belongs.
   *
   * Two section headings on the reviews page kept hand-rolling the recipe purely because a
   * `div` inside an `<h2>` is invalid markup, and a rule that is easier to break than to obey
   * is a rule that gets broken. The colour and the mono variants stay `className`'s job —
   * a label in a verdict tone is still this label.
   */
  as?: ElementType;
}) {
  return (
    <Tag
      className={cn("text-[10px] font-bold uppercase tracking-[0.13em] text-ink-3", className)}
      {...props}
    >
      {children}
    </Tag>
  );
}
