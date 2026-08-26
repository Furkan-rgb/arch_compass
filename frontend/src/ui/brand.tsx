import { Link } from "react-router-dom";

import { cn } from "../lib/cn";
import { CompassMark } from "./icons";

/**
 * The only place the mark is drawn, and the claim is true again: the app shell used to build
 * a second one from the bare compass glyph, so the identity changed at the click the landing
 * page exists to earn. It draws this now, at 24px.
 *
 * Flat ink: there is no gradient in this system.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        // The mark is a tile: 32px on the landing page, 24 in the rail. `rounded-md` is 10px
        // now, which is a third of the larger one and reads as a rounded rectangle rather than
        // as a mark; `rounded-sm` holds the corner at both sizes.
        //
        // `accent-fill` rather than `accent`: the fill is the deep red in both themes, because
        // a mark that lightens in dark is a second logo. The letterform token lifts; this one
        // does not.
        "grid place-items-center rounded-sm bg-accent-fill text-accent-on-fill",
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
  // than beside it. That pairing is what makes this the marketing wordmark rather than the
  // universal one: it does not fit a 48px rail, so the workbench's header draws `BrandMark`
  // beside its own 14px wordtext instead. Two sizes of one recipe, not two marks — the tile
  // and the Arch/Compass split are the identity, and both come from this file.
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
          <span className="block text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-3">
            {subtitle}
          </span>
        ) : null}
      </span>
    </Link>
  );
}
