import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

/*
  A control is 28px and does not move when the pointer arrives: hover shifts colour and
  border, nothing else. What the registry shipped instead — a translate on :active, a ring
  blooming three pixels out of the edge, a fill fading to 80% — made every secondary action
  look like the thing to press.

  The focus ring is the sheet's own: 2px of accent, offset 2px, the same ring every other
  focusable thing on the page draws.
*/
const buttonVariants = cva(
  [
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5",
    "rounded-control border font-[550] whitespace-nowrap",
    "transition-[color,background-color,border-color] duration-[120ms]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:cursor-not-allowed disabled:opacity-55",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        default: "border-rule bg-surface text-ink not-disabled:hover:border-ink-3",
        /* The one control on a screen that commits something is the only one that is
           filled, so it is the only one that carries the accent as a background. */
        primary:
          "border-transparent bg-primary text-on-accent not-disabled:hover:bg-accent-ink",
        /* Stopping a run is a thing that should change, so it borrows the revision family
           rather than bringing a fourth hue onto the screen. Quiet until the pointer
           arrives, then it fills: the colour is the confirmation. */
        destructive:
          "border-danger-rule bg-danger-soft text-danger not-disabled:hover:border-danger not-disabled:hover:bg-danger not-disabled:hover:text-on-accent",
      },
      size: {
        default: "min-h-7 px-3 text-meta",
        icon: "size-7 p-0",
      },
    },
    compoundVariants: [
      /* Primary is also the only control taller than the rest, and that is a fact about the
         design rather than about the caller — so it carries its own height here instead of
         standing as a size anyone can ask for. There is no 32px secondary button in this
         design, and a size named `lg` would invite one. */
      { variant: "primary", size: "default", class: "min-h-8 px-4 text-ui" },
      /* An icon alone is quieter than a word: it starts at the second ink and only reaches
         the first under the pointer. */
      { variant: "default", size: "icon", class: "text-ink-2 not-disabled:hover:text-ink" },
    ],
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
