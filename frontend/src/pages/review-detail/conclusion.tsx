/** The Conclusion card: what the verdicts amount to, read as a set. */

import { cn } from "@/lib/utils";

import { Group, sheet } from "../../components";
import { Citations } from "../../review-ledger";
import type { ReviewOverview } from "../../types";

/**
 * What the verdicts amount to, read as a set.
 *
 * Leads with the bottom line — the situation, what came out wrong, and what to do — because
 * a reader who gets no further than the first sentence should still know where they stand.
 * Closes with the limits, because a reader who has just been told what to do is exactly who
 * needs to know what was not examined.
 *
 * Below the ledger rather than above it. It is the one thing none of the separate calls
 * could produce, and it is also the thing a reader checks *after* seeing which boundaries it
 * is talking about — the citations lead back up into the rows.
 */
export function Conclusion({ overview }: { overview: ReviewOverview }) {
  const themes = overview.themes || [];
  const sequence = overview.recommended_sequence || [];
  return (
    // "Conclusion", not "Findings": the findings are the boundaries above, each with its own
    // verdict. This is what they amount to read as a set.
    <section data-slot="overview" className={cn(sheet, "p-[var(--card-pad)]")} aria-label="Conclusion">
      <h2 className="m-0 mb-3 text-micro font-[650] tracking-[.09em] uppercase text-accent-ink">
        Conclusion
      </h2>
      <p data-slot="overview-lead" className="m-0 max-w-[74ch] text-body leading-reading">
        {overview.situation}
      </p>

      {themes.length > 0 ? (
        <Group label="Across the boundaries">
          <ul className={overviewList}>
            {themes.map((statement) => (
              <li key={statement.text} className={cn(overviewClaim, overviewBullet)}>
                <span className="min-w-0">{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ul>
        </Group>
      ) : null}

      {sequence.length > 0 ? (
        <Group label="Recommended actions, in order">
          <ol className={cn(overviewList, "[counter-reset:step]")}>
            {sequence.map((statement) => (
              <li key={statement.text} className={cn(overviewClaim, overviewStep)}>
                <span className="min-w-0">{statement.text}</span>
                <Citations references={statement.supporting_references || []} />
              </li>
            ))}
          </ol>
        </Group>
      ) : null}

      {/* Kept even when there is nothing else: "no theme ran across these boundaries" is a
          result, and a reader still has to know what the method could not see. */}
      <p
        data-slot="overview-limits"
        className="m-0 mt-4 max-w-[82ch] border-t border-rule-soft pt-3 text-ui leading-[1.6] text-ink-2"
      >
        <strong>What this review could not see.</strong> {overview.limits}
      </p>
    </section>
  );
}

/* A claim the conclusion draws, with the boundaries it rests on beside it.
   The marker is a pseudo-element rather than a list bullet or a rendered span, because the
   claim and its citations are one wrapping line of flex items and a marker in that flow
   would be a fourth one — it has to sit outside the text it marks. */
const overviewList = "m-0 grid max-w-[82ch] list-none gap-3 p-0";
const overviewClaim =
  "relative flex flex-wrap items-baseline gap-x-2 gap-y-1 text-body leading-[1.55] before:absolute before:left-[2px]";
const overviewBullet = "pl-4 before:font-bold before:text-primary before:content-['·']";
/* Numbered, because the recommended order is the whole of what that list adds: a dot would
   give the reader nothing to refer to when they come back to the third one. */
const overviewStep =
  "pl-6 [counter-increment:step] before:text-ui before:tabular-nums before:text-accent-ink before:content-[counter(step)_'.']";
