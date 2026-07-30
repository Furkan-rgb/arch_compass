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
        /* No padding at all: the three parts inside — the field, the list, the hints — each
           run the full width of the panel, and the panel's radius is what crops them. */
        className={cn("max-w-[min(600px,92vw)] gap-0 overflow-hidden p-0", className)}
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
    /* One 48px row, and no control drawn inside it. A palette is a sheet you type into: the
       field is the top of the sheet, the magnifier sits in the sheet's own gutter, and the
       hairline under it is the only edge. A bordered pill here would draw a second box inside
       a box, and a focus ring would light the one element in the app that cannot be anything
       but focused. The gutter is 20px so the magnifier lands in the same column as the
       items' icons below it, and the caret in the same column as their titles. */
    <div
      data-slot="command-input-wrapper"
      className="flex h-12 flex-none items-center gap-2.5 border-b border-rule px-5"
    >
      <Search size={15} aria-hidden className="flex-none text-ink-3" />
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          // The base sheet gives every `input` a border, a radius, a padding and a focus
          // shadow. All four are unsaid here rather than overridden downstream.
          "h-full w-full min-w-0 rounded-none border-0 bg-transparent p-0 shadow-none",
          "text-body text-ink outline-none placeholder:text-ink-3",
          "focus:border-0 focus:shadow-none",
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
      className={cn("max-h-[min(58vh,420px)] scroll-py-2 overflow-y-auto p-2", className)}
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
      className={cn("px-3 py-6 text-center text-meta text-ink-3", className)}
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
         this part of the list is, said softer than anything in it. Type only — no band, no
         rule. A heading that paints its own ground turns a list into a table of contents. */
      className={cn(
        "overflow-hidden",
        "**:[[cmdk-group-heading]]:px-3 **:[[cmdk-group-heading]]:pt-3 **:[[cmdk-group-heading]]:pb-1",
        "**:[[cmdk-group-heading]]:font-display **:[[cmdk-group-heading]]:text-micro",
        "**:[[cmdk-group-heading]]:font-[650] **:[[cmdk-group-heading]]:tracking-[.09em]",
        "**:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:text-ink-3",
        className
      )}
      {...props}
    />
  )
}

/* A row of the palette is not a ledger row. A ledger is read down a column and its rows are
   records, so they get a record's height and a record's rule; these are destinations, forty
   pixels of nothing with one of them lit. Only the lit one is drawn at all — no rule beneath a
   row, no ground under an unselected one — because in a list you arrow through, anything
   painted on more than one row is a stripe competing with the cursor.

   `data-[selected=true]`, with the value written out. cmdk marks every row it renders, the
   unselected ones as `data-selected="false"` — so the bare `data-selected:` variant, which
   asks whether the attribute is *there*, lit all of them and turned the list into the bands
   this replaces.

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
        "flex min-h-10 cursor-pointer items-center gap-2.5 rounded-control",
        "bg-transparent px-3 text-ui text-ink outline-none select-none",
        "data-[selected=true]:bg-palette-hover",
        "data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:text-ink-3",
        "data-[selected=true]:[&_svg]:text-ink-2",
        className
      )}
      {...props}
    />
  )
}

/*
  The keys, at the bottom edge. Two things at once: the arrow keys and Enter are the whole
  interface here and are worth saying once, and a list that scrolls needs a floor — without
  one the last row is cut off mid-height and reads as a rendering fault rather than as more
  list. Hidden from the a11y tree: the dialog's description already says what this is, and
  "↑↓ · ↵ · esc" announced glyph by glyph is noise.
*/
function CommandFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="command-footer"
      aria-hidden
      className={cn(
        "flex h-[34px] flex-none items-center justify-end gap-3 border-t border-rule px-3.5",
        "font-mono text-micro text-ink-3",
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
  CommandFooter,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
}
