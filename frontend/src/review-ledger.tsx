import { ChevronRight, Network } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Ledger,
  LedgerBar,
  LedgerCount,
  LedgerFoot,
  LedgerItem,
  RowStripe,
  VerdictText,
  type Stripe,
  rowJudging,
  rowMeta,
  rowName,
  rowProps,
  rowQueued,
  rowWhere,
} from "@/components/ledger";
import { cn } from "@/lib/utils";

import { sheet } from "./components";
import { FindingSource } from "./finding-source";
import type { RunState } from "./run-progress";
import type { ReviewedBoundary } from "./types";

/**
 * The verdicts as a ledger: one row per boundary, opened for the reasoning behind it.
 *
 * What this replaced was a scroll — every finding drawn as a full-width essay with its
 * bearings and its evidence already open, so the one thing a reader comes here for, how many
 * boundaries came out which way, was only learnable by reading to the end. The counts now
 * lead, the rows are the index, and the essay is one click deep at reading leading. Nothing
 * was dropped: a row opens into exactly what the finding said before.
 *
 * A cleared boundary keeps its row. It is the record that the advisor looked, and a ledger
 * that listed only problems would read identically whether six boundaries were examined and
 * cleared or none ever was.
 */

/**
 * One boundary named as a link into its own row.
 *
 * The single most useful move on this page: a reader who doubts a theme is one click from
 * the verdicts it was built from. The ledger opens the row the reference names, so the jump
 * lands on the reasoning rather than on a collapsed line.
 */
export function Cite({ reference }: { reference: string }) {
  return (
    <a
      data-slot="citation"
      className={cn(
        "rounded-pill border border-accent-rule bg-accent-soft px-2 py-px",
        "font-mono text-meta tracking-[.04em] whitespace-nowrap text-accent-ink no-underline",
        "hover:border-primary hover:bg-primary hover:text-on-accent",
      )}
      href={`#${reference}`}
    >
      {reference}
    </a>
  );
}

/** The boundaries a claim rests on, as links into the findings themselves. */
export function Citations({ references }: { references: string[] }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {references.map((reference) => (
        <Cite key={reference} reference={reference} />
      ))}
    </span>
  );
}

/**
 * Which verdict is the exception here, and therefore the one that wears the loud mark.
 *
 * Every row carrying a filled chip is a page where nothing is emphasised, because the eye
 * cannot pick an exception out of a column of identical badges. So the majority verdict is
 * quiet text in its own hue and the minority wears the chip — on a report where five of six
 * boundaries should change, the one that earned its place is the thing worth seeing.
 *
 * `null` where the two are level: neither is the exception then, and picking one would be
 * inventing an emphasis the set does not have.
 */
export function loudVerdict(reviewed: ReviewedBoundary[]): boolean | null {
  const material = reviewed.filter((item) => item.material).length;
  const cleared = reviewed.length - material;
  if (material === cleared) return null;
  return material < cleared;
}

/** The words this product uses for the two verdicts, wherever it counts or marks them. */
export const VERDICT_WORDS = { material: "should change", cleared: "earns its place" };

export type BandFact = { label: string; value: ReactNode; title?: string };

/* The counts are the product's material and its whole answer, so they are the one number on
   the page set at display size in the face values are stored in. The word under each is a
   label, at the size and tracking every label on this page wears. */
const countValue = "font-mono text-display font-[650] tracking-[-.02em] tabular-nums leading-[1.15]";
const countName = "text-micro tracking-[.05em] uppercase";

/**
 * What the verdicts amount to, in the first 80 pixels of the page.
 *
 * `holding` prints how far the run got and not how it went. The verdicts of a first pass are
 * stored but withheld — four of five moved once the questions were answered on the example
 * this flow was measured against — and a band that led with the split would be reporting
 * them as findings by the back door, in the largest type on the screen.
 */
export function VerdictBand({
  material,
  cleared,
  judged,
  total,
  mode,
  countLabel = "boundaries judged",
  facts,
}: {
  material: number;
  cleared: number;
  judged: number;
  total: number;
  /** `counted` prints how far the run got in place of a split it should not report. */
  mode: "settled" | "live" | "counted";
  countLabel?: string;
  facts: BandFact[];
}) {
  const share = (count: number) => (total > 0 ? `${(count / total) * 100}%` : "0%");
  return (
    <section
      data-slot="verdict-band"
      className={cn(sheet, "flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3")}
      aria-label="Verdicts"
    >
      <div data-slot="verdict-pair" className="flex gap-6">
        {mode === "counted" ? (
          <div className="grid">
            <b className={countValue}>{judged}</b>
            <span className={cn(countName, "text-ink-3")}>{countLabel}</span>
          </div>
        ) : (
          <>
            {/* The hue is on the pair, so the number and its word are one statement. */}
            <div className="grid text-material">
              <b className={countValue}>{material}</b>
              <span className={countName}>{VERDICT_WORDS.material}</span>
            </div>
            <div className="grid text-cleared">
              <b className={countValue}>{cleared}</b>
              <span className={countName}>{VERDICT_WORDS.cleared}</span>
            </div>
          </>
        )}
      </div>

      {/* Stacked rather than side by side, so the gap left at the end of the bar is the part
          of the sweep that has not been judged yet. On a finished review there is none. */}
      {mode === "counted" || total === 0 ? null : (
        <div
          className="flex h-1.5 w-32 overflow-hidden rounded-pill bg-rule-soft"
          role="img"
          aria-label={
            mode === "live"
              ? `${judged} of ${total} boundaries judged so far`
              : `${material} of ${total} boundaries should change`
          }
        >
          <i className="block h-full bg-material" style={{ width: share(material) }} />
          <i className="block h-full bg-cleared" style={{ width: share(cleared) }} />
        </div>
      )}

      {/* Provenance, pushed to the far end of the row — until the row is too narrow to have
          a far end, where it becomes the line under the counts instead. */}
      <dl
        data-slot="band-facts"
        className="ml-auto flex flex-wrap gap-x-6 gap-y-1 max-[860px]:ml-0"
      >
        {facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className={cn(countName, "text-ink-3")}>{fact.label}</dt>
            <dd
              className="mt-0.5 overflow-hidden font-mono text-meta tabular-nums text-ellipsis whitespace-nowrap text-ink-2"
              title={fact.title}
            >
              {fact.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

type Filter = "all" | "material" | "cleared";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "material", label: "Should change" },
  { id: "cleared", label: "Earns its place" },
];

/* The reasoning behind one verdict, at reading width and reading leading — the one passage
   on this page written to be read rather than scanned. Everything around it is 78ch, which
   is the width of substantiation you scan. */
const reasoning = "mb-3 max-w-[72ch] text-body leading-reading";
const evidence = "mb-3 max-w-[78ch]";
/* A heading inside a row: small caps with a rule running out to the edge of the column, so
   it divides the detail without adding a second border to it. */
const subhead =
  "mt-4 mb-2 flex items-center gap-2 text-micro font-[650] tracking-[.09em] text-ink-3 uppercase after:h-px after:flex-1 after:bg-rule-soft after:content-['']";

/**
 * One boundary's row, and everything the finding said behind it.
 *
 * The row is the button and the detail is what it discloses, which is why the qualified name
 * is set in the mono face and the location beside it: those are the two facts a reader scans
 * a column of these for.
 */
function LedgerRow({
  item,
  policyCount,
  loud,
  open,
  onOpen,
  onShowInAtlas,
  reviewId,
}: {
  item: ReviewedBoundary;
  policyCount: number;
  /** Which verdict is the exception on this page, from `loudVerdict`. */
  loud: boolean | null;
  open: boolean;
  onOpen: (reference: string | null) => void;
  onShowInAtlas: ((nodeId: string) => void) | null;
  reviewId: string;
}) {
  const bearings = item.policy_bearings || [];
  const abstraction = item.candidate.participants[0];
  const implementation = item.candidate.participants[1];
  const where = abstraction?.location || implementation?.location || null;
  const verdict = item.material ? "material" : "cleared";
  const word = item.material ? VERDICT_WORDS.material : VERDICT_WORDS.cleared;
  return (
    // `asChild`, so the disclosure is the list item itself rather than a wrapper inside it:
    // the stripe, the dividing rule and the `:target` mark are all drawn from the item, and
    // a box between them and the row would cut every one of those selectors.
    <Collapsible
      asChild
      open={open}
      onOpenChange={(next) => onOpen(next ? item.reference : null)}
    >
      <LedgerItem id={item.reference}>
        <CollapsibleTrigger
          {...rowProps({ kind: "finding" })}
          // The detail keeps the name this page has always given it, and the trigger is
          // pointed back at that rather than at the generated one. A citation names a row,
          // and the two ends of a disclosure have to agree on what the row is called.
          aria-controls={`detail-${item.reference}`}
        >
          <RowStripe verdict={verdict} />
          {/* Radix marks the open disclosure on the trigger, which is the row this sits in. */}
          <ChevronRight
            className="justify-self-center text-ink-3 transition-transform duration-[140ms] group-data-[state=open]:rotate-90"
            size={13}
            aria-hidden
          />
          <span className={rowName}>
            {abstraction?.qualified_name || item.candidate.summary}
          </span>
          <span className={rowWhere}>
            {where ? `${where.path}:${where.start_line}` : item.reference}
          </span>
          {/* The denominator is named on purpose: every policy was presented to every
              boundary, so one that does not appear here was considered and found not to
              apply — a different statement from never having been shown. */}
          <span className={rowMeta} title={`${bearings.length} of ${policyCount} policies`}>
            {bearings.length}/{policyCount}
          </span>
          {/* Words, not only a coloured rail: a reader scanning for "what was the answer"
              should not have to learn a colour convention first. The exception wears the
              chip and the majority is quiet text, so the odd one out is what the eye finds.
              The chip is the badge's verdict variant — the one place in this design a chip
              is allowed to be loud is on a verdict, which is exactly this. */}
          {loud === item.material ? (
            <Badge variant={verdict} className="font-[650] tracking-[.04em]">
              {word}
            </Badge>
          ) : (
            <VerdictText verdict={verdict}>{word}</VerdictText>
          )}
        </CollapsibleTrigger>

        {/* `forceMount`, so every row carries its detail whether or not it is showing: a
            citation has to be able to open any of them, and the evidence each one fetches
            is asked for once per page rather than again on every reopening. */}
        <CollapsibleContent
          forceMount
          id={`detail-${item.reference}`}
          className="pt-1 pr-4 pb-4 pl-9 data-[state=closed]:hidden"
        >
          {/* The review's own wording for the verdict, kept as it was written. It depends on
              which shape was judged — "not earning its place" is right for indirection that
              hides nothing and wrong for a constant copied into four modules — so it is the
              review's sentence to write, not this page's. A sentence, so it is set as one:
              the two-word mark in the row above it is shouted, and this is not. */}
          <p className="mt-1 mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span
              className={cn(
                "font-mono text-meta whitespace-nowrap",
                item.material ? "text-material" : "text-cleared",
              )}
            >
              {item.verdict_label}
            </span>
            <code className="text-micro tracking-[.07em] text-ink-3">{item.reference}</code>
          </p>

          {implementation ? (
            <p className="mb-3 text-ui text-ink-2 [overflow-wrap:anywhere]">
              Implemented only by <code>{implementation.qualified_name}</code>
              {implementation.location ? (
                <span className="ml-2 text-meta text-ink-3">
                  {implementation.location.path}:{implementation.location.start_line}
                </span>
              ) : null}
            </p>
          ) : null}

          <p className={reasoning}>{item.rationale}</p>

          {item.recommended_response ? (
            <p
              className={cn(
                evidence,
                "rounded-control bg-material-soft p-3 leading-[1.55] text-material",
              )}
            >
              <strong>Recommendation.</strong> {item.recommended_response}
            </p>
          ) : null}

          {bearings.length > 0 ? (
            // Open, not collapsed twice over. The substantiation is the reason to believe the
            // verdict, and a reader who has already opened the row should not have to open
            // anything else to reach it.
            <>
              <p className={subhead}>
                Bearings — {bearings.length} of {policyCount} policies bear on this boundary
              </p>
              {/* A card each, as wide as the column allows, each only as tall as its own
                  sentence. The column count steps down with the card count, because three
                  columns holding two cards leaves the right third blank — and out of 27
                  policies most boundaries bear two or three.

                  Named `bearing`, not `policy-card`: that name already belongs to the
                  Policies page, and these were inheriting its 255px floor, its hover lift
                  and its pointer cursor — a card of two lines stood a quarter of a screen
                  tall. */}
              <ul
                data-slot="bearings"
                className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-2 p-0"
              >
                {bearings.map((bearing) => (
                  <li
                    key={bearing.policy_id}
                    data-slot="bearing"
                    className="rounded-control border border-rule bg-sunken px-3 py-2"
                  >
                    <strong className="mb-0.5 block text-meta font-[650] leading-[1.35] text-ink">
                      {bearing.policy_title}
                    </strong>
                    <span className="block text-meta leading-[1.5] text-ink-2">
                      {bearing.how}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className={cn(evidence, "text-ui text-ink-3")}>
              None of the {policyCount} policies presented bore on this boundary.
            </p>
          )}

          {/* What the case did not say, beside what the method could not see. Two different
              things a verdict rests on, and only this one is the reader's to fix — which is
              why it sits above the limits rather than being folded into them. */}
          {item.hinge ? (
            <p className="mb-2 max-w-[78ch] border-l-2 border-accent-rule pl-3 text-ui leading-[1.6] text-ink-2">
              <strong className="text-accent-ink">
                This verdict turns on an open question.
              </strong>{" "}
              {item.hinge.unknown}{" "}
              <span className="block">If so: {item.hinge.if_confirmed}</span>{" "}
              <span className="block">If not: {item.hinge.if_denied}</span>
            </p>
          ) : null}

          <FindingSource reviewId={reviewId} reference={item.reference} />

          <p
            data-slot="finding-limits"
            className="m-0 max-w-[78ch] text-meta leading-[1.5] text-ink-3"
          >
            {item.candidate.limitations}
          </p>

          {/* The map is a tab of this page rather than a section further down it, so this
              switches to it with the boundary already selected. Leaving the review to answer
              "where does this sit" lost the review; the question and its answer belong in one
              reading (workspace-design §4). Absent when the atlas is no longer indexed. */}
          {onShowInAtlas && abstraction?.node_id ? (
            <button
              type="button"
              className="mt-3 inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-ui text-accent-ink hover:underline"
              onClick={() => onShowInAtlas(abstraction.node_id)}
            >
              <Network size={14} aria-hidden /> Show {item.reference} in the atlas
            </button>
          ) : null}
        </CollapsibleContent>
      </LedgerItem>
    </Collapsible>
  );
}

/**
 * Every boundary examined, as one filterable ledger.
 *
 * One row open at a time. Two open findings put their reasoning side by side and neither is
 * the one being read; an accordion keeps the index intact underneath whichever is open.
 */
export function FindingsLedger({
  reviewed,
  policyCount,
  reviewId,
  open,
  onOpen,
  onShowInAtlas,
}: {
  reviewed: ReviewedBoundary[];
  policyCount: number;
  reviewId: string;
  /** The reference whose reasoning is showing, if any. Held by the page, because a citation
      link from the conclusion has to be able to open one. */
  open: string | null;
  onOpen: (reference: string | null) => void;
  onShowInAtlas: ((nodeId: string) => void) | null;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const loud = loudVerdict(reviewed);
  const shown = reviewed.filter(
    (item) =>
      filter === "all" || (filter === "material" ? item.material : !item.material),
  );

  return (
    <section className={sheet} aria-label="Boundaries examined">
      <LedgerBar>
        <strong>Boundaries</strong>
        <ToggleGroup
          type="single"
          value={filter}
          // A group in single mode clears itself when the current item is pressed again.
          // "No filter" is what `all` already says, so the empty value is the one answer
          // this control refuses.
          onValueChange={(value) => {
            if (value) setFilter(value as Filter);
          }}
          // Full width below 620px, which is what this control did when it shared a class
          // with the Policies filter bar and inherited that bar's stacking rule. Kept
          // deliberately rather than by accident: on a phone the row it sits in has nothing
          // else on it, and a filter floating at max-content there reads as unfinished.
          className="overflow-x-auto max-[620px]:w-full"
          aria-label="Filter by verdict"
        >
          {FILTERS.map(({ id, label }) => (
            <ToggleGroupItem key={id} value={id}>
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <LedgerCount>
          {shown.length} of {reviewed.length}
        </LedgerCount>
      </LedgerBar>

      <Ledger>
        {shown.map((item) => (
          <LedgerRow
            key={item.reference}
            item={item}
            policyCount={policyCount}
            loud={loud}
            open={open === item.reference}
            onOpen={onOpen}
            onShowInAtlas={onShowInAtlas}
            reviewId={reviewId}
          />
        ))}
      </Ledger>

      <LedgerFoot>
        Cleared boundaries stay listed: a report that showed only problems would look
        identical whether every boundary was examined or none ever was. <code>BR-001</code>{" "}
        and the rest are references ArchCompass assigns in detection order — citations lead
        to them, and citing one in a question makes the answer cite it back.
      </LedgerFoot>
    </section>
  );
}

/**
 * The same ledger while the run is still filling it.
 *
 * The stream announces every boundary the sweep found before it judges any of them, so the
 * rows exist from the moment detection ends and each one settles in place as its verdict
 * lands. A watcher reading the run's stored record instead has the counts and not the names,
 * and gets rows without labels rather than invented ones — the detected order is known only
 * to the run that swept for them.
 */
export function JudgingLedger({ progress }: { progress: RunState }) {
  const total = progress?.total ?? 0;
  const named = progress?.boundaries ?? [];
  const judged = progress?.judged ?? 0;
  const settled = progress?.eliciting || progress?.summarising;

  return (
    <section className={sheet} aria-label="Boundaries examined">
      <LedgerBar>
        <strong>Boundaries</strong>
        <LedgerCount>
          {judged} of {total} judged
        </LedgerCount>
      </LedgerBar>
      <Ledger>
        {Array.from({ length: total }, (_, index) => {
          const verdict = progress?.verdicts[index] ?? null;
          const current = index === judged && !settled;
          const name = named[index];
          // "Queued" is not a verdict and gets no colour: the neutral rule is the row that
          // has not been decided yet, and the accent is the one under the model right now.
          const state: Stripe =
            verdict === null ? (current ? "judging" : "none") : verdict ? "material" : "cleared";
          return (
            <LedgerItem key={index}>
              {/* Nothing to disclose, so nothing to press: the same row, minus the pointer. */}
              <div {...rowProps({ kind: "finding", className: "cursor-default" })}>
                <RowStripe verdict={state} />
                <span />
                {name ? (
                  <span className={rowName}>{name}</span>
                ) : (
                  // The shape of the answer rather than a guess at its content: the stream
                  // carries the names and the stored record does not.
                  <Skeleton className="h-2 w-[24ch] max-w-full" aria-hidden />
                )}
                <span className={rowWhere} />
                <span className={rowMeta} />
                {verdict === null ? (
                  <span className={current ? rowJudging : rowQueued}>
                    {current ? "judging…" : "queued"}
                  </span>
                ) : (
                  <VerdictText verdict={verdict ? "material" : "cleared"}>
                    {verdict ? VERDICT_WORDS.material : VERDICT_WORDS.cleared}
                  </VerdictText>
                )}
              </div>
            </LedgerItem>
          );
        })}
      </Ledger>
      {named.length === 0 && total > 0 ? (
        <LedgerFoot>
          Which boundary is under the model right now is in the stream this run is writing,
          not in its record, so the rows are unnamed here.
        </LedgerFoot>
      ) : null}
    </section>
  );
}
