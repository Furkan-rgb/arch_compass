import { cn } from "@/lib/utils"

/*
  34px, one rule around it, and the accent only on focus — where it means "this is the field
  taking what you type" rather than "press this". The focus mark is a 2px halo in the accent's
  softest tint rather than an outline, so a field in a dense row does not shove its neighbours.
*/
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-[var(--h-field)] w-full min-w-0 rounded-control border border-rule bg-surface px-2.5",
        "text-ui text-ink placeholder:text-ink-3",
        "transition-[border-color,box-shadow] duration-[120ms]",
        "outline-none focus:border-primary focus:shadow-[0_0_0_2px_var(--accent-soft)]",
        "disabled:cursor-not-allowed disabled:opacity-55",
        className
      )}
      {...props}
    />
  )
}

export { Input }
