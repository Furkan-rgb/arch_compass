import { cn } from "@/lib/utils";

import { sheet } from "./components";
import { VerdictText } from "@/components/ledger";
import type { BoundaryReviewReport, ReviewedBoundary } from "./types";

/**
 * Where a boundary stands against the previous revision, worn as typography.
 *
 * The partition's rule is the ledger's rule: quiet is the resting state. A boundary that
 * carried, or was re-judged because its own inputs moved, says nothing — the verdict
 * beside it is the news. The marks exist for the three states a reader must not have to
 * deduce: it is new, it is back from the dead, or it is an old decision riding a renamed
 * boundary. Same small-caps idiom as the standing marks, because both are the team's
 * layer over the model's verdicts, never verdict colours.
 */
export function DeltaMark({ boundary }: { boundary: ReviewedBoundary }) {
  const mark = (word: string, title: string, attention: boolean) => (
    <span
      className={cn(
        "font-mono text-micro font-[650] tracking-[.08em] uppercase whitespace-nowrap",
        attention ? "text-accent-ink" : "text-ink-3",
      )}
      title={title}
    >
      {word}
    </span>
  );
  if (boundary.judged_because === "new") {
    return mark("new", "First revision this boundary exists in.", true);
  }
  if (boundary.judged_because === "resurfaced") {
    return mark(
      "back",
      "Addressed in an earlier revision — the same boundary has reappeared, with the standing and discussion it had.",
      true,
    );
  }
  if (boundary.delta_state === "succeeded") {
    return mark(
      "carried across",
      `The boundary changed shape${
        boundary.succeeds ? ` (succeeds ${boundary.succeeds})` : ""
      } and any standing decision rode along — worth re-reading whether it still holds.`,
      false,
    );
  }
  return null;
}

/**
 * The revision in one line, for the fact band: what moved, what carried.
 *
 * Zeros are omitted because the sentence is read, not tabulated — "4 judged · 9 carried"
 * answers "why was this fast and what should I look at" in one glance. A revision that
 * carried everything says so in those words: that is the good outcome, and a bare "0
 * judged" would read as a run that did nothing.
 */
export function deltaFact(delta: NonNullable<BoundaryReviewReport["delta"]>): string {
  if (delta.first_revision) return "first — nothing to compare with";
  const parts: string[] = [];
  if (delta.judged) parts.push(`${delta.judged} judged`);
  if (delta.succeeded) parts.push(`${delta.succeeded} carried across`);
  if (delta.resurfaced) parts.push(`${delta.resurfaced} back`);
  if (delta.addressed) parts.push(`${delta.addressed} addressed`);
  if (delta.carried) parts.push(`${delta.carried} carried`);
  if (parts.length === 1 && delta.carried) return `all ${delta.carried} carried`;
  return parts.join(" · ") || "nothing detected";
}

/**
 * The boundaries this revision closed: they were in the previous revision and the code no
 * longer has them.
 *
 * Its own quiet section rather than rows in the ledger, because an addressed boundary was
 * not detected here — it has no verdict, no excerpt, nothing to unfold. What it has is
 * the one sentence worth celebrating: the line is closed. Cleared-edge green, because
 * this is the loop doing what it exists for.
 */
export function AddressedLedger({
  addressed,
}: {
  addressed: NonNullable<BoundaryReviewReport["delta"]>["addressed_boundaries"];
}) {
  if (!addressed?.length) return null;
  return (
    <section
      aria-label="Addressed since the previous revision"
      className={cn(sheet, "mb-4 border-l-[3px] border-l-cleared p-[var(--card-pad)] max-sm:border-l-[3px]!")}
    >
      <h2 className="m-0 mb-2 text-micro font-[650] tracking-[.09em] uppercase text-ink-3">
        Addressed since the previous revision
      </h2>
      <ul className="m-0 grid list-none gap-1.5 p-0">
        {addressed.map((item) => (
          <li
            key={item.fingerprint}
            className="flex flex-wrap items-baseline gap-x-2 text-ui"
          >
            <code className="font-mono text-meta font-[550] text-ink">{item.title}</code>
            <span className="text-ink-3">
              was {item.material ? "still to change" : "earning its place"} — the code no
              longer has this boundary.
            </span>
            <VerdictText verdict="cleared">line closed</VerdictText>
          </li>
        ))}
      </ul>
    </section>
  );
}
