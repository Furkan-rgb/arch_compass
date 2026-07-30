import { cn } from "@/lib/utils"

/*
  A bar standing in for a value that has not landed yet. Static, unlike the registry's:
  a pulse here would be the only motion on a page whose whole subject is not moving yet,
  and it would be drawing the eye to the one thing there is nothing to read.
*/
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("rounded-sm bg-rule-soft", className)}
      {...props}
    />
  )
}

export { Skeleton }
