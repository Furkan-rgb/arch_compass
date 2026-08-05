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

/**
 * What a ledger is made of, by day and by night.
 *
 * Every measurement below is a token, and the tokens are the only thing the theme moves. By
 * day the sheet is not there at all — it is a transparent wrapper and each row is a white
 * card that floats on the canvas with ten pixels of air under it. By night the cards fuse:
 * the sheet becomes the object, the rows lose their background and their radius, and a
 * hairline at five percent white is all that divides them.
 *
 * So there is no `theme === "dark"` anywhere in this file, and there must never be one. A
 * component here asks what a row is made of; the stylesheet answers.
 */
export const ledgerSheet =
  "mb-[var(--gap-lg)] rounded-panel [border:var(--sheet-border)] bg-[var(--sheet-bg)] shadow-[var(--sheet-shadow)]";

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
        "flex flex-wrap items-center gap-2.5 px-[var(--row-pad-x)] pt-3 pb-2",
        // Borderless by day, because the rows below it are already separate objects and a
        // rule over floating cards divides nothing from nothing.
        "[border-bottom:var(--lhead-rule)]",
        // The bar's name is a `strong`, in the face this design states things in.
        // A descendant rule because the caller passes the element, not a class.
        "[&>strong]:font-display [&>strong]:text-ui [&>strong]:font-semibold",
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

/** The rows. Their spacing is the material: ten pixels of air by day, none by night. */
export function Ledger({ className, ...props }: React.ComponentProps<"ol">) {
  return (
    <ol
      data-slot="ledger"
      className={cn(
        "m-0 grid list-none gap-[var(--row-gap)] p-[var(--rows-pad)]",
        className,
      )}
      {...props}
    />
  );
}

/**
 * One record, whatever is drawn inside it — and the object the material flip acts on.
 *
 * A card by day, a band of one sheet by night. The dividing rule, the scroll margin and the
 * `:target` mark all belong to the item rather than to the row: a citation names a record,
 * and landing on one has to light the row up even where the row is a link with its own hover.
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
        "rounded-[var(--row-radius)] bg-[var(--row-bg)] shadow-[var(--row-shadow)]",
        "[border-bottom:var(--row-divider)] last:border-b-0",
        // Cleared by the sticky chrome, so a cited row is not scrolled under it.
        "scroll-mt-14",
        // The mark follows the card's own corners, or it draws square ones inside them.
        "[&:target>[data-slot=ledger-row]]:bg-accent-soft",
        "[&:target>[data-slot=ledger-row]]:rounded-[var(--row-radius)]",
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
        "m-0 px-[var(--row-pad-x)] pt-2 pb-3 text-micro leading-[1.5] text-ink-3 [&_code]:text-micro",
        "[border-top:var(--foot-rule)]",
        className,
      )}
    >
      {children}
    </p>
  );
}

/*
  One row: the verdict stripe's column, then what the record is, where it is, a fact or two
  about it, and the verdict. `group`, because the disclosure arrow reads the row's own open
  state.

  Fifty pixels tall, and the stripe's column is `--stripe-col` rather than a number — the one
  place the flip reaches the row's geometry, and it moves by a single pixel (4 by day, 3 by
  night). Everything else about the grid is stated once and never restated, which is the rule
  the whole design rests on: the material changes, the layout does not.

  Two geometries, and the difference between them is real: a finding has a disclosure arrow in
  a fixed 20px column and a review does not, and a review's five-word outcome needs the wider
  gutter. Below 860px both drop the columns a narrow screen can do without — for a finding the
  location and the policy count, both of which are in the row's own detail; for a review the
  case revision, which the review's own page states.
*/
const rowVariants = cva(
  [
    "group grid w-full min-h-[var(--row-h)] items-center gap-y-0 border-0 bg-transparent py-0 pl-0 text-left",
    // The hover has to follow the card's own corners by day, and there are none by night.
    "rounded-[var(--row-radius)]",
  ],
  {
    variants: {
      kind: {
        finding: [
          "cursor-pointer grid-cols-[var(--stripe-col)_20px_minmax(0,auto)_minmax(0,1fr)_auto_auto] gap-x-3.5 pr-[var(--row-pad-x)]",
          "hover:bg-sunken",
          "max-[860px]:grid-cols-[var(--stripe-col)_20px_minmax(0,1fr)_auto]",
        ],
        /* No hover of its own: the hover belongs to the record, whose controls are this
           link's siblings, so highlighting the link alone would light half the row. */
        review: [
          "cursor-pointer grid-cols-[var(--stripe-col)_minmax(0,auto)_minmax(0,1fr)_auto_auto_auto] gap-x-4 pr-2",
          "max-[860px]:grid-cols-[var(--stripe-col)_minmax(0,1fr)_auto_auto] max-[860px]:gap-x-3.5",
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

/*
  The verdict's own vocabulary: a fill, an ink, and a word.

  Three records rather than three copies, because this product draws one verdict in four
  shapes — a tick beside a row, a rule down the leading edge of a poster card, the count in
  the band, and the word next to any of them — and a hue that disagreed with its word across
  two of them would be the design saying two things about one judgement. Everything below
  composes these; nothing anywhere writes `bg-material` beside a verdict again.

  The neutral fill is a record with no verdict yet, not a missing one, and the accent is the
  one under the model right now — neither is a judgement, which is why neither has an ink or
  a word.
*/
export const VERDICT_FILL = {
  none: "bg-rule",
  material: "bg-material",
  cleared: "bg-cleared",
  // `bg-primary`, not `bg-accent`. In this sheet the bare name `accent` belongs to shadcn's
  // meaning of it — the tint a row takes under the pointer, which here is `--sunken` — and
  // this design's accent reaches the utilities as `--color-primary`. Written as `bg-accent`
  // the row under the model right now was drawn in the well's own colour: a stripe the same
  // shade as a hover, on the one row of a running ledger that has to be findable.
  judging: "bg-primary",
} as const;

export const VERDICT_INK = { material: "text-material", cleared: "text-cleared" } as const;

/** The words this product uses for the two verdicts, wherever it counts or marks them.
    "Sound" replaced "earns its place" on the surface: one stampable word, read in a
    column. The method's own question — is this boundary earning its place — keeps its
    phrasing in the prompts and the domain, where it is a question and not a stamp. */
export const VERDICT_WORDS = {
  material: "should change",
  cleared: "sound",
} as const;

export type Stripe = keyof typeof VERDICT_FILL;
export type Verdict = keyof typeof VERDICT_INK;

/**
 * The verdict stripe: the mark that makes a column of records scannable without reading a
 * word of any of them.
 *
 * Same element, two drawings, four measurements. By day it is a short rounded tick set in
 * from the card's leading edge, because a rule running the full height of a floating card
 * would read as a torn edge; by night it is the row's whole leading edge, because on one
 * unbroken sheet a short tick has nothing to be short against.
 *
 * `justify-self-start` with its own width rather than a stretched grid item: the tick is
 * inset past its own column and into the gutter, and a stretched item in a 4px track cannot
 * be pushed anywhere.
 */
const stripeVariants = cva(
  [
    "w-[var(--stripe-col)] h-[var(--stripe-h)] ml-[var(--stripe-ml)]",
    "justify-self-start [align-self:var(--stripe-align)] rounded-[var(--stripe-r)]",
  ],
  { variants: { verdict: VERDICT_FILL }, defaultVariants: { verdict: "none" } },
);

export function RowStripe({ verdict = "none" }: { verdict?: Stripe }) {
  return <i aria-hidden className={stripeVariants({ verdict })} />;
}

/**
 * One record as a poster rather than as a row: the same stripe, run the full height of a
 * card, with the verdict set large beside it.
 *
 * The material flip does not reach this one. A row's stripe is short by day because it sits
 * on a floating card among other floating cards; a poster *is* the card, and its stripe is
 * the card's own leading edge in both themes. So the four `--stripe-*` tokens are deliberately
 * not read here — what is shared with a row is the hue, which is the part that carries the
 * judgement.
 */
export const posterCard =
  "grid grid-cols-[4px_minmax(0,1fr)] gap-x-4 border border-rule-soft bg-surface";

export function PosterStripe({ verdict }: { verdict: Stripe }) {
  return <span aria-hidden className={cn("self-stretch rounded-[99px]", VERDICT_FILL[verdict])} />;
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

/** A record whose verdict was not reached here: looked up, not judged. As quiet as queued. */
export const rowCarried = "font-mono text-micro whitespace-nowrap text-ink-3";

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
    verdict: VERDICT_INK,
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
  verdict: Verdict;
  children: ReactNode;
}) {
  return (
    <span data-slot="verdict-text" className={verdictTextVariants({ verdict, tone })}>
      {children}
    </span>
  );
}

/**
 * A policy a verdict leaned on, named on the verdict itself.
 *
 * Two tones of one chip, because a citation is the same claim whether it can be followed or
 * not. On a review it is a link into the row it names — the single most useful move on that
 * page — and it takes the interactive step up in size and the filled hover that says so. On
 * a page with no rows to land in it is a plain chip at the smallest step, and it must not
 * offer a hover it cannot honour.
 */
const citationVariants = cva(
  "rounded-pill border border-accent-rule bg-accent-soft font-mono whitespace-nowrap text-accent-ink",
  {
    variants: {
      tone: {
        chip: "px-[9px] py-[3px] text-micro",
        link: cn(
          "px-2 py-px text-meta tracking-[.04em] no-underline",
          "hover:border-primary hover:bg-primary hover:text-on-accent",
        ),
      },
    },
    defaultVariants: { tone: "chip" },
  },
);

/** The citation as a link, for a page whose rows it can reach. */
export const citationLink = citationVariants({ tone: "link" });

/** The citation as a plain chip, where there is nothing to follow it to. */
export function Citation({ children }: { children: ReactNode }) {
  return (
    <span data-slot="citation" className={citationVariants()}>
      {children}
    </span>
  );
}
