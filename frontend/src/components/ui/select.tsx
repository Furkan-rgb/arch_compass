import { Select as SelectPrimitive } from "radix-ui";
import { Check, ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * A menu of alternatives, restyled onto this system's tokens.
 *
 * Vendored from shadcn — which is to say from Radix — rather than left as a native
 * `<select>`, for one reason that shows and one that does not. The one that shows: a native
 * select is drawn by the operating system, so its width is the widest option plus whatever
 * padding the platform feels like, and it will not sit at a control's height without
 * fighting. Ours was a wide box with the word "Comet" alone at the left of it. The one that
 * does not: an option list that is real markup can carry a check on the chosen row, follow
 * the type ramp, and be read the same way on every platform.
 *
 * Every colour here is this system's. The registry's palette is not defined in this project
 * and would be a second, silent theme if it were.
 */
function Select(props: React.ComponentProps<typeof SelectPrimitive.Root>) {
  return <SelectPrimitive.Root data-slot="select" {...props} />;
}

function SelectValue(props: React.ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value data-slot="select-value" {...props} />;
}

function SelectGroup({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Group>) {
  return <SelectPrimitive.Group data-slot="select-group" className={cn("p-1", className)} {...props} />;
}

/**
 * `w-fit`, so the trigger is as wide as what it says.
 *
 * The empty space in the old control was the native element's: the box was sized to the
 * longest option and the current one sat alone at the left of it. A trigger that is the
 * width of its own label puts the chevron where a reader expects it — immediately after the
 * word — and stops the row's spacing from being decided by whichever option has the most
 * letters.
 */
function SelectTrigger({
  className,
  size = "sm",
  children,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Trigger> & { size?: "sm" | "md" }) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        "inline-flex w-fit select-none items-center justify-between gap-1.5 whitespace-nowrap",
        // `--rule-control`, not `--rule-strong`. This trigger rests on `--control`, which in
        // light is the same white as the panel behind it, so the edge is the entire
        // affordance — and `--rule-strong` measured 1.41:1 against it, under the 3:1 a
        // boundary a reader has to find is held to. `--rule` and `--rule-strong` keep
        // structure, which is a quieter job.
        "rounded-sm border border-rule-control bg-control text-ink shadow-rim transition duration-150",
        "hover:bg-control-2",
        // No ring of its own, and no `outline-none` turning off the one the product declares
        // in `@layer base`. The registry's `ring-ink/20` composites to 1.57:1, so this was a
        // second, weaker focus treatment that won wherever it was written.
        "disabled:pointer-events-none disabled:border-rule-control disabled:bg-control disabled:text-ink-3 disabled:shadow-none",
        "data-[placeholder]:text-ink-3",
        size === "sm"
          ? "min-h-8 pointer-coarse:min-h-11 px-2.5 text-xs font-semibold"
          : "min-h-9 pointer-coarse:min-h-11 px-3 text-[13px] font-semibold",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown aria-hidden="true" className="size-3.5 shrink-0 text-ink-3" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

function SelectContent({
  className,
  children,
  position = "popper",
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        position={position}
        sideOffset={4}
        className={cn(
          "relative z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width)",
          "overflow-y-auto overflow-x-hidden rounded-md border border-rule-strong bg-surface text-ink shadow-rim",
          "origin-(--radix-select-content-transform-origin)",
          "data-open:animate-fade",
          className,
        )}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

function SelectLabel({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Label>) {
  return (
    <SelectPrimitive.Label
      data-slot="select-label"
      className={cn(
        "px-2 py-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-3",
        className,
      )}
      {...props}
    />
  );
}

function SelectItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex w-full cursor-default select-none items-center gap-2 rounded-sm",
        "min-h-8 pointer-coarse:min-h-11 py-1.5 pl-2 pr-7 text-[13px] text-ink-2 outline-none",
        "focus:bg-sunken focus:text-ink data-[state=checked]:text-ink data-[state=checked]:font-semibold",
        // An option that cannot be chosen is still an option a reader is meant to read — it
        // is telling them the alternative exists and is unavailable. `opacity-45` on
        // `--ink-2` took that sentence to roughly 2:1; `--ink-3` is the tier the token layer
        // measures at 5:1 or better on every ground, and the missing hover is what says the
        // row is inert.
        "data-disabled:pointer-events-none data-disabled:text-ink-3",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <span className="pointer-events-none absolute right-2 flex size-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check aria-hidden="true" className="size-3.5" />
        </SelectPrimitive.ItemIndicator>
      </span>
    </SelectPrimitive.Item>
  );
}

function SelectSeparator({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Separator>) {
  return (
    <SelectPrimitive.Separator
      data-slot="select-separator"
      className={cn("pointer-events-none -mx-1 my-1 h-px bg-rule", className)}
      {...props}
    />
  );
}

function SelectScrollUpButton({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollUpButton>) {
  return (
    <SelectPrimitive.ScrollUpButton
      data-slot="select-scroll-up-button"
      className={cn("flex cursor-default items-center justify-center bg-surface py-1", className)}
      {...props}
    >
      <ChevronUp aria-hidden="true" className="size-3.5 text-ink-3" />
    </SelectPrimitive.ScrollUpButton>
  );
}

function SelectScrollDownButton({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollDownButton>) {
  return (
    <SelectPrimitive.ScrollDownButton
      data-slot="select-scroll-down-button"
      className={cn("flex cursor-default items-center justify-center bg-surface py-1", className)}
      {...props}
    >
      <ChevronDown aria-hidden="true" className="size-3.5 text-ink-3" />
    </SelectPrimitive.ScrollDownButton>
  );
}

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
};
