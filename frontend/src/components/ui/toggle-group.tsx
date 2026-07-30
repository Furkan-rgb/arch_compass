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
        "inline-flex w-fit items-center rounded-control border border-rule bg-sunken p-0.5",
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
        "inline-flex h-[22px] shrink-0 cursor-pointer items-center justify-center",
        "rounded-sm bg-transparent px-2 text-meta text-ink-2 whitespace-nowrap",
        "transition-[color,background-color] duration-[120ms]",
        "hover:text-ink",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        "data-[state=on]:bg-surface data-[state=on]:font-[550] data-[state=on]:text-ink data-[state=on]:shadow-lift",
        "disabled:cursor-not-allowed disabled:opacity-55",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0",
        className
      )}
      {...props}
    />
  )
}

export { ToggleGroup, ToggleGroupItem }
