import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { cn } from "../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "quiet" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "border-accent bg-accent text-on-accent hover:border-accent-strong hover:bg-accent-strong active:translate-y-px",
  secondary:
    "border-rule-strong bg-surface text-ink hover:border-accent/45 hover:bg-accent-soft active:translate-y-px",
  ghost: "border-transparent text-ink-2 hover:bg-sunken hover:text-ink",
  quiet: "border-rule bg-sunken/70 text-ink-2 hover:border-rule-strong hover:text-ink",
  danger: "border-material/30 bg-material-soft text-material hover:border-material/55",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-8 gap-1.5 px-2.5 text-xs",
  md: "min-h-10 gap-2 px-3.5 text-sm",
  lg: "min-h-12 gap-2.5 px-5 text-[15px]",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md") {
  return cn(
    "inline-flex select-none items-center justify-center rounded-md border font-semibold transition duration-150",
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

/** A pressed/unpressed control for filters — a button, not a checkbox pretending to be one. */
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
        "inline-flex min-h-8 items-center gap-1.5 whitespace-nowrap rounded-sm px-2.5 text-xs font-semibold transition",
        pressed
          ? "bg-ink text-canvas shadow-panel"
          : "text-ink-3 hover:bg-sunken hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
