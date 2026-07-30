import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

/*
  A chip states a fact about the thing beside it. Sentence case at 11px/600: shouting it in
  uppercase gave a piece of metadata more voice than the title it was attached to.

  Four variants, and the names are the meanings. `neutral` and `accent` are quiet outlines —
  a fact, and a fact you can act on. `material` and `cleared` are the two verdicts, and they
  are loud on purpose: they appear nowhere but on a verdict, so nothing else on the screen
  can be mistaken for one. The registry's `default` (a filled accent chip) is gone with them,
  because a filled accent means "press me" everywhere else in this design.
*/
const badgeVariants = cva(
  [
    "inline-flex w-fit items-center gap-1 rounded-pill border px-2.5 py-0.5",
    "text-micro font-[650] tracking-[.04em] whitespace-nowrap",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "[&>svg]:pointer-events-none [&>svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        neutral: "border-rule bg-surface text-ink-2",
        accent: "border-accent-rule bg-accent-soft text-accent-ink",
        material: "border-danger-rule bg-danger-soft text-danger",
        cleared: "border-cleared-rule bg-cleared-soft text-cleared",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
)

function Badge({
  className,
  variant = "neutral",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
