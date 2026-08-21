import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { cn } from "../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "quiet" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  // The one action a screen is asking for, in the one hue the product has. `danger` below is
  // the same red at a wash rather than a fill — a destructive action is consequential, not
  // primary, and fill against wash is what keeps the two apart now that both are red.
  primary:
    "border-accent-fill bg-accent-fill text-accent-on-fill hover:border-accent-strong hover:bg-accent-strong active:translate-y-px",
  // `bg-control` rather than `bg-surface`: a secondary button lands on the void, on a panel
  // and inside a sunken block, and on this ground it has to read as raised above all three.
  // One flat grey can only be brighter than one of them, so in dark the token is a film that
  // steps up from whatever is behind it, and the rim is the light along its top edge.
  secondary:
    "border-rule-strong bg-control text-ink shadow-rim hover:border-rule-strong hover:bg-control-2 active:translate-y-px",
  ghost: "border-transparent text-ink-2 hover:bg-sunken hover:text-ink",
  quiet: "border-rule bg-sunken/70 text-ink-2 hover:border-rule-strong hover:text-ink",
  danger: "border-material/30 bg-material-soft text-material hover:border-material/55",
};

// 44px is the charter's fifth principle, and `md` is what a button is unless somebody says
// otherwise — so `md` is the size that has to clear it. It was 40, which is why three call
// sites had already written `min-h-11` back on by hand. `sm` stays at 32 because it is the
// dense inline size; where a `sm` control is genuinely tapped, the call site grows its box
// and hands the extra height back with a negative margin.
/**
 * `sm` grows to the 44px floor on a coarse pointer and stays 32px on a fine one.
 *
 * The floor is a *touch* requirement, so answering it by width would be answering a
 * different question — and would cost a mouse user the density this size exists for. A
 * pseudo-element cannot answer it either: `getBoundingClientRect` ignores an absolutely
 * positioned `::after`, so a 32px button with an extended `::after` still measures 32,
 * and a finger is no more fooled than the test is. The box has to be the target.
 */
const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-8 pointer-coarse:min-h-11 gap-1.5 px-2.5 text-xs",
  md: "min-h-11 gap-2 px-3.5 text-sm",
  lg: "min-h-12 gap-2.5 px-5 text-[15px]",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md") {
  return cn(
    // `rounded-sm` is the control step. A button used to be `md` because `md` was 2px like
    // everything else; now the ladder has five real values, `md` is a block inside a panel,
    // and a button that took it would be rounder than the panel it sits in relative to its
    // own height.
    "inline-flex select-none items-center justify-center rounded-sm border font-semibold transition duration-150",
    "disabled:pointer-events-none disabled:opacity-45",
    VARIANTS[variant],
    SIZES[size],
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  type = "button",
  ...props
}: ButtonProps) {
  return <button type={type} className={cn(buttonClass(variant, size), className)} {...props} />;
}

export function ButtonLink({
  className,
  variant = "primary",
  size = "md",
  ...props
}: LinkProps & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={cn(buttonClass(variant, size), className)} {...props} />;
}

export function ExternalButtonLink({
  className,
  variant = "secondary",
  size = "md",
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}) {
  return (
    <a className={cn(buttonClass(variant, size), className)} {...props}>
      {children}
    </a>
  );
}

/**
 * A pressed/unpressed control for filters — a button, not a checkbox pretending to be one.
 *
 * What is on is *raised*, not inverted. `bg-ink text-canvas` is the loudest fill the system
 * can draw, and a row of them — a set of filters at rest is usually a row of them — reads as
 * a row of alarms rather than as a setting nobody has touched. So a pressed toggle wears the
 * `secondary` button's recipe: the control film, a rim along its top edge, full-strength ink.
 * White in light, a step up from the ground in dark: one gesture, not one colour.
 *
 * This is the same treatment `components/ui/toggle.tsx` gives a Radix switch, deliberately.
 * Two toggles that look different are two toggles a reader has to learn separately.
 */
export function ToggleButton({
  pressed,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { pressed: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={cn(
        // 44px is a *touch* requirement, so it is answered on a coarse pointer and nowhere
        // else — the same split `Button`'s `sm` size makes. A segmented control of three
        // chips is one line of text and two words of count; holding it at 44px with a mouse
        // spent a third of the queue's header on a strip that says which filter is on.
        "inline-flex min-h-8 pointer-coarse:min-h-11 items-center gap-1.5 whitespace-nowrap rounded-sm border px-2.5 text-xs font-semibold transition duration-150",
        // A toggle for an empty set stays readable — it is telling you the count is zero,
        // which is information — but stops offering to filter to nothing.
        "disabled:pointer-events-none disabled:opacity-40",
        pressed
          ? "border-rule-strong bg-control text-ink shadow-rim"
          : "border-transparent text-ink-3 hover:bg-sunken hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
