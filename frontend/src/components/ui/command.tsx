import { Command as CommandPrimitive } from "cmdk"
import { Search } from "lucide-react"

import { cn } from "@/lib/utils"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"

/*
  The palette. cmdk owns the filtering and the arrow keys; everything here is the material.

  Three things the registry shipped are gone rather than restyled. The input arrived wrapped
  in `InputGroup` — a second vendored file, 154 lines of it, to draw a magnifier beside a
  field — and the field this design wants is a row across the top of the sheet, not a
  bordered control inside one. Every item carried a tick set in reserved space on the right,
  which is a control for a menu that answers a question; this one goes places, and nothing it
  lists is ever the selected one. And the title lived *outside* the dialog's content, so the
  name a screen reader announces for the palette was not inside the thing being named.
*/

function Command({ className, ...props }: React.ComponentProps<typeof CommandPrimitive>) {
  return (
    <CommandPrimitive
      data-slot="command"
      className={cn("flex size-full min-h-0 flex-col overflow-hidden", className)}
      {...props}
    />
  )
}

/*
  Not centred. A palette is typed into, so it sits where a dropped-open field would — high
  enough that the list grows downwards into empty page rather than pushing the sheet around
  under the reader's hands.
*/
function CommandDialog({
  title,
  description,
  children,
  className,
  ...props
}: React.ComponentProps<typeof Dialog> & {
  title: string
  description: string
  className?: string
}) {
  return (
    <Dialog {...props}>
      <DialogContent
        overlayClassName="items-start pt-[14vh]"
        showCloseButton={false}
        className={cn("max-w-[560px] gap-0 overflow-hidden p-0", className)}
      >
        {/* Announced, not drawn: the field's own placeholder says the same thing in the
            place a sighted reader is already looking. */}
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <DialogDescription className="sr-only">{description}</DialogDescription>
        {children}
      </DialogContent>
    </Dialog>
  )
}

function CommandInput({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Input>) {
  return (
    <div
      data-slot="command-input-wrapper"
      className="flex flex-none items-center gap-2.5 border-b border-rule px-[18px]"
    >
      <Search size={15} aria-hidden className="flex-none text-ink-3" />
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          "h-[46px] w-full min-w-0 border-0 bg-transparent text-body text-ink outline-none",
          "placeholder:text-ink-3",
          className
        )}
        {...props}
      />
    </div>
  )
}

function CommandList({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.List>) {
  return (
    <CommandPrimitive.List
      data-slot="command-list"
      className={cn("max-h-[min(58vh,420px)] scroll-py-2 overflow-y-auto p-1.5", className)}
      {...props}
    />
  )
}

function CommandEmpty({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Empty>) {
  return (
    <CommandPrimitive.Empty
      data-slot="command-empty"
      className={cn("px-3.5 py-8 text-center text-meta text-ink-3", className)}
      {...props}
    />
  )
}

function CommandGroup({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="command-group"
      /* The same quiet small-caps heading `Group` draws over a division of a page: what
         this part of the list is, said softer than anything in it. */
      className={cn(
        "overflow-hidden",
        "**:[[cmdk-group-heading]]:px-3.5 **:[[cmdk-group-heading]]:pt-3 **:[[cmdk-group-heading]]:pb-1.5",
        "**:[[cmdk-group-heading]]:font-display **:[[cmdk-group-heading]]:text-micro",
        "**:[[cmdk-group-heading]]:font-[650] **:[[cmdk-group-heading]]:tracking-[.09em]",
        "**:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:text-ink-3",
        className
      )}
      {...props}
    />
  )
}

/* A row of the palette is a ledger row: the same height, the same gutter, the same hover.
   The keyboard's highlight and the pointer's are one thing — cmdk moves `data-selected` onto
   whichever row the pointer is over — so there is no second hover rule to disagree with it. */
function CommandItem({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Item>) {
  return (
    <CommandPrimitive.Item
      data-slot="command-item"
      className={cn(
        "group/command-item",
        "flex min-h-[var(--row-h)] cursor-pointer items-center gap-3 rounded-control",
        "px-[var(--row-pad-x)] text-ui text-ink outline-none select-none",
        "data-selected:bg-sunken",
        "data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:text-ink-3",
        "data-selected:[&_svg]:text-ink-2",
        className
      )}
      {...props}
    />
  )
}

export {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
}
