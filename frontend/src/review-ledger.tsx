import { ChevronRight, Network } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Spinner } from "@/components/ui/spinner";
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
  rowCarried,
  rowJudging,
  rowMeta,
  rowName,
  rowProps,
  rowQueued,
  rowWhere,
  citationLink,
  ledgerSheet,
  VERDICT_WORDS,
} from "@/components/ledger";
import { cn } from "@/lib/utils";

import { DeltaMark } from "./delta";
import { FindingSource } from "./finding-source";
import { judgingRows, type RunState } from "./run-progress";
import { DecisionMark, StandingFooter } from "./triage";
import type { BoundaryTriage, ReviewedBoundary } from "./types";

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
    <a data-slot="citation" className={citationLink} href={`#${reference}`}>
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

export type BandFact = { label: string; value: ReactNode; title?: string };

/* The counts are the product's material and its whole answer, so they are the one number on
   the page set at display size — in the display face, which is where this design states a
   judgement. Tabular, because two of them stand side by side and their digits have to line
   up. The word under each is a label, at the size and tracking every label on this page
   wears. */
const countValue =
  "font-display text-display font-[650] tracking-[-.03em] tabular-nums leading-[1.05]";
const countName = "text-micro tracking-[.06em] uppercase";
/* One of the two glows this design allows, and the reason the dark theme exists: on onyx the
   verdict counts stop being coloured numerals and become the lamps the page is lit by. The
   token is `none` by day — a glow on porcelain is a smudge — so nothing here has to ask
   which theme is on. It is spent on the verdicts and nowhere else, which is why it is not
   folded into `countValue`: the neutral count a held run prints is a position, not a verdict,
   and a third light on the page would cost the other two their meaning. */
const countLamp = "[text-shadow:var(--lamp-glow)]";

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
    // Not the page's standard sheet: the band is the one panel whose material is stated in
    // tokens of its own, because by night it is a gradient rather than a flat surface — the
    // page's single lit object, with the lamps on it.
    <section
      data-slot="verdict-band"
      className={cn(
        "mb-[var(--gap-lg)] flex flex-wrap items-center gap-x-[34px] gap-y-3.5",
        // `background`, not `background-color`: by night this token is a gradient, and a
        // colour property handed one paints nothing at all.
        "rounded-panel [border:var(--band-border)] [background:var(--band-bg)]",
        "p-[var(--band-pad)] shadow-[var(--band-shadow)]",
      )}
      aria-label="Verdicts"
    >
      <div data-slot="verdict-pair" className="flex gap-[26px]">
        {mode === "counted" ? (
          <div className="grid">
            <b className={countValue}>{judged}</b>
            <span className={cn(countName, "text-ink-3")}>{countLabel}</span>
          </div>
        ) : (
          <>
            {/* The hue is on the pair, so the number and its word are one statement. */}
            <div className="grid text-material">
              <b className={cn(countValue, countLamp)}>{material}</b>
              <span className={countName}>{VERDICT_WORDS.material}</span>
            </div>
            <div className="grid text-cleared">
              <b className={cn(countValue, countLamp)}>{cleared}</b>
              <span className={countName}>{VERDICT_WORDS.cleared}</span>
            </div>
          </>
        )}
      </div>

      {/* Stacked rather than side by side, so the gap left at the end of the bar is the part
          of the sweep that has not been judged yet. On a finished review there is none. */}
      {mode === "counted" || total === 0 ? null : (
        <div
          className="flex h-2 w-[150px] overflow-hidden rounded-pill bg-[var(--band-track)]"
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
        className="ml-auto flex flex-wrap gap-x-[26px] gap-y-1 max-[860px]:ml-0"
      >
        {facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className={cn(countName, "tracking-[.05em] text-ink-3")}>{fact.label}</dt>
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

type Filter = "all" | "material" | "cleared" | "unreviewed";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "material", label: "Should change" },
  { id: "cleared", label: "Earns its place" },
];

/* One more filter, shown only where its question can be asked: "unreviewed" needs a branch
   for decisions to be filed under. A filter for a question with no answer is a control that
   teaches the reader to distrust the bar. The "new & changed" filter that used to sit beside
   it went with the baseline that gave those words their meaning. */
const UNREVIEWED_FILTER: { id: Filter; label: string } = {
  id: "unreviewed",
  label: "Unreviewed",
};

/* The reasoning behind one verdict, at reading width and reading leading — the one passage
   on this page written to be read rather than scanned. Everything around it is 78ch, which
   is the width of substantiation you scan. */
const reasoning = "mb-3 max-w-[72ch] text-body leading-reading [overflow-wrap:anywhere]";
const evidence = "mb-3 max-w-[78ch] [overflow-wrap:anywhere]";
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
  open,
  onOpen,
  onShowInAtlas,
  reviewId,
  triage,
  branchId,
}: {
  item: ReviewedBoundary;
  policyCount: number;
  open: boolean;
  onOpen: (reference: string | null) => void;
  onShowInAtlas: ((nodeId: string) => void) | null;
  reviewId: string;
  /** This boundary's fingerprint and standing decision, joined on by the server. Absent
      while a run is watched live — triage waits for the record. */
  triage: BoundaryTriage | undefined;
  branchId: string | null;
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
          {/* One grid cell, not two: the row's geometry is a six-column contract with
              `rowVariants`, and every extra child would wrap the tail onto a second line.
              Inside it, reading order matches authority order: where the revision put the
              boundary, what the team said, what the model judged. Quiet is the resting
              state — carried and re-judged boundaries wear no delta mark, undecided ones
              no standing mark. */}
          <span className="flex items-center gap-2 justify-self-end">
            <DeltaMark boundary={item} />
            <DecisionMark triage={triage} />
            {/* Words, not only a coloured rail: a reader scanning for "what was the answer"
                should not have to learn a colour convention first. Every verdict wears the
                label — the hue still separates them at a glance, and two boundaries with
                two answers read as two stamps rather than one stamp and a whisper. */}
            <Badge variant={verdict} className="font-[650] tracking-[.04em]">
              {word}
            </Badge>
          </span>
        </CollapsibleTrigger>

        {/* `forceMount`, so every row carries its detail whether or not it is showing: a
            citation has to be able to open any of them, and the evidence each one fetches
            is asked for once per page rather than again on every reopening. */}
        <CollapsibleContent
          forceMount
          id={`detail-${item.reference}`}
          className="pt-1.5 pr-[var(--row-pad-x)] pb-5 pl-[var(--detail-pad-l)] data-[state=closed]:hidden"
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
              {/* The grid carries its own bottom margin. Without one the space under it was
                  whatever the next block happened to bring: `FindingSource` brings 16px, a
                  hinge brings nothing, and an excerpt that came back empty brings nothing —
                  so the cards sat flush against the next thing on exactly the boundaries
                  that have the most to say. Every gap in this detail is 16px after margins
                  collapse, and this one is now no exception. */}
              <ul
                data-slot="bearings"
                className="m-0 mb-3 grid list-none grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-2.5 p-0"
              >
                {bearings.map((bearing) => (
                  <li
                    key={bearing.policy_id}
                    data-slot="bearing"
                    className="rounded-control [border:var(--sheet-border)] bg-sunken px-3.5 py-2.5"
                  >
                    <strong className="mb-0.5 block text-meta font-[650] leading-[1.35] text-ink [overflow-wrap:anywhere]">
                      {bearing.policy_title}
                    </strong>
                    <span className="block text-meta leading-[1.5] text-ink-2 [overflow-wrap:anywhere]">
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
            // It draws its own rule, so it owns the space above that rule rather than taking
            // whatever the block before it left: against the bearing cards, an accent edge
            // starting flush with a card's bottom read as part of that card.
            <p className="mt-4 mb-2 max-w-[78ch] border-l-2 border-accent-rule pl-3 text-ui leading-[1.6] text-ink-2 [overflow-wrap:anywhere]">
              <strong className="text-accent-ink">
                This verdict turns on an open question.
              </strong>{" "}
              {item.hinge.unknown}
              {/* Two answers to the question above, and they are alternatives rather than a
                  sentence that wrapped — which is what three block spans at reading leading
                  and no separation between them looked like. */}
              <span className="mt-1 block">If so: {item.hinge.if_confirmed}</span>
              <span className="mt-1 block">If not: {item.hinge.if_denied}</span>
            </p>
          ) : null}

          <FindingSource reviewId={reviewId} reference={item.reference} />

          {/* What this finding could not see — a statement about the finding, not a caption
              on the excerpt above it. With no margin it sat on the last code block and read
              as one, so it takes the same 16px every other section here takes. */}
          <p
            data-slot="finding-limits"
            className="m-0 mt-4 max-w-[78ch] text-meta leading-[1.5] text-ink-3 [overflow-wrap:anywhere]"
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

          {/* Last, like a signature after a letter: the verdict and its evidence are
              read first, and what the team made of them is recorded underneath. Absent
              while the record has no triage join to offer (a live run). */}
          {triage ? (
            <StandingFooter
              boundary={item}
              triage={triage}
              branchId={branchId}
              reviewId={reviewId}
            />
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
  triage,
  branchId = null,
}: {
  reviewed: ReviewedBoundary[];
  policyCount: number;
  reviewId: string;
  /** The reference whose reasoning is showing, if any. Held by the page, because a citation
      link from the conclusion has to be able to open one. */
  open: string | null;
  onOpen: (reference: string | null) => void;
  onShowInAtlas: ((nodeId: string) => void) | null;
  /** Reference → the server's triage join for that boundary. Absent entirely on surfaces
      that watch a live run — triage reads the record, not the stream. */
  triage?: Map<string, BoundaryTriage>;
  branchId?: string | null;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const filters = [
    ...FILTERS,
    ...(branchId && triage ? [UNREVIEWED_FILTER] : []),
  ];
  const shown = reviewed.filter((item) => {
    switch (filter) {
      case "material":
        return item.material;
      case "cleared":
        return !item.material;
      case "unreviewed":
        return !triage?.get(item.reference)?.decision;
      default:
        return true;
    }
  });

  return (
    <section className={ledgerSheet} aria-label="Boundaries examined">
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
          // Full width below 620px, and last: the name and its count share the first
          // line — a label alone on a row it owns reads as a heading over emptiness, and
          // a count orphaned under the pills read as belonging to nothing. The pills take
          // the second line whole, where a filter at max-content would read as unfinished.
          className={cn(
            "overflow-x-auto max-[620px]:order-last",
            // The pills' line reaches the rows' own outer edges: the bar's padding
            // indents its text to match the rows' interior, but the pill track is an
            // object like the row cards below it, and an object narrower than the
            // objects it filters read as belonging to something else.
            "max-[620px]:-mx-[var(--row-pad-x)]",
            "max-[620px]:w-[calc(100%+2*var(--row-pad-x))]",
          )}
          aria-label="Filter by verdict"
        >
          {filters.map(({ id, label }) => (
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
            open={open === item.reference}
            onOpen={onOpen}
            onShowInAtlas={onShowInAtlas}
            reviewId={reviewId}
            triage={triage?.get(item.reference)}
            branchId={branchId ?? null}
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
export function JudgingLedger({
  progress,
  bearings,
  foot,
}: {
  progress: RunState;
  /**
   * What each landed verdict leaned on, as `borne/presented`, in the run's own order.
   *
   * Absent on a real run and that is not an omission: the stream reports that a boundary was
   * judged and which way, never how many policies bore on it, so a column filled in here from
   * anything but the caller's own knowledge would be a guess printed as a count. The finished
   * review has them, and `FindingsLedger` is where they are read.
   */
  bearings?: string[];
  /**
   * What this list does not contain, where the caller has something to say about it.
   *
   * A run in flight has one thing worth saying and says it itself: the rows are unnamed
   * because the names are in the stream. Anywhere the ledger is drawn over a set that is
   * already named — the front door's replay of one — that sentence is not the true one, and
   * the caller supplies the sentence that is.
   */
  foot?: ReactNode;
}) {
  const total = progress?.total ?? 0;
  const named = progress?.boundaries ?? [];
  const judged = progress?.judged ?? 0;
  const carried = progress?.carried ?? 0;
  // As many rows as the run actually has in flight, which against a provider that answers
  // several at once is several. The ledger is the run's own account of itself and a single
  // moving row would be a tidier account than the true one.
  const inFlight = judgingRows(progress);

  return (
    <section className={ledgerSheet} aria-label="Boundaries examined">
      <LedgerBar>
        <strong>Boundaries</strong>
        <LedgerCount>
          {judged} of {total} judged
          {/* Said while it is happening rather than only on the finished review. A run that
              carried most of its verdicts is over in seconds, and a count that stayed silent
              about it would leave the reader to conclude the run had skipped the work. */}
          {carried > 0 ? ` · ${carried} carried` : null}
        </LedgerCount>
      </LedgerBar>
      <Ledger>
        {Array.from({ length: total }, (_, index) => {
          const verdict = progress?.verdicts[index] ?? null;
          const origin = progress?.carriedFrom?.[index] ?? null;
          const current = inFlight.has(index);
          const name = named[index];
          // "Queued" is not a verdict and gets no colour: the neutral rule is the row that
          // has not been decided yet, and the accent is a row under the model right now.
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
                {/* Where a verdict was looked up rather than reached, the row says so in
                    place of the count of what bore on it: nothing bore on it here. The
                    origin run is in the title rather than the line, because a review id is
                    longer than the column and a reader wants the fact, not the identifier. */}
                <span
                  className={origin === null ? rowMeta : rowCarried}
                  title={origin === null ? undefined : `Carried from review ${origin}`}
                >
                  {origin !== null
                    ? "carried from an earlier run"
                    : verdict === null
                      ? null
                      : bearings?.[index]}
                </span>
                {verdict === null ? (
                  <span className={current ? rowJudging : rowQueued}>
                    {/* The spinner is the word: a row under the model right now is doing
                        exactly one thing, and a mark that moves says so without adding a
                        second verb to a column of verdicts. */}
                    {current ? (
                      <>
                        <Spinner className="size-3" aria-hidden role="presentation" />
                        <span className="sr-only">judging…</span>
                      </>
                    ) : (
                      "queued"
                    )}
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
      {foot ? (
        <LedgerFoot>{foot}</LedgerFoot>
      ) : named.length === 0 && total > 0 ? (
        <LedgerFoot>
          Which boundary is under the model right now is in the stream this run is writing,
          not in its record, so the rows are unnamed here.
        </LedgerFoot>
      ) : null}
    </section>
  );
}
