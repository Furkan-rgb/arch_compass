import { cva, type VariantProps } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/*
  The instrument this product reads records on: a bar that says what the rows are and how many,
  the rows themselves divided by rules and nothing nested, and a foot for the sentence about
  what the list does and does not contain.

  Shared rather than copied because three surfaces are the same instrument on purpose — the
  boundaries a review examined, the same list while the run is still filling it, and every
  review this workspace has run. A listing of reviews and the findings of one review look alike
  because they are alike, and the day one of them grows a column the other has to grow it too.

  What is here is the compound shape: the row's own grid, its cells, the verdict stripe and the
  verdict mark. What is not here is anything one surface does alone — a menu, a filter, a link
  arrow — which each of them writes in utilities at the one place it is true.
*/

/** The bar over a ledger: what these rows are, and how many of them there are. */
export function LedgerBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      data-slot="ledger-bar"
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-rule px-3 py-2",
        // The bar's name is a `strong`, at the size every label in this instrument wears.
        // A descendant rule because the caller passes the element, not a class.
        "[&>strong]:text-meta [&>strong]:font-[650]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * How many rows, pushed to the far end of the bar.
 *
 * Mono with tabular figures: it changes as a filter is typed or a run fills the list, and a
 * number that reflows its own width while being read is worse than no number.
 */
export function LedgerCount({ children }: { children: ReactNode }) {
  return (
    <span
      data-slot="ledger-count"
      className="ml-auto font-mono text-meta tabular-nums text-ink-3"
    >
      {children}
    </span>
  );
}

/** The rows. */
export function Ledger({ className, ...props }: React.ComponentProps<"ol">) {
  return (
    <ol
      data-slot="ledger"
      className={cn("m-0 grid list-none p-0", className)}
      {...props}
    />
  );
}

/**
 * One record, whatever is drawn inside it.
 *
 * The dividing rule, the scroll margin and the `:target` mark all belong to the item rather
 * than to the row: a citation names a record, and landing on one has to light the row up even
 * where the row is a link with its own hover.
 */
export function LedgerItem({
  className,
  ...props
}: React.ComponentProps<"li">) {
  return (
    <li
      {...props}
      // After the spread, not before it: a disclosure wrapping this with `asChild` merges its
      // own slot in through these props, and the item has to stay the item.
      data-slot="ledger-item"
      className={cn(
        "border-b border-rule-soft last:border-b-0",
        // Cleared by the sticky chrome, so a cited row is not scrolled under it.
        "scroll-mt-14",
        "[&:target>[data-slot=ledger-row]]:bg-accent-soft",
        className,
      )}
    />
  );
}

/**
 * What the list does not contain, under it.
 *
 * Every one of these says the same kind of thing: a ledger that showed only the interesting
 * rows would read identically to one where there was nothing interesting to show.
 */
export function LedgerFoot({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      data-slot="ledger-foot"
      className={cn(
        "m-0 border-t border-rule-soft px-3 py-2 text-micro leading-[1.5] text-ink-3 [&_code]:text-micro",
        className,
      )}
    >
      {children}
    </p>
  );
}

/*
  One row: a 3px verdict stripe, then what the record is, where it is, a fact or two about it,
  and the verdict. `group`, because the disclosure arrow reads the row's own open state.

  Two geometries, and the difference between them is real: a finding has a disclosure arrow in
  a fixed 20px column and a review does not, and a review's five-word outcome needs the wider
  gutter. Below 860px both drop the columns a narrow screen can do without — for a finding the
  location and the policy count, both of which are in the row's own detail; for a review the
  case revision, which the review's own page states.
*/
const rowVariants = cva(
  [
    "group grid w-full min-h-[38px] items-center gap-y-0 border-0 bg-transparent py-0 pl-0 text-left",
  ],
  {
    variants: {
      kind: {
        finding: [
          "cursor-pointer grid-cols-[3px_20px_minmax(0,auto)_minmax(0,1fr)_auto_auto] gap-x-3 pr-3",
          "hover:bg-sunken",
          "max-[860px]:grid-cols-[3px_20px_minmax(0,1fr)_auto]",
        ],
        /* No hover of its own: the hover belongs to the record, whose controls are this
           link's siblings, so highlighting the link alone would light half the row. */
        review: [
          "cursor-pointer grid-cols-[3px_minmax(0,auto)_minmax(0,1fr)_auto_auto_auto] gap-x-4 pr-2",
          "max-[860px]:grid-cols-[3px_minmax(0,1fr)_auto_auto] max-[860px]:gap-x-3",
        ],
      },
    },
    defaultVariants: { kind: "finding" },
  },
);

/**
 * A row's own attributes, spread onto whatever element it is this time — a disclosure trigger,
 * a link, or a plain box while a run fills it in.
 *
 * Props rather than a component, because all three of those are already components with their
 * own opinions about what they render, and wrapping them in a fourth would put a box between
 * the item and the row that the item's rule and its `:target` mark both reach through. The
 * slot travels with the class for the same reason: the `:target` mark names the row, so a row
 * that announced itself as one only sometimes would silently lose it. Where the row is not the
 * item's own child — a review listing sets the record's controls beside the link — the caller
 * renames the slot to say which of the two it is, and that mark is not in play there.
 */
export function rowProps({
  kind,
  className,
}: VariantProps<typeof rowVariants> & { className?: string }) {
  return {
    "data-slot": "ledger-row",
    className: cn(rowVariants({ kind }), className),
  } as const;
}

/**
 * The verdict stripe: three pixels that make a column of records scannable without reading a
 * word of any of them. The neutral rule is a record with no verdict yet, not a missing one.
 */
const stripeVariants = cva("self-stretch", {
  variants: {
    verdict: {
      none: "bg-rule",
      material: "bg-material",
      cleared: "bg-cleared",
      judging: "bg-accent",
    },
  },
  defaultVariants: { verdict: "none" },
});

export type Stripe = "none" | "material" | "cleared" | "judging";

export function RowStripe({ verdict = "none" }: { verdict?: Stripe }) {
  return <i aria-hidden className={stripeVariants({ verdict })} />;
}

/** What the record is: a qualified name or a timestamp, in the face this product stores facts in. */
export const rowName =
  "overflow-hidden font-mono text-meta font-[550] text-ellipsis whitespace-nowrap";

/** Where it is, or which revision it judged. First column a narrow screen gives up. */
export const rowWhere =
  "overflow-hidden font-mono text-micro text-ellipsis whitespace-nowrap text-ink-3 max-[860px]:hidden";

/** A count about the record — policies borne, say. Tabular, because it sits in a column. */
export const rowMeta =
  "font-mono text-micro tabular-nums whitespace-nowrap text-ink-3 max-[860px]:hidden";

/** A record with no verdict yet: what it is doing now, or that it is waiting its turn. */
export const rowJudging = "font-mono text-micro whitespace-nowrap text-accent-ink";
export const rowQueued = "font-mono text-micro whitespace-nowrap text-ink-3";

/**
 * The verdict as a word.
 *
 * The majority verdict is quiet text in its own hue and the exception wears the badge's loud
 * verdict variant: a column of filled chips emphasises nothing, and the one record that came
 * out the other way is exactly what a reader is scanning for. One hue and one face whether it
 * marks a boundary or a whole run.
 *
 * `sentence` is for the five-word outcome with figures in it that a review listing carries.
 * Shouted in caps it stops being scannable, and the numbers have to line up down the column.
 */
const verdictTextVariants = cva("font-mono text-micro whitespace-nowrap", {
  variants: {
    verdict: {
      material: "text-material",
      cleared: "text-cleared",
    },
    tone: {
      mark: "tracking-[.05em] uppercase",
      sentence: "tracking-[.01em] tabular-nums",
    },
  },
  defaultVariants: { tone: "mark" },
});

export function VerdictText({
  verdict,
  tone,
  children,
}: VariantProps<typeof verdictTextVariants> & {
  verdict: "material" | "cleared";
  children: ReactNode;
}) {
  return (
    <span data-slot="verdict-text" className={verdictTextVariants({ verdict, tone })}>
      {children}
    </span>
  );
}
