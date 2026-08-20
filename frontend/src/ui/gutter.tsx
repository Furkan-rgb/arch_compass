import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * The attribution gutter — the one structural device this interface is built around.
 *
 * The charter's second commitment says the machine assembles, the model judges and the
 * person decides, and that ArchCompass keeps those three jobs visibly apart. They were
 * apart in the domain and identical on screen: a verdict badge and a standing decision were
 * the same component reading a different table. This is where that stops.
 *
 * A single hairline runs the height of a finding. Every block registers against it, and the
 * column to its left says whose voice produced the block beside it. Where the voice changes
 * the tick becomes a rule across both columns and a filled square sits on the spine, so
 * reading down a finding shows the handoff: measured, then judged, then yours.
 *
 * The gutter carries *who*, not only *what* — the detector and its version, the model
 * identity and when it judged, or that nobody has decided yet. That is why there is no
 * separate provenance footer any more: it was printing the same attribution twice.
 *
 * Below `lg` the two columns stack, so the attribution becomes a label above its block. The
 * sequence survives; the registration does not, and nothing has been found that would.
 */
export function Gutter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-1 lg:grid-cols-[6.75rem_minmax(0,1fr)]", className)}>
      {children}
    </div>
  );
}

/**
 * One block, registered against the gutter.
 *
 * Pass `voice` for the block that begins a new one — it draws the rule and the mark and is
 * the only thing allowed to name the speaker. Pass `label` for a block continuing the voice
 * above it; it gets a quiet label and no rule, because nothing changed hands.
 */
export function GutterBlock({
  voice,
  who,
  label,
  children,
  className,
}: {
  voice?: string;
  who?: ReactNode;
  label?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const turns = Boolean(voice);
  return (
    <>
      <div
        className={cn(
          // The spine itself. It is one continuous rule because the cells stack with no gap,
          // and grid stretches the gutter cell to its row's height.
          "relative px-4 pt-4 lg:border-r lg:border-rule lg:px-0 lg:py-5 lg:pr-3.5 lg:text-right",
          turns && "border-t border-rule-strong lg:pt-5",
          !turns && "lg:border-t-0",
        )}
      >
        {voice ? (
          <>
            <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-ink">
              {voice}
            </div>
            {who ? (
              <div className="mt-1 font-mono text-[10px] leading-snug text-ink-3 [overflow-wrap:anywhere]">
                {who}
              </div>
            ) : null}
            {/* The mark sits on the spine, not beside it, so the handoff reads as a point on
                a line rather than as another label. */}
            <span
              aria-hidden="true"
              className="absolute -right-[3px] -top-[3px] hidden size-1.5 bg-ink lg:block"
            />
          </>
        ) : label ? (
          <div className="text-[10px] font-semibold uppercase tracking-[0.09em] leading-snug text-ink-3">
            {label}
          </div>
        ) : null}
      </div>
      <div
        className={cn(
          "min-w-0 px-4 pb-5 pt-2.5 lg:py-5 lg:pl-5 lg:pr-6",
          turns && "lg:border-t lg:border-rule-strong",
          className,
        )}
      >
        {children}
      </div>
    </>
  );
}
