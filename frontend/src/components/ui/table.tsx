import { cn } from "@/lib/utils"

/*
  Rows of one shape being compared. It scrolls sideways inside its own container rather than
  widening the page, because a source path is as long as someone's filesystem happens to be —
  the caller sets the min-width at which the columns stop squeezing, since only the caller
  knows how many there are.

  A header is 11px uppercase on the sunken well; a header is the one place this design
  shouts, because it is a label for a column rather than a piece of content.
*/
function Table({
  className,
  containerClassName,
  ...props
}: React.ComponentProps<"table"> & {
  /* For the caller whose sheet is already the scroller. A table inside a scrolling sheet
     would otherwise scroll within it and put the scrollbar between the last row and the
     sentence under the table, rather than at the foot of the sheet that is scrolling —
     `overflow-visible` hands the overflow back to whatever holds this. */
  containerClassName?: string
}) {
  return (
    <div
      data-slot="table-container"
      className={cn("w-full overflow-x-auto", containerClassName)}
    >
      <table
        data-slot="table"
        className={cn("w-full border-collapse text-meta", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={cn(className)} {...props} />
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child>td]:border-b-0", className)}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn("transition-colors duration-[120ms]", className)}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "border-b border-rule bg-sunken px-4 py-2 text-left align-middle",
        "text-micro font-[650] tracking-[.06em] text-ink-3 uppercase whitespace-nowrap",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn("border-b border-rule-soft px-4 py-2.5 align-top", className)}
      {...props}
    />
  )
}

function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-2 text-meta text-ink-3", className)}
      {...props}
    />
  )
}

export { Table, TableHeader, TableBody, TableHead, TableRow, TableCell, TableCaption }
