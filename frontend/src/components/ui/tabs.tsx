import { Tabs as TabsPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/*
  Sections of one record, not destinations: the strip carries the rule the content hangs
  from, so moving between them never moves the page under the reader. The active section is
  marked by 2px of accent on that rule and nothing else — the registry's pill-in-a-well says
  "pick a mode", which is a different claim about what is below.

  The strip is chrome, so it bleeds back out through the page's own gutter and its rule runs
  the width of the column.

  The rule is an inset shadow rather than a border because the strip scrolls sideways when
  the sections outgrow a narrow window, and `overflow-x` cannot be authored alone: a box
  with one axis scrollable computes the other from `visible` to `auto`, so a border the
  active marker deliberately overlapped left a pixel of the strip scrollable up and down.
  A shadow takes no space to overlap, which is the same drawing with nothing to scroll.
*/
function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col", className)} {...props} />
}

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "flex gap-1 overflow-x-auto bg-chrome backdrop-blur-[var(--chrome-blur)] shadow-[inset_0_-1px_0_var(--rule)]",
        "mx-[calc(var(--gutter)*-1)] mb-[var(--gap-lg)] px-[var(--gutter)]",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "relative cursor-pointer border-0 bg-transparent",
        "px-3 py-[11px] text-ui text-ink-2 whitespace-nowrap",
        "transition-[color] duration-[120ms]",
        "hover:text-ink",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        "data-[state=active]:font-semibold data-[state=active]:text-[var(--chrome-active-ink)]",
        /* The marker is drawn rather than bordered, and inset ten pixels from each end so it
           marks the word instead of the whole hit area. Absolute and pinned to `bottom-0`,
           not `-1px`: it has to overlap the strip's rule without adding a pixel of scrollable
           height — see the note above about what a border cost here once. */
        "after:pointer-events-none after:absolute after:inset-x-2.5 after:bottom-0",
        "after:h-0.5 after:rounded-t-pill after:content-['']",
        "data-[state=active]:after:bg-primary",
        /* The count beside a section's name is a fact about it, in the face facts are
           stored in, and it must not reflow its own width as the run fills it in. */
        "[&_i]:ml-1 [&_i]:font-mono [&_i]:text-micro [&_i]:not-italic [&_i]:tabular-nums [&_i]:text-ink-3",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("pt-4 outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
