import type { ReactNode } from "react";
import { useRef } from "react";

import { cn } from "../lib/cn";
import { useScrollEdges } from "../lib/motion";

export type TabItem = { id: string; label: string; count?: number };

/**
 * A tablist with arrow-key roving focus, because a workbench is driven from the keyboard as
 * often as from the pointer.
 */
export function Tabs({
  items,
  active,
  onChange,
  label,
  className,
  variant = "line",
}: {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
  variant?: "line" | "solid";
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const { ref: scrollRef, edges } = useScrollEdges<HTMLDivElement>();

  /**
   * Left and right walk, Home and End jump.
   *
   * The two jumps are part of the tablist pattern rather than an extra, and they are worth
   * more here than in most tablists: the review's strip runs to five or six tabs on a narrow
   * column, where it scrolls, and "back to the first one" was six keystrokes past the edge
   * of what is on screen.
   */
  function onKeyDown(event: React.KeyboardEvent) {
    const index = items.findIndex((item) => item.id === active);
    if (index === -1) return;

    let target: number;
    if (event.key === "ArrowRight") target = (index + 1) % items.length;
    else if (event.key === "ArrowLeft") target = (index - 1 + items.length) % items.length;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = items.length - 1;
    else return;

    event.preventDefault();
    const next = items[target];
    onChange(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`#tab-${next.id}`)?.focus();
  }

  const list = (
    <div
      ref={(node) => {
        listRef.current = node;
        scrollRef.current = node;
      }}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      data-edge-left={variant === "line" ? edges.left : undefined}
      data-edge-right={variant === "line" ? edges.right : undefined}
      className={cn(
        "flex gap-1",
        // The two variants run out of room differently. A line of tabs is a rule across the
        // panel and cannot wrap without stranding the underline on a row above it, so it
        // scrolls. A solid strip is a box of pills with nothing to align to, so it wraps —
        // and it has to: "Indexed 43 · Browse · Clone · Examples" is 373px, which does not
        // fit any phone, and it was scrolling with `scrollbar-none` hiding the fact. The
        // last tab was simply cut in half at the edge of a padded card.
        //
        // The line variant still scrolls, and now it says so. `scrollbar-none` on its own is
        // how the same defect survived here: macOS keeps overlay scrollbars hidden until the
        // trackpad is touched, so at 390px the review's strip read "Docket Rounds Atlas Delta
        // Report A" — a first-class surface reduced to a stray letter that looks like a
        // rendering fault. `.scroll-edge-x` is the horizontal twin of the fade the vertical
        // scrollers already use, driven by the same hook. It has to sit on this element and
        // the rule has to sit on the wrapper below, or the mask fades the ends of a line that
        // runs the width of the panel.
        //
        // The track is `bg-sunken` and the tabs are pills on it, which is what
        // `components/ui/toggle-group.tsx` draws for a one-of-many set. Two pickers answering
        // the same question and drawn two different ways are two pickers a reader has to
        // learn separately.
        variant === "line"
          ? "scroll-edge-x scrollbar-none overflow-x-auto"
          : "flex-wrap rounded-sm border border-rule bg-sunken p-0.5",
        variant === "solid" && className,
      )}
    >
      {items.map((item) => {
        const selected = item.id === active;
        return (
          <button
            key={item.id}
            id={`tab-${item.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`panel-${item.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-sm font-semibold transition",
              variant === "line"
                ? cn(
                    // `py-3`, not `py-2.5`: at 10px the row measured 42px on a phone, two
                    // short of the 44px floor, and a tab has the room for the other two.
                    // `px-2` below `sm` buys 8px a tab back across six tabs, which is what
                    // pulls the review's last surface inside a 390px viewport at all.
                    "-mb-px border-b-2 px-2 py-3 sm:px-3",
                    // The hover takes emphasis off rather than adding chrome. Both states
                    // used to be a 2px underline resolving to `text-ink`, so for the seconds
                    // a pointer rested on a neighbour the only thing separating "you are
                    // here" from "you are pointing at this" was the underline's *hue* — on
                    // the review page's primary navigation, which is the one thing the
                    // colour rule exists to prevent. The selected tab is now the only 2px
                    // underline on the strip.
                    selected
                      ? "border-accent text-ink"
                      : "border-transparent text-ink-3 hover:text-ink",
                  )
                : cn(
                    // Same touch floor as a small button, and for the same reason: on
                    // `/start` this strip is the whole navigation and a phone gets a finger.
                    "min-h-8 pointer-coarse:min-h-11 rounded-sm border px-3",
                    // What is on is raised, not inverted. This was `bg-ink text-canvas` —
                    // the loudest fill the system can draw, and in dark the selected pill
                    // was a solid `#fafafa` slab brighter than anything else on the page,
                    // sitting in a `bg-surface` track on a `bg-surface` panel that had no
                    // shape of its own. The recipe here is the one `ToggleButton` and the
                    // vendored Radix switch already share: the control film, a control's
                    // edge, a rim along the top, full-strength ink.
                    selected
                      ? "border-rule-control bg-control text-ink shadow-rim"
                      : "border-transparent text-ink-3 hover:bg-sunken hover:text-ink",
                  ),
            )}
          >
            {item.label}
            {item.count === undefined ? null : (
              // One branch, not two. The second existed only to survive the inverted slab —
              // a count on a near-black pill had to be painted in the canvas colour — and it
              // went with it.
              <span className="rounded-xs bg-sunken px-1.5 py-0.5 text-[10px] font-bold text-ink-3 tabular-nums">
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );

  // The rule belongs to the panel, the scroll belongs to the strip, and they cannot be the
  // same element: a horizontal mask on the element carrying `border-b` fades the ends of the
  // rule, which reads as the panel's own edge failing to paint.
  return variant === "line" ? (
    <div className={cn("border-b border-rule", className)}>{list}</div>
  ) : (
    list
  );
}

export function TabPanel({
  id,
  active,
  children,
  className,
}: {
  id: string;
  active: string;
  children: ReactNode;
  className?: string;
}) {
  if (id !== active) return null;
  return (
    <div
      id={`panel-${id}`}
      role="tabpanel"
      aria-labelledby={`tab-${id}`}
      tabIndex={0}
      // `tabIndex={0}` is how a keyboard user reaches a panel whose content is not itself
      // focusable, and `outline-none` used to sit beside it — a utility, which beats the base
      // `:focus-visible` rule the whole product's focus indicator lives in. So every one of
      // these was a tab stop that showed nothing when it received focus: tab out of the
      // tablist and the indicator simply vanished for one press, on the review's five
      // surfaces, the context rail's four, the repository picker and the policy editor.
      //
      // The offset is negative rather than absent, which is the device `.atlas-canvas` uses:
      // a panel is flush against the strip above it, so a ring drawn 2px outside would be
      // clipped by whichever neighbour it overhangs.
      className={cn("animate-fade focus-visible:-outline-offset-2", className)}
    >
      {children}
    </div>
  );
}
