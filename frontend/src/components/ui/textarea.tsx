import { cn } from "@/lib/utils"

/*
  The field's twin, at the height of three lines and resizable down the vertical only —
  a box that widens tears the column it sits in. `field-sizing-content`, which the registry
  ships, is gone: a box that grows while it is being typed into moves everything under it,
  and every one of these sits above something the reader is comparing against.
*/
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        /* `block`, because a textarea is `inline-block` by default and an inline-level box
           picks up the line-height leading of whatever holds it — five stray pixels under
           every field that sits in normal flow rather than in a flex or grid row. */
        "block min-h-[76px] w-full resize-y rounded-control border border-rule bg-surface px-2.5 py-2",
        "text-ui leading-[1.55] text-ink placeholder:text-ink-3",
        "transition-[border-color,box-shadow] duration-[120ms]",
        "outline-none focus:border-primary focus:shadow-[0_0_0_2px_var(--accent-soft)]",
        "disabled:cursor-not-allowed disabled:opacity-55",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
