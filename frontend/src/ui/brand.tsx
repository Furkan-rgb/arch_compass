import { Link } from "react-router-dom";

import { cn } from "../lib/cn";
import { CompassMark } from "./icons";

/** The only place the mark is drawn. Flat ink: there is no gradient in this system. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        // The mark is a tile at 32px. `rounded-md` is 10px now, which is a third of it and
        // reads as a rounded rectangle rather than as a mark; `rounded-sm` holds the corner.
        "grid place-items-center rounded-sm bg-ink text-canvas",
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
  // The mark is 32px and stays 32px; the link's own box is 44 so a thumb lands on it rather
  // than beside it. Where the row it sits in must not grow with it, the call site hands the
  // difference back with a negative margin — see the header in `app/shell.tsx`.
  return (
    <Link
      to={to}
      className={cn("group inline-flex min-h-11 items-center gap-2.5 rounded-sm", className)}
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
