import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/*
  A segmented control: a small closed set where one answer is already true, drawn as a well
  sunk into the surface with the current answer lifted out of it. Small on purpose — it
  filters or switches a view, it never commits anything, and at button height it would read
  as three things to press.

  One geometry, no variants. The registry's spacing/orientation/outline matrix described
  five controls this design does not have; a caller that needs a square item (an icon
  alone) says so with `className`, which is one line at the one place it is true.

  The stock `toggle` primitive it was built on went with them: nothing here toggles alone.
*/
function ToggleGroup({
  className,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root>) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      className={cn(
        // The well, and no rule around it: by day the surface it is sunk into is what marks
        // its edge, and by night the well is a lift of white that needs no help being seen.
        "inline-flex w-fit items-center gap-0.5 rounded-[calc(var(--r-control)+2px)] bg-sunken p-[3px]",
        className
      )}
      {...props}
    />
  )
}

function ToggleGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(
        "inline-flex min-h-[25px] shrink-0 cursor-pointer items-center justify-center",
        "rounded-control bg-transparent px-2.5 py-[3px] text-meta text-ink-2 whitespace-nowrap",
        "transition-[color,background-color] duration-[120ms]",
        "hover:text-ink",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        /* The pressed segment, straight off the flip tokens: by day a white chip that
           stands off the well on a one-pixel shadow, by night the well itself lit to ten
           percent white — because a white chip on onyx reads as a hole, not a lift. */
        "data-[state=on]:bg-[var(--seg-on)] data-[state=on]:font-[550]",
        "data-[state=on]:text-[var(--seg-on-ink)] data-[state=on]:shadow-[var(--seg-shadow)]",
        "disabled:cursor-not-allowed disabled:opacity-55",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0",
        className
      )}
      {...props}
    />
  )
}

export { ToggleGroup, ToggleGroupItem }
