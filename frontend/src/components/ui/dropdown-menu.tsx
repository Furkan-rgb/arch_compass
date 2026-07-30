import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/*
  The menu that drops out of a row's own control. It is the panel material — the same
  borderless-on-porcelain, hairlined-on-onyx sheet every other floating thing is made of —
  and it floats, so it spends the float shadow like the dialog and the drawer do.

  Trimmed to the two things this app's one menu is built from: an item and a label. The
  registry's checkbox, radio, sub-menu, shortcut and separator parts are gone rather than
  restyled; there is no menu here that answers a question or nests, and a vendored variant
  nobody calls is a design decision waiting to be made by accident.

  No entrance animation, for the reason the dialog states: it would be the only motion in a
  design that otherwise has none, and it arrived with a dependency this tree does not carry.
*/

function DropdownMenu({
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root data-slot="dropdown-menu" {...props} />
}

function DropdownMenuTrigger({
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return <DropdownMenuPrimitive.Trigger data-slot="dropdown-menu-trigger" {...props} />
}

function DropdownMenuContent({
  className,
  align = "end",
  sideOffset = 5,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        align={align}
        className={cn(
          "z-50 max-h-(--radix-dropdown-menu-content-available-height) min-w-[15em]",
          "overflow-x-hidden overflow-y-auto rounded-panel [border:var(--sheet-border)]",
          "bg-surface p-1 text-ink shadow-float",
          className
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  )
}

/* A control the width of the surface it drops out of, aligned with the sentence above it.
   The highlight is the surface's own sunken step for everything but the destructive item —
   what marks the row that cannot be undone is its hue, not a louder highlight. Radix moves
   `data-highlighted` for the pointer and the arrow keys alike, so there is one rule for both. */
function DropdownMenuItem({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Item> & {
  variant?: "default" | "destructive"
}) {
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-variant={variant}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-control p-2 text-body text-ink",
        "outline-none select-none",
        "data-highlighted:bg-sunken",
        "data-[variant=destructive]:text-danger",
        "data-[variant=destructive]:data-highlighted:bg-danger-soft",
        "data-disabled:pointer-events-none data-disabled:opacity-55",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0",
        className
      )}
      {...props}
    />
  )
}

/* Not an item: a sentence the items below are an answer to. It takes no highlight and no
   pointer, and it is the only thing in the menu set at the interface size. */
function DropdownMenuLabel({
  className,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Label>) {
  return (
    <DropdownMenuPrimitive.Label
      data-slot="dropdown-menu-label"
      className={cn("p-2 text-ui leading-[1.5] font-normal text-ink-2", className)}
      {...props}
    />
  )
}

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
}
