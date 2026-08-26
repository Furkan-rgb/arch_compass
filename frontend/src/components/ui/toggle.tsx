import { Toggle as TogglePrimitive } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * One switch, restyled onto this system's tokens.
 *
 * Vendored from shadcn for the behaviour — roving focus, arrow-key traversal, the pressed
 * state announced as a real toggle — and repainted, because the registry's palette
 * (`bg-muted`, `text-foreground`, `border-input`) does not exist in this project and the two
 * colour systems must not both be live in one interface.
 *
 * What is *on* is raised; what is off is plain text. A filled `bg-ink` chip is the loudest
 * thing a screen can draw, and a row of five of them — which is what "every relationship is
 * drawn" looks like at rest — reads as five alarms rather than as a setting nobody has
 * touched. So a pressed switch wears the `secondary` button's recipe: the control film, a rim
 * along its top edge, full-strength ink and a hairline.
 *
 * The border is what carries the state, not the fill. In light the control film *is* the
 * panel colour — both are white — so a filled-versus-unfilled distinction is invisible there
 * however it is written. An edge that appears is legible in both themes, which is the test a
 * state has to pass here: one gesture, not one colour. That edge is `--rule-control` rather
 * than `--rule-strong`, because it is the whole affordance and a 1.41:1 hairline is under the
 * 3:1 a boundary a reader has to find is held to — the same move `secondary` and
 * `ToggleButton` made, and the reason all three still look like one control.
 */
const toggleVariants = cva(
  cn(
    "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-sm border",
    "font-semibold transition duration-150",
    "border-transparent bg-transparent text-ink-3",
    "hover:bg-sunken hover:text-ink",
    "data-[state=on]:border-rule-control data-[state=on]:bg-control data-[state=on]:text-ink data-[state=on]:shadow-rim",
    // No `outline-none` and no ring of its own. The registry shipped
    // `focus-visible:ring-ink/20`, which composites to 1.57:1 — under the 3:1 an indicator is
    // held to — and, worse, it turned off the one focus rule the product declares in
    // `@layer base` to do it. Two focus treatments in one interface, and the weaker of them
    // won wherever this component was used. The base ink outline paints a switch now, exactly
    // as it paints a `Button`.
    //
    // Off is drawn, not dimmed, for the reason `ui/button.tsx` sets out at length: an alpha
    // composites the label *and* its ground toward whatever is behind them, so `opacity-40`
    // took a switch that is telling you a count is zero down to about 1.9:1 — the least
    // readable text on the strip, and the one the reader was meant to be told.
    //
    // The recipe is `ToggleButton`'s rather than `Button`'s, and the difference matters here:
    // a button's off state takes the control film because a button is a filled control at
    // rest, while this one's resting state has no fill at all. Painting the film on a
    // *disabled* switch would draw the state that means on. So it keeps the unpressed look,
    // loses the pointer, and sets its label at `--ink-3`, which `tokens.test.ts` measures at
    // 5:1 or better on every ground in both themes.
    "disabled:pointer-events-none disabled:border-transparent disabled:bg-transparent disabled:text-ink-3 disabled:shadow-none",
  ),
  {
    variants: {
      size: {
        // 44px is a *touch* requirement, so it is answered on a coarse pointer and nowhere
        // else — the same split `Button`'s `sm` size makes.
        sm: "min-h-8 pointer-coarse:min-h-11 px-2.5 text-xs",
        md: "min-h-9 pointer-coarse:min-h-11 px-3 text-[13px]",
      },
    },
    defaultVariants: { size: "sm" },
  },
);

function Toggle({
  className,
  size,
  ...props
}: React.ComponentProps<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={cn(toggleVariants({ size }), className)}
      {...props}
    />
  );
}

export { Toggle, toggleVariants };
