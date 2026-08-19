import { Link } from "react-router-dom";

import { cn } from "../lib/cn";
import { CompassMark } from "./icons";

/** The one gradient in the product, and the only place the mark is drawn. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid place-items-center rounded-md bg-gradient-to-br from-accent to-accent-strong text-on-accent shadow-panel",
        className,
      )}
    >
      <CompassMark className="size-[62%]" />
    </span>
  );
}

export function Wordmark({
  to = "/",
  subtitle,
  className,
}: {
  to?: string;
  subtitle?: string;
  className?: string;
}) {
  return (
    <Link
      to={to}
      className={cn("group inline-flex items-center gap-2.5 rounded-md", className)}
    >
      <BrandMark className="size-8 text-base transition group-hover:scale-[1.04]" />
      <span className="min-w-0">
        <span className="block font-display text-[15px] font-semibold leading-tight tracking-tight text-ink">
          Arch<span className="text-accent">Compass</span>
        </span>
        {subtitle ? (
          <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
            {subtitle}
          </span>
        ) : null}
      </span>
    </Link>
  );
}
