import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";

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
 * here. "Everywhere" is true on any route; the other two are only true on a docket, and
 * saying so is cheaper than a sheet that changes shape with the route and leaves a reader
 * unsure whether a key is gone or was never there.
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
    title: "Deciding",
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
 * The same recipe the decision bar prints on its buttons. It is not shared with that one on
 * purpose — there the cap sits on an ink fill and borrows `border-current`; here it sits on
 * a panel and takes the rule.
 */
function KeyCap({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex min-w-6 items-center justify-center rounded-xs border border-rule-strong bg-control px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-4 text-ink shadow-rim">
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
                <ul className="mt-1.5 divide-y divide-rule">
                  {group.shortcuts.map((entry) => (
                    <li
                      key={entry.id}
                      className="flex items-baseline justify-between gap-4 py-1.5"
                    >
                      <span className="min-w-0 text-[13px] text-ink-2">{entry.does}</span>
                      <span className="flex shrink-0 items-center gap-1">
                        {entry.caps.map((cap, index) => (
                          <KeyCap key={index}>{cap}</KeyCap>
                        ))}
                      </span>
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
