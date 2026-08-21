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
 * state has to pass here: one gesture, not one colour.
 */
const toggleVariants = cva(
  cn(
    "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-sm border",
    "font-semibold transition duration-150",
    "border-transparent bg-transparent text-ink-3",
    "hover:bg-sunken hover:text-ink",
    "data-[state=on]:border-rule-strong data-[state=on]:bg-control data-[state=on]:text-ink data-[state=on]:shadow-rim",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/20",
    "disabled:pointer-events-none disabled:opacity-40",
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
