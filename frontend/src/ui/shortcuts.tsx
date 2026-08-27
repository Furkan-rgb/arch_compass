import type { HTMLAttributes, ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";

import { cn } from "../lib/cn";
import { isPlainShortcut } from "../lib/keyboard";
import { useOverlay } from "../lib/motion";
import { Button } from "./button";
import { ArrowDown, ArrowUp } from "./icons";
import { Label } from "./panel";

type Shortcut = { id: string; caps: ReactNode[]; does: string };

/**
 * The keys, in one place, said once.
 *
 * The only sentence in the product that taught the keyboard sat *below* every row on the
 * docket — forty rows past the list the shortcuts exist to move through — and named four of
 * the six keys it supports. A reader who never scrolled to the end of a review never learnt
 * that the review had a keyboard at all.
 *
 * Grouped by scope rather than by key, because that is the question being asked: what works
 * here. "Everywhere" is true on any route; the other three name the surface they are true on,
 * which is cheaper than a sheet that changes shape with the route and leaves a reader unsure
 * whether a key is gone or was never there. The last of them used to be called "Deciding" —
 * an activity where its three siblings named a place — so nothing on the sheet said where
 * A, P and W are live.
 *
 * The two ways down the list are one row rather than two, because they are one shortcut with
 * two keys on it — and the arrows are drawn from `ui/icons.tsx` rather than typed, which is
 * the same rule that applies to every other mark in the product.
 */
const GROUPS: Array<{ title: string; shortcuts: Shortcut[] }> = [
  {
    title: "Everywhere",
    shortcuts: [
      { id: "palette", caps: ["⌘", "K"], does: "Search reviews, repositories and sections" },
      { id: "help", caps: ["?"], does: "This list" },
      { id: "escape", caps: ["Esc"], does: "Close what is open" },
    ],
  },
  {
    title: "The docket",
    shortcuts: [
      { id: "down", caps: ["j", <ArrowDown key="down" />], does: "Down the list, opening what it lands on" },
      { id: "up", caps: ["k", <ArrowUp key="up" />], does: "Back up the list" },
      { id: "select", caps: ["x"], does: "Select the open row, to decide several at once" },
    ],
  },
  {
    title: "Reading the map",
    shortcuts: [
      { id: "match", caps: ["n"], does: "The next element matching what you searched for" },
      // "Shift" as a word rather than the glyph: `design-system.test.ts` refuses a pasted
      // symbol because it falls back to the system font, and ⌘ is the one exception the
      // allowlist makes — a Mac keyboard prints it on the key and nothing prints ⇧ on Shift.
      { id: "match-back", caps: ["Shift", "n"], does: "The previous one" },
    ],
  },
  {
    title: "An open docket row",
    shortcuts: [
      { id: "accept", caps: ["A"], does: "Accept and act on the open finding" },
      { id: "park", caps: ["P"], does: "Park it for later" },
      { id: "waive", caps: ["W"], does: "Waive it — asks for a reason first" },
    ],
  },
];

/**
 * Bound at the document, behind the same guards as ⌘K.
 *
 * `?` is Shift and `/` on most layouts, so the modifier guard has to let Shift through — see
 * `isPlainShortcut`. The modal guard is what stops this stacking over the palette or the
 * context drawer, and it is also what makes pressing `?` a second time a no-op rather than
 * a re-open: the sheet itself is `aria-modal`, and Escape is how it closes.
 */
export function useShortcutSheet() {
  const [isOpen, setOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "?" || !isPlainShortcut(event)) return;
      event.preventDefault();
      setOpen(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return {
    isOpen,
    open: useCallback(() => setOpen(true), []),
    close: useCallback(() => setOpen(false), []),
  };
}

/**
 * A key cap: a literal keystroke rather than a word, so it is set in mono.
 *
 * One recipe with a ground, rather than a recipe per call site. There were five hand-rolled
 * `<kbd>`s at three sizes — 10px, 10.5px and 11px — with four borders and three inks between
 * them, and four of the five sat below 11px, which is the smallest mono step the type scale
 * has. At 10px IBM Plex Mono inside a 1px box stops reading as a cap at all.
 *
 * `on` is what actually differed between them, and it is a fact about what the cap is resting
 * on rather than about what a cap is. That is the argument for a prop instead of a copy: the
 * sheet's caps sit on a panel and take the control edge and the control fill; the rail's sit
 * on the band, which does not invert with the theme and has neither.
 *
 * There is a third ground — `border-current` over an ink fill, which the decision bar prints
 * on its own buttons — and it is deliberately not here yet. A variant with no call site is a
 * variant nobody has checked; it belongs in this prop the day that file adopts it.
 */
export function KeyCap({
  on = "surface",
  className,
  children,
  ...props
}: HTMLAttributes<HTMLElement> & { on?: "surface" | "band"; children: ReactNode }) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-6 items-center justify-center rounded-xs border px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-4",
        on === "surface" && "border-rule-control bg-control text-ink shadow-rim",
        on === "band" && "border-band-rule text-band-ink-2",
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  );
}

export function ShortcutSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useOverlay(open, onClose);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      <div className="absolute inset-0 bg-overlay" aria-hidden="true" onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="animate-expand relative flex max-h-[70vh] w-full max-w-md flex-col overflow-hidden rounded-lg border border-rule bg-surface shadow-float"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-rule px-4 py-3.5">
          <h2 className="font-display text-base font-semibold tracking-tight">
            Keyboard shortcuts
          </h2>
          <Button variant="ghost" size="sm" className="min-h-11" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="scrollbar-slim min-h-0 flex-1 overflow-y-auto px-4 py-3.5">
          <div className="grid gap-5">
            {GROUPS.map((group) => (
              <section key={group.title}>
                <Label>{group.title}</Label>
                {/* The key first, in a fixed track. This is the one list in the product that
                    is keyed on a keystroke, and it led with the sentence and hung the caps off
                    the right edge — where a row carrying two caps and a row carrying one do
                    not line up, so neither column could be scanned. Finding `W` meant reading
                    eleven sentences. The charter's rule is to lead with the identifier and
                    keep the sentence beneath it; here the identifier is the key. */}
                <ul className="mt-1.5 divide-y divide-rule">
                  {group.shortcuts.map((entry) => (
                    <li key={entry.id} className="flex items-baseline gap-3 py-1.5">
                      <span className="flex w-20 shrink-0 items-center justify-end gap-1">
                        {entry.caps.map((cap, index) => (
                          <KeyCap key={index}>{cap}</KeyCap>
                        ))}
                      </span>
                      <span className="min-w-0 text-[13px] text-ink-2">{entry.does}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
