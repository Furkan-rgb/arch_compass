import { createContext, useContext } from "react";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import { type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { toggleVariants } from "@/components/ui/toggle";

/**
 * A set of switches that belong together, and are traversed as one control.
 *
 * Vendored from shadcn and repainted; `toggle.tsx` carries the reasoning for how a switch
 * shows its state. The variant here is about the *set*, not the switch, which is why the
 * switches themselves have only one look:
 *
 * - `segment` is one-of-many — which lens — and gets a sunken track. The track is what says
 *   these are alternatives, so choosing one un-chooses the rest.
 * - `chips` is many-of-many — which relationships to draw, what to leave out — and gets no
 *   track, because a bar drawn around switches that can all be on or all be off would claim
 *   a choice between them that does not exist.
 */
export type ToggleGroupVariant = "segment" | "chips";

const ToggleGroupContext = createContext<VariantProps<typeof toggleVariants>>({ size: "sm" });

function ToggleGroup({
  className,
  variant = "segment",
  size = "sm",
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root> &
  VariantProps<typeof toggleVariants> & { variant?: ToggleGroupVariant }) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      data-variant={variant}
      className={cn(
        "inline-flex w-fit items-center",
        variant === "segment"
          ? "gap-0.5 rounded-sm border border-rule bg-sunken/70 p-0.5"
          : "flex-wrap gap-1",
        className,
      )}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ size }}>{children}</ToggleGroupContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({
  className,
  children,
  size,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item> &
  VariantProps<typeof toggleVariants>) {
  const context = useContext(ToggleGroupContext);
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn("shrink-0", toggleVariants({ size: size ?? context.size }), className)}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
}

export { ToggleGroup, ToggleGroupItem };
