import { Dialog as DialogPrimitive } from "radix-ui"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

/*
  The one thing besides a drawer that floats above the page, so it is one of the two places
  the float shadow is spent. The backdrop is the sheet's own overlay token with the same 3px
  blur the drawer uses — a modal and a drawer darken the page the same amount or the reader
  learns two different meanings for "behind".

  No zoom, no fade: the registry's entrance animations are the only motion in a design that
  otherwise has none, and they arrived with a dependency (tw-animate-css) this tree does not
  carry.
*/
function Dialog({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({ ...props }: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

/*
  The backdrop, and also the scroller. The dialog sits inside it rather than beside it — the
  arrangement Radix documents for content that can be taller than the window, which one of
  these is: a case is eleven fields of prose and there is no height at which it stops being
  worth reading. Centred by the overlay's own grid, so a short dialog needs no transform and a
  tall one simply starts at the top of a page that scrolls.
*/
function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 z-50 grid items-center justify-items-center overflow-y-auto",
        "bg-overlay p-4 backdrop-blur-[3px]",
        className
      )}
      {...props}
    />
  )
}

function DialogContent({
  className,
  overlayClassName,
  children,
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & {
  showCloseButton?: boolean
  /* Where on the page this one sits, and how much room is left around it. The overlay owns
     both, because it is the box the dialog is placed in. */
  overlayClassName?: string
}) {
  return (
    <DialogPortal>
      <DialogOverlay className={overlayClassName}>
        <DialogPrimitive.Content
          data-slot="dialog-content"
          className={cn(
            // The gutter is the overlay's padding, so the width here is simply "all of it,
            // up to a reading measure" — no `calc` against the viewport, and one class for a
            // caller that needs a wider one.
            // Borderless on porcelain and hairlined on onyx, like every other panel: what
            // holds a floating dialog off the page by day is its shadow.
            "grid w-full max-w-md gap-3.5 rounded-panel [border:var(--sheet-border)] bg-surface p-6",
            "text-body text-ink shadow-float outline-none",
            className
          )}
          {...props}
        >
          {children}
          {showCloseButton && (
            <DialogPrimitive.Close data-slot="dialog-close" asChild>
              <Button size="icon" className="absolute top-4 right-4 border-0 bg-transparent">
                <X size={14} aria-hidden />
                <span className="sr-only">Close</span>
              </Button>
            </DialogPrimitive.Close>
          )}
        </DialogPrimitive.Content>
      </DialogOverlay>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-1", className)}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn("flex flex-wrap items-center gap-2 sm:justify-end", className)}
      {...props}
    />
  )
}

function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("font-display text-sub font-[650] tracking-[-.015em] text-ink", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-meta leading-[1.5] text-ink-2", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
