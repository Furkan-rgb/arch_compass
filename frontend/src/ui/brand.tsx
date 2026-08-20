import { Link } from "react-router-dom";

import { cn } from "../lib/cn";
import { CompassMark } from "./icons";

/** The only place the mark is drawn. Flat ink: there is no gradient in this system. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid place-items-center rounded-md bg-ink text-canvas",
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
        <span className="block font-display text-[15px] font-bold leading-tight tracking-tight text-ink">
          <span className="font-normal text-ink-2">Arch</span>Compass
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
