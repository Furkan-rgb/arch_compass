import { Tooltip as TooltipPrimitive } from "radix-ui";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * A short explanation attached to a control, on hover **and on focus**.
 *
 * What this replaces is the `title` attribute, which the product reached for thirty times
 * and which is not an interface: it appears after a delay the reader cannot change, is drawn
 * by the operating system in a font that belongs to no design system, and never appears for a
 * keyboard. Where a `title` was the *only* route to a piece of information — a truncated
 * path, what a control does — that information was unreachable from the keyboard entirely.
 *
 * **It does not fix touch, and this docstring used to claim it did.** Radix's tooltip opens
 * on hover and on focus and does not open on a tap, by design, which is the same behaviour
 * `title` has. So on a phone or a tablet the two places the claim named as the *only* route
 * — the theme toggle's three-state sentence and the model chips' role-and-state note — are
 * still unreachable for a sighted touch user, though both do carry the sentence in
 * `aria-label`, so a screen reader gets it. The correction matters more than the gap: an
 * uncorrected claim is why the next component reaches for `Tooltip` believing touch is
 * handled. Where a tooltip is the only route to something, put the sentence on screen below
 * `sm`, or drive `open` from a tap on a coarse pointer at that call site.
 *
 * `title` is left alone where it duplicates something already on screen or already in the
 * accessible name. A tooltip repeating a visible label is a second thing to dismiss.
 *
 * Painted from `components/ui/select.tsx`'s open panel, because a tooltip and a menu are the
 * same kind of thing — a small surface summoned over the page — and two of them that look
 * different are two things a reader has to learn. `max-w-[36ch]` is a measure rather than a
 * width: past that a tooltip is a paragraph, and a paragraph belongs on the page.
 */
export function Tooltip({
  content,
  children,
  side = "top",
  className,
}: {
  /** The explanation. Kept to a sentence; anything longer is a paragraph on the page. */
  content: ReactNode;
  /** The control it explains. Rendered as itself — this adds no wrapper element. */
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}) {
  return (
    // Its own provider rather than one at the root: a tooltip is rare here and scattered,
    // and the shared "one opens, the rest follow instantly" behaviour a root provider buys
    // needs the tooltips to be neighbours, which none of ours are.
    <TooltipPrimitive.Provider delayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            sideOffset={6}
            collisionPadding={8}
            className={cn(
              "z-50 max-w-[36ch] rounded-sm border border-rule-strong bg-surface px-2.5 py-1.5",
              "font-sans text-[12px] leading-5 text-ink-2 shadow-rim wrap-anywhere",
              "data-open:animate-fade",
              className,
            )}
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
