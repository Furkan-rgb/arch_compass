import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type Decision, type Finding, type Review, type ReviewRun } from "../../api";
import { cn } from "../../lib/cn";
import { dispositionOf, humanise, plural, splitQualified, verdictOf } from "../../lib/format";
import { hasOpenReveal, isPlainShortcut } from "../../lib/keyboard";
import { useHasKeyboard } from "../../lib/media";
import { Mark } from "../../ui/mark";
import { TONE_EDGE, TONE_TEXT } from "../../ui/meta";
import { Button, ButtonLink, CopyButton, ToggleButton } from "../../ui/button";
import { Input } from "../../ui/field";
import { ArrowDown, ArrowUp, ChevronDown, DriftedIcon } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";
import { Prose } from "../../ui/prose";
import { RejudgementNote, type useRejudgementNotice } from "../start/run-progress";
import { ClarificationRound, type RoundAnswers } from "./clarification";
import { DecisionBar } from "./decision-bar";
import { FindingBody } from "./finding-detail";
import { CandidateTrajectory, TrajectoryPlaceholder } from "./trajectory";
import {
  type QueueFilter,
  awaitsAnswers,
  decisionIsStale,
  deltaIndexOf,
  deltaStateOf,
  movedSincePrevious,
  needsAttention,
} from "./docket-rules";

/**
 * The docket: the queue and the workbench, which were always the same list.
 *
 * The two used to be two panes. A rail down the left held rows reading `Clock`,
 * `ConfigLoader`, `IdGenerator` — bare leaf names, indistinguishable, unreadable — and
 * clicking one painted a full assessment into a column 900px to the right. Working through
 * six of them was: click, read across, decide across, click back. The list could not be
 * read and the detail could not be scanned, and the eye crossed the screen twice per item.
 *
 * They are one column now. Every candidate is a row carrying its own claim in a sentence, so
 * the list is the overview; the row opens in place, so checking a claim never moves you; and
 * deciding closes it and opens the next one that wants you, so there is a rhythm to work
 * down rather than a pair of panes to alternate between.
 *
 * The charter's first interface rule was "the queue is the product", and this is the version
 * of that rule that survives contact with a reviewer: the queue is not a rail beside the
 * product, it *is* the product, and the assessment is what a row of it says when asked.
 */

/**
 * The most segments the progress strip will draw.
 *
 * Past this a review has more candidates than the strip has room for, so a segment stands
 * for a share of the work rather than for one candidate — which is the whole of what went
 * wrong before: the fill compared a segment *index* against the raw settled count, so any
 * review larger than the strip read as finished the moment 24 things were settled.
 */
const SEGMENTS = 24;

/**
 * The shortest review the strip says anything on.
 *
 * `segments` is `Math.min(total, SEGMENTS)`, so a three-candidate review draws three marks
 * and a one-candidate review draws a single 5px block sitting alone to the left of "0 of 1
 * settled". At that length the strip carries nothing the sentence beside it does not carry
 * exactly, and it reads as a bullet or a stray rule rather than as a measure. Below this the
 * sentence stands on its own; the strip is `aria-hidden` either way, so nothing is lost to a
 * reader who is not looking at it.
 */
const STRIP_FLOOR = 4;

/**
 * How long a list has to be before grouping it by pattern earns its headings.
 *
 * The first review of a lineage has no movement to group on, and the experience doc names
 * exactly that as the open problem: "a wall of forty candidates is still a wall", and the way
 * out is "grouping on something the machine already measured". A pattern is that. But a
 * heading over three rows is a heading that says nothing — the same argument
 * `sharedNamespace` makes one function down — so it only applies where there is a wall.
 */
const WALL = 8;

/** How far through the work this review is, what is left, and how to find one of it. */
function Progress({
  total,
  settled,
  filter,
  onFilterChange,
  counts,
  query,
  onQueryChange,
  matched,
}: {
  total: number;
  settled: number;
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  counts: { attention: number; settled: number; all: number };
  query: string;
  onQueryChange: (query: string) => void;
  /** How many rows the text filter leaves, of the ones the chips would have shown. */
  matched: { shown: number; of: number };
}) {
  const hasKeyboard = useHasKeyboard();
  const segments = Math.min(total, SEGMENTS);
  /**
   * By ratio rather than by index, with both ends of the ratio reserved.
   *
   * A segment index compared against a raw count is only the same question while the two
   * scales are the same, which they stop being at 25 candidates. Comparing ratios fixed
   * that and left a threshold rather than removing one: `Math.round` fills the last mark at
   * 98%, so on a hundred candidates the ninety-ninth settlement rounded 23.76 up to 24 and
   * the whole strip turned to ink while one candidate still wanted a person — and at the
   * other end the first settlement rounded 0.24 down to 0, so a reader who had just decided
   * something saw a strip that had not moved. A full strip now means finished, an empty one
   * means nothing has settled, and every state between is the proportion. The count beside
   * it is exact either way, which is why the strip is allowed to round at all.
   */
  const filled =
    settled >= total
      ? segments
      : Math.min(
          segments - 1,
          Math.max(settled ? 1 : 0, Math.round((settled / total) * segments)),
        );

  return (
    // One row rather than two. Progress spent two stacked lines and about 100px of the first
    // screen on chrome before any work, on a surface whose first rule is that the queue is
    // the product — and the four things in it are all short. They wrap on a narrow screen,
    // which is the row this used to hard-code at every width.
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
      <div className="flex shrink-0 items-center gap-3">
        {/* One segment per candidate, filled as it settles. Ink and rule, never a verdict
            hue: how far through you are is not a grade anything was given. Past `SEGMENTS`
            it is a proportion, and says so on the hover — the count beside it is exact
            either way, which is why the strip is allowed to round. */}
        {total >= STRIP_FLOOR ? (
          <span
            aria-hidden="true"
            title={
              total > segments
                ? "A proportion: each mark stands for more than one candidate."
                : undefined
            }
            className="flex shrink-0 items-center gap-[3px]"
          >
            {Array.from({ length: segments }, (_, index) => (
              <span
                key={index}
                className={cn(
                  "block h-3.5 w-[5px] rounded-xs",
                  // The unfilled mark is the denominator, and it was drawn in `--rule-strong`
                  // — a value declared for 1px hairlines, which on the canvas measures 1.68:1
                  // in light and 2.22:1 in dark. At 5x14px that is not a quiet graphic, it is
                  // an absent one: at the state a reviewer arrives in, 0 of 6 settled, every
                  // mark is unfilled and the whole strip read as a rendering artefact.
                  // `--rule-control` is the ramp's answer to exactly this measurement — the
                  // boundary value declared for the 3:1 a reader needs to find a non-text
                  // graphic — and on the canvas it measures 2.98:1 in light and 3.77:1 in
                  // dark. The light figure is two hundredths short of the floor and is stated
                  // rather than rounded: nothing else on the ramp is closer, the strip is
                  // `aria-hidden` with the exact count printed beside it, and lifting it
                  // would mean minting a boundary token this system does not have. The
                  // figures moved with the v2 ramp; `--rule-strong` was 15% black and is 22%,
                  // which is why the old pair of numbers here read so much lower.
                  index < filled ? "bg-ink" : "bg-rule-control",
                )}
              />
            ))}
          </span>
        ) : null}
        <span className="text-[12.5px] text-ink-2">
          <span className="font-mono font-semibold tabular-nums text-ink">{settled}</span> of{" "}
          <span className="font-mono tabular-nums">{total}</span> settled
        </span>
      </div>

      {/* Three filters was the whole of the navigation, and none of them is "the one about
          SqlAlchemy". A count beside the box rather than under the list, because it is the
          control's own report on what it did — and a count with a control on it is the
          form this document asks numbers to take.

          `flex-1`, because the box carries `w-full` from `controlClass` and its parent was
          content-sized: `width: 100%` against a shrink-to-fit parent resolves back to the
          input's intrinsic `size=20`, so the declared `max-w-[22rem]` was never reached at
          any width and the placeholder was severed mid-word on every screen. */}
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:max-w-[26rem]">
        <Input
          type="search"
          aria-label="Find a candidate in this review"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Find a name, a claim or a pattern"
          // Dense, because this sits in the strip above the queue rather than in a form, and
          // `pointer-coarse:min-h-11` because 32px is not a tap target — the same split every
          // control in the system makes between a pointer and a finger.
          className="h-8 min-w-0 max-w-[22rem] py-1 text-[13px] pointer-coarse:min-h-11"
        />
        {query.trim() ? (
          <span className="shrink-0 text-[12px] text-ink-3">
            <span className="font-mono tabular-nums text-ink-2">{matched.shown}</span> of{" "}
            <span className="font-mono tabular-nums">{matched.of}</span>
          </span>
        ) : null}
      </div>

      {/* The track is what says these are alternatives. Without it a one-of-many group
          resolves to one button and two bare grey words on the canvas, with the distinction
          deferred to a hover — so the row read as one segmented control that had partly
          failed to render. `--sunken` is the ground the elevation contract names for a
          track, and this is the recipe `ui/tabs.tsx` already draws for its solid variant, so
          the two pickers answering the same kind of question are drawn the same way. The
          unpressed chip's hover survives it: the fill half is swallowed by the track, and
          `hover:text-ink` — which is what `Tabs` relies on for the same reason — is not. */}
      <div
        role="group"
        aria-label="Filter the docket"
        className="flex shrink-0 gap-1 rounded-sm border border-rule bg-sunken p-0.5"
      >
        {(
          [
            ["attention", "Attention", counts.attention],
            ["settled", "Settled", counts.settled],
            ["all", "All", counts.all],
          ] as const
        ).map(([id, label, count]) => (
          <ToggleButton
            key={id}
            pressed={filter === id}
            // A count of zero is worth reading — it is telling you there is nothing there —
            // and worth nothing to press. "Settled 0" was a dead end you were invited to
            // walk into; the delta's chips already refused that and this is the same rule.
            disabled={!count && filter !== id}
            onClick={() => onFilterChange(id)}
          >
            {label}
            {/* Separated by weight, not by opacity. A flat 70% was applied on top of whichever
                ink the chip was using: on the pressed chip that is `--ink` and survives, on
                the unpressed chip it is `--ink-3` — the tier whose floor across the four
                grounds is 4.62:1 — and on the `--sunken` track these chips sit in, the
                multiplier took 4.76:1 down to 2.74:1 in light at 12px semibold.
                The count is the informative half of the chip, so it was the half that had
                been made hardest to read. The label keeps `font-semibold` from
                `ToggleButton`; dropping to the normal weight here is the whole separation. */}
            <span className="font-normal tabular-nums">{count}</span>
          </ToggleButton>
        ))}
      </div>

      {/* The keys, beside the control they act on. This sentence used to sit below every
          row — forty rows past the list the shortcuts exist to move through — and named
          four of the keys the handler supports. The full list is behind `?`, which the
          shell binds everywhere.

          Only where there is something to press them on. On a phone this was eleven key
          caps and four verbs — the single densest thing above the list — describing a
          keyboard that is not there, and it sat between the reader and the findings.

          **Guarded twice, and the CSS is the one that cannot be wrong.** `useHasKeyboard`
          subscribes to the same query in JavaScript, which keeps the caps out of the DOM
          entirely — worth having, because they are eleven nodes and a screen reader would
          otherwise read out keys nobody can press. But that hook seeds its state from
          `matchMedia` during render and falls back to `true` where the API is missing, so
          there is a window in which it can answer for a keyboard that is not there: a cold
          load under a device emulator renders the strip perhaps one time in three, which is
          how this was found. A media query in the stylesheet has no such window — it is
          resolved by the engine before the first paint and re-resolved whenever the input
          changes — so it backstops the hook rather than duplicating it. Written as an
          arbitrary variant because the pair is one question; `pointer-coarse` alone would
          keep the caps on a touchscreen laptop, which has both. */}
      {hasKeyboard ? (
        <p className="ml-auto hidden flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-ink-3 [@media(hover:hover)_and_(pointer:fine)]:flex">
          <Key>j</Key>
          {/* The glyph is drawn and therefore hidden, so the cap has to say the key's name
              for anything not looking at the screen. Without it the hint announced as "j k
              walk" — the two keys a reader who has not learned the letter bindings would
              reach for first were the two silently absent from the only place the docket's
              keyboard model is taught. `sr-only` takes it out of flow, so nothing moves. */}
          <Key>
            <ArrowDown aria-hidden="true" className="size-3" />
            <span className="sr-only">Down arrow</span>
          </Key>
          <Key>k</Key>
          <Key>
            <ArrowUp aria-hidden="true" className="size-3" />
            <span className="sr-only">Up arrow</span>
          </Key>
          <span>walk</span>
          <Key>A</Key>
          <Key>P</Key>
          <Key>W</Key>
          <span>decide</span>
          <Key>x</Key>
          <span>select</span>
          <Key>Esc</Key>
          <span>close</span>
          {/* `text-ink-3`, not `text-ink-3/50`. Halving the tier composites to `#aba8a6` on
              the light canvas — 2.04:1, below every step of the declared ink ramp, and
              invisible to `tokens.test.ts`, which measures the three named inks and cannot
              see an alpha written at a call site. `ui/meta.tsx` made the same correction to
              the same character for the same reason. */}
          <span aria-hidden="true" className="text-ink-3">
            ·
          </span>
          <Key>?</Key>
          <span>all keys</span>
        </p>
      ) : null}
    </div>
  );
}

/**
 * A literal keystroke, so it is set in mono.
 *
 * A third cap, and deliberately not the shortcut sheet's or the decision bar's: theirs sit on
 * a panel and on an ink fill respectively, and this one sits in a footnote beside the control
 * it describes, where a key at the sheet's size would outweigh the sentence around it.
 *
 * `--rule-control` rather than `--rule` for the outline, because the outline is the only
 * thing here that says these are keys. At 10.5px on the page canvas `--rule` measures
 * 1.28:1 in light and 1.33:1 in dark, so the caps did not read as caps and the line read as
 * an undifferentiated run of seventeen micro-tokens rather than as keys and verbs. The
 * ramp's answer to a boundary a reader has to find is this token, which on the canvas
 * measures 2.98:1 in light and 3.77:1 in dark — the closest the ramp gets to the 3:1 a
 * non-text graphic is held to, and the same pair the progress strip above states.
 */
function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center rounded-xs border border-rule-control px-1 font-mono text-[10.5px] font-semibold leading-4 text-ink-2">
      {children}
    </kbd>
  );
}

/** The package every row in a group lives in, when they all live in one. Null otherwise. */
function sharedNamespace(findings: Finding[]): string | null {
  // A group of one hoists nothing: there is no repetition to remove, and the row would lose
  // its own context to a heading saying exactly what the row would have said.
  if (findings.length < 2) return null;
  const namespaces = findings.map(
    (finding) =>
      splitQualified(finding.candidate.participants[0]?.qualified_name ?? "").namespace,
  );
  const [first] = namespaces;
  return first && namespaces.every((namespace) => namespace === first) ? first : null;
}

/** Everything on a row a person might be looking for, as one string to match against. */
function searchableText(finding: Finding): string {
  return [
    ...finding.candidate.participants.map((participant) => participant.qualified_name),
    finding.candidate.summary,
    humanise(finding.candidate.pattern),
  ]
    .join(" ")
    .toLowerCase();
}

/**
 * The claim's opening citation of the row's own identifier, split off so it can recede.
 *
 * The group above hoists `ports`, the row's heading says `Clock`, and the server-authored
 * sentence beneath them then opens `ports.Clock is implemented only by…` — so the eye finds
 * no new token for roughly twenty-five characters, on the line that exists to save a reader
 * opening the row. Nothing is rewritten: the sentence is the model's and stays verbatim,
 * word for word and in order. What changes is that its first phrase is set in the mono tier
 * the identifier above it already uses, so the reader's eye starts at the third word.
 *
 * A literal prefix test rather than a parse, because the summary is prose from a model and
 * anything cleverer would be this surface guessing at its grammar. A sentence that does not
 * open with the identifier is left exactly as it arrived.
 */
function splitCitation(summary: string, identity: string): [string, string] {
  return summary.startsWith(`${identity} `)
    ? [identity, summary.slice(identity.length + 1)]
    : ["", summary];
}

/** What a row says about itself once a person, or nobody, has spoken. */
function RowState({ finding, decision }: { finding: Finding; decision?: Decision }) {
  const stale = decisionIsStale(finding, decision);
  if (decision && !stale) {
    const disposition = dispositionOf(decision.disposition);
    return (
      // `min-w-0` and no `shrink-0`. These two spans are the only part of a row that is prose
      // rather than an identifier, and they were the only part with no way not to grow: the
      // longest of them measures about 240px against a content column of about 251px on a
      // 390px phone, which is a fit by a handful of pixels and by nothing else. The meta row
      // around them already wraps, so the sentence takes its own line when it cannot fit
      // beside the pattern, and wraps inside itself when even that is not enough.
      <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] font-semibold text-ink-2">
        <Mark shape={disposition.glyph} className="size-[13px] shrink-0" />
        {disposition.label} by the team
      </span>
    );
  }
  if (stale && decision) {
    // The whole sentence, not the word "stale": what a reader needs is the two verdicts, in
    // the order they happened, because that is the entire reason the row is back.
    return (
      <span className="flex min-w-0 items-center gap-1 text-[11.5px] font-semibold text-ink">
        <DriftedIcon className="size-[13px] shrink-0" />
        Decided against {verdictOf(decision.finding_verdict).label.toLowerCase()}, now{" "}
        {verdictOf(finding.verdict).label.toLowerCase()}
      </span>
    );
  }
  return null;
}

/**
 * One candidate, as a line you can read and a panel you can open.
 *
 * The collapsed row carries three things and no more: what it is, what the model called it,
 * and what it claims — that last one being the whole reason this works. A rail of leaf names
 * made a reader open every row to find out whether it mattered. A sentence per row means most
 * rows never have to be opened at all.
 */
function DocketRow({
  review,
  finding,
  decision,
  delta,
  lineage,
  lineageDepth,
  open,
  takeFocus,
  hoistedNamespace,
  selected,
  selecting,
  link,
  onSelect,
  onToggle,
  onAnswer,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  decision?: Decision;
  /** Where this candidate stands against the previous review, or null on a first review. */
  delta: string | null;
  lineage: Review[];
  /** How deep the lineage is according to the listing, for the strip's reserved room. */
  lineageDepth: number;
  open: boolean;
  /**
   * Whether the keyboard should follow the cursor onto this row.
   *
   * Only when the docket moved the cursor itself — deciding advances to the next row that
   * wants a person, and the control that was pressed unmounts with the row it was on, so
   * focus falls to `<body>` and the next Tab restarts at "Skip to content". Not on first
   * paint and not when somebody clicked this row, where focus is already where they put it.
   * The clarification round has done this since it was written; the docket, which is the
   * surface `docs/experience.md` says is worked from the keyboard, did not.
   */
  takeFocus: boolean;
  hoistedNamespace?: string;
  selected: boolean;
  /** Whether anything at all is selected, which is what puts the boxes on screen. */
  selecting: boolean;
  /** The address of this one finding, for handing it to somebody else. */
  link: string;
  onSelect: (selected: boolean) => void;
  onToggle: () => void;
  onAnswer?: () => void;
  onOpenContext?: () => void;
}) {
  const descriptor = verdictOf(finding.verdict);
  const identity = finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary;
  const { namespace, leaf } = splitQualified(identity);
  const settled = !needsAttention(finding, decision);
  const [citation, claim] = splitCitation(finding.candidate.summary, identity);
  const panelId = `finding-panel-${finding.candidate.id}`;
  const ref = useRef<HTMLElement>(null);

  // Opening a row that the keyboard walked to has to bring it into view, or `j` past the
  // fold silently expands something below the screen.
  //
  // The article rather than the button inside it, which is what this used to hold. Two things
  // were wrong with the button: `scroll-margin-top` applies to the element being scrolled
  // into view, so the margin below — the whole point of it — sat on an ancestor and never
  // applied; and the button starts below the article's top edge, so even the correct margin
  // would have left the verdict edge and the row's heading above the fold.
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    ref.current?.scrollIntoView?.({ block: "nearest" });
    // `preventScroll`, because the line above has already decided where this row sits and a
    // second scroll from the focus call would fight it.
    if (takeFocus) button.current?.focus({ preventScroll: true });
  }, [open, takeFocus]);

  return (
    <article
      ref={ref}
      aria-labelledby={`finding-${finding.candidate.id}`}
      className={
        // The bottom rule moved to the `<ul>`, as `divide-y divide-rule`, and this is the
        // whole of why. `border-b … last:border-b-0` was written here, on an `<article>` that
        // is the only child of its own `<li>` — so `:last-child` matched on every row, the
        // rule was compiled and never painted, and six candidates rendered as one unbroken
        // sheet. Sibling position is a fact the parent knows and a child cannot, so the rule
        // now lives where the answer is.
        //
        // 48px of opaque topbar and 44px of pinned surface strip, and the docket scrolls with
        // the page — so a row walked *up* to with `k` was aligned flush with the viewport and
        // landed underneath both, hiding the identifier and the verdict of the row just
        // arrived at. 96px clears the pair with four to spare. It was 56px when only the
        // topbar was pinned; the strip was pinned afterwards and this is the measurement that
        // had to move with it.
        //
        // `relative`, because the verdict edge is drawn as a positioned span rather than as
        // this element's own `border-l`. Neither `bg-surface` on an open row nor `bg-transparent`
        // on a settled one is here any more: the `<ul>` around them is already `bg-surface`,
        // so both composited to the colour underneath them and said nothing. A row at rest
        // has no ground of its own; what says a row is open is the panel that appears below
        // it, which is not something a reader can miss.
        "relative scroll-mt-24"
      }
    >
      {/* The verdict as an edge, running the full height of its row.
          A docket is worked down a column, and the question asked of the whole column at
          once — where does one verdict stop and the next begin — is not one a mark inside a
          row can answer: at any size that fits beside a name, a glyph has to be looked *at*.
          An edge is read without being looked at, costs no horizontal space, and is a rule
          rather than a card, which is the structure this system already uses.

          The question used to be "where does the red start", because red was the only hue in
          the system and the other two verdicts were greys. Three signals is what makes the
          column worth scanning at all: an amber run and a green run are now two shapes rather
          than one column of ink with a red interruption in it.

          It was `inset-y-1`, four pixels of air at each end, and that answered a real defect
          the wrong way round. The defect: a run of same-verdict rows — the common case on a
          second visit — fused into one unbroken bar down the whole list that read as the
          panel's own border rather than as six verdicts. The wrong way round: 4px above a
          row boundary and 4px below it, with the 1px divider between them, is a **nine
          pixel** white notch cut into a red edge. Measured on the docket at 1440: an edge
          from y=992 to y=1073 in an 89px row, the next starting at y=1082. Nine pixels is
          not a boundary, it is a break — nine times every other seam on this surface — and
          a break in a rule reads as a rendering fault rather than as a decision. It was
          reported as a gap in the red, which is exactly what it is.

          The separation the bar needed was already on the page. `divide-y` on the `<ul>`
          puts a `--rule` hairline on every row boundary, and that hairline runs the `<li>`'s
          whole width — across the three pixels this edge occupies as well as the row's
          words, because both start at the list's content box. So the edge is broken at each
          row boundary by exactly the one pixel that separates everything else here, at a
          line the eye already knows the meaning of. Nothing had to be invented, and the
          notch costs eight pixels of the verdict on every row to say what the divider says
          for free.

          The two do not overlap; they abut, and that is the mechanism rather than a
          quibble. This span is positioned against the `<article>`, so `inset-y-0` resolves
          against the article's box — which stops exactly where the `<li>`'s `border-bottom`
          starts. Measured at 1440: the first row's edge ends at y=1077.03 and the hairline
          occupies 1077.03 to 1078.03. Hang the same span off the `<li>` instead and
          `inset-y-0` would resolve against a box that *includes* that border, the colour
          would paint straight over the hairline, and a run of one verdict would fuse for
          real. The test below catches that; this paragraph is why.

          What it looks like, said honestly, because the inset was written on a mis-reading
          of it: six identical verdicts read as one column of colour with hairline ticks in
          it, not as six separate marks. That is correct. Six identical verdicts *are* one
          run, and the question this edge exists to answer — where does one verdict stop — is
          answered better by a continuous shape than by six pieces of one. What made the old
          bar a defect was the other half: that it could be taken for the panel's own chrome.
          It cannot be. The panel's border is one pixel of `--rule` on all four sides — 11%
          black in light, 12% white in dark. This is three pixels of an opaque verdict hue on
          one — `--material-edge`, `--held-edge` or `--cleared-edge`, the graphic tier of the
          three signals, each of which clears the 3:1 a meaningful graphic is held to on all
          four grounds in both themes. Nothing else about the panel is coloured. Where
          consecutive verdicts differ the column visibly breaks into per-row segments, which
          is the only place that difference is worth seeing.

          Two of those three used to be greys — `--held` was the ink and `--cleared` was
          `--ink-3` — so a docket of amber and green rows was one column of two ink values
          with an occasional red in it, and the edge could only answer the question for one of
          the three verdicts it was drawn for. That is the defect the ramp change was written
          to repair, and it is why this edge is worth three pixels rather than one.

          That last sentence was written from the design and went a long time without a run
          behind it. Offline — which is every browser check — the judge holds or clears on one
          question asked about the review's *case* rather than about a candidate
          (`reasoning/adapters/deterministic.py:105`), so all six candidates come back with
          one verdict and no run had ever drawn two hues in one column.
          `test_a_rail_states_the_verdict_of_its_own_row` in `tests/browser/` deals three
          verdicts across one docket and measures the boundary; it says in its own docstring
          what dealing them costs.

          A positioned span rather than the article's own `border-l` for a reason that
          outlived the inset: an open row's argument and decision bar are inside this article,
          and a border would take the row's padding with it. The class is still `TONE_EDGE`
          from `ui/meta.tsx`, which is where this system's hues are named; which of them a row
          gets is `descriptor.tone`, decided by the one verdict table in `lib/format` and
          never picked here. The span is 3px wide and its left border is 3px, so the border is
          the whole of it.

          Which hue a verdict gets was nobody's claim until that test. `TONE_EDGE.held`
          retyped as `border-l-material-edge` paints every held candidate in the alarm colour
          and the whole repository stayed green, because `ui/verdict-hues.test.ts` asked only
          *where* the three hues may be named. It asks what each is paired with now, and the
          browser test asks the rest: that this row, on screen, is painted the colour its own
          verdict names.

          Both halves — continuous down a run, never touching across a boundary — are held by
          `test_the_verdict_edge_is_cut_only_by_the_row_rule` in `tests/browser/`. They are
          geometry, so jsdom cannot see either, and the whole lesson of the notch is that a
          class nothing can fail is not a decision anybody checked. */}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 z-[1] w-[3px] border-l-[3px]",
          settled ? "border-l-transparent" : TONE_EDGE[descriptor.tone],
        )}
      />

      {/* The row's own name, for anything that reads the document rather than looks at it —
          heading navigation being the fastest way down a long list with a screen reader.
          The whole qualified name and the claim, because two candidates in one package share
          a name and a column of identical headings is a column of nothing. What is *drawn*
          drops the namespace where the group above it already said it, which is a different
          question.

          `h3`, under the group heading's `h2`. It was the other way round — the group was an
          `h3` and every row inside it an `h2` — so heading navigation reported each candidate
          as a peer of the section above it and jumping by heading walked *out* of the group
          rather than through it. */}
      <h3 id={`finding-${finding.candidate.id}`} className="sr-only">
        {identity} — {finding.candidate.summary}
      </h3>

      {/* The row's hover ground is painted here, on the element that is the whole row, and
          not on the button inside it. The button is one of two or three flex items — the
          checkbox column stands before it and, on an open row, the copy control after it —
          so a ground the button painted stopped 28px short of the row's left edge and left a
          full-height strip of `--surface` down the side of every hovered row, a whole step of
          the ramp lighter than the row beside it, with the verdict edge and the checkbox
          stranded on the wrong colour. A row is one thing to the eye, so its ground has to be
          one thing too.

          Only the width changed; the colour is the one this row has always hovered to, and
          the argument for it moved up here with it. The product's most-clicked control had
          `--surface-2` painted on a `<ul>` that is already `--surface`, which under the v1
          ramp was five levels and about 1.04:1 in either theme — below the point at which a
          background change is perceptible at all. The v2 ramp widened that pair to 1.08:1 in
          light and 1.11:1 in dark, so it is a step now rather than a typo; it is still the
          wrong step, because `--surface-2` is the token for a strip *inside* a panel and
          `--sunken` is the one the elevation contract assigns to a quiet inset, which is what
          a hovered row is. That pair measures 1.26:1 in light and 1.28:1 in dark, and it is
          what the revision rail beneath this list already uses, so the two agree.
          Unconditional, because an open row's header is still the control that closes it.

          `group`, for the checkbox: what reveals the box is a pointer anywhere in the row. */}
      <div className="group flex items-stretch transition hover:bg-sunken">
        {/* Outside the row's own button, because a checkbox inside a button is a control
            inside a control. It is invisible until it is wanted — the row hovered, the box
            focused, or anything at all selected — so a docket nobody is bulk-deciding looks
            exactly as it did. The reveal is `group-hover` off the wrapper and was `hover` on
            this label: the label is 28px wide and fully transparent, so the control
            announced itself only to somebody who already knew where it was. `focus-within`
            stays here, on the box's own parent, which is the tighter scope for it.

            On a coarse pointer the box is simply there — hover is the affordance that
            reveals it, and a finger has none — so the label has to be pressable as it
            stands: `pl-4 pr-3.5` around a 15px box is a 45px strip, over the 44 the charter
            asks for, and the label stretches to the row's full height for the other axis. */}
        <label
          className={cn(
            // Centred on the row, with the verdict mark, the trajectory and the copy
            // control — every piece of a row's chrome, as against its text, which stays
            // where it starts.
            //
            // This reverses the reasoning that stood here, and the reasoning was not wrong:
            // a row is 89px tall with a one-line claim and 108px with two, so a centred
            // column lands at a different height on every row, and a surface read by
            // scanning down a column pays for that. What it missed is that the chrome was
            // not reading as a column in the first place. It was reading as a band across
            // one row — a box, a mark, a name, and 700px away a strip of the same circles —
            // and a band pinned to the top of a three-line row sits visibly above the
            // weight of the thing it belongs to. The user reported it twice. The cost is
            // named and accepted: the boxes no longer form a straight edge down a docket of
            // mixed row heights.
            "flex shrink-0 cursor-pointer items-center pl-3 transition sm:pl-4",
            "pointer-coarse:pl-4 pointer-coarse:pr-3.5",
            selected || selecting
              ? "opacity-100"
              : "opacity-0 pointer-coarse:opacity-100 focus-within:opacity-100 group-hover:opacity-100",
          )}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelect(event.target.checked)}
            className="size-[15px] accent-[var(--ink)]"
          />
          <span className="sr-only">Select {identity}</span>
        </label>

        <button
          type="button"
          ref={button}
          data-candidate={finding.candidate.id}
          aria-expanded={open}
          aria-controls={panelId}
          title={identity}
          onClick={onToggle}
          // No ground of its own, and no `transition` either: the hover state this control
          // answers to is painted by the wrapper above, which is the element that is the
          // whole row rather than the middle of it, and the argument for the colour moved up
          // there with the class. Nothing else here animates — the chevron below carries its
          // own.
          //
          // The ground moved; the affordance did not. This is still the row's control, still
          // `min-h-14`, still the thing that takes focus and the Enter key.
          className="flex min-w-0 flex-1 min-h-14 items-start gap-3 px-3 py-3 text-left sm:px-4"
        >
          {/* `self-center` rather than the button's own `items-start`: the button has to
              stay top-aligned for the text block beside it, which is three lines and grows,
              and only the mark travels with the chrome. */}
          <Mark
            shape={descriptor.glyph}
            className={cn(
              "size-[15px] shrink-0 self-center",
              settled ? "text-ink-3" : TONE_TEXT[descriptor.tone],
            )}
          />

          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {/* The namespace is context and is dropped where the group above already said it;
                  the leaf is the identity and is never dropped. The whole name stays on the
                  hover and in the accessible name, because a row that only ever says `Clock`
                  cannot be told from the three other `Clock`s in the repository. */}
              {hoistedNamespace ? <span className="sr-only">{identity}</span> : null}
              {!hoistedNamespace && namespace ? (
                <span className="min-w-0 truncate font-mono text-[11px] text-ink-3">
                  {namespace}.
                </span>
              ) : null}
              <span
                aria-hidden={hoistedNamespace ? "true" : undefined}
                className={cn(
                  "font-mono text-[14px] font-medium leading-[1.35] [overflow-wrap:anywhere]",
                  settled ? "text-ink-2" : "text-ink",
                )}
              >
                {leaf}
              </span>
              {/* The word stays when the row settles; only the hue is withdrawn. A settled row
                  used to drop it entirely, so under the Settled filter — the surface for "what
                  did we decide, and about what" — a waived material finding was indistinguishable
                  from a cleared one. A verdict states itself four ways in this system — a glyph,
                  a word, a left edge and a hue — and settling withdraws the two that are colour,
                  which leaves the two that are not. Render the row in greyscale and it says
                  exactly what it said before, which is the test that rule exists for. */}
              {/* The hue is the only thing overridden here, and it took a scale change to get
                  to that. `Label` used to be 10px — correct for a section eyebrow and wrong
                  for a verdict: it set the word smaller than the row's own metadata and less
                  than half the size of its claim, so the four lines of a row ranked by size in
                  the reverse of the order the docket is scanned in, and the verdict word — one
                  of the three things the charter says a verdict must always state — was the
                  first thing to disappear when the column was squinted at. This row carried a
                  local `text-[11px]` for that. v2 moved the label row of the scale to 11px for
                  the same reason everywhere, so the correction is the system's now and the
                  override is gone with it. */}
              <Label as="span" className={settled ? undefined : TONE_TEXT[descriptor.tone]}>
                {descriptor.label}
              </Label>
            </span>

            {/* The claim. This is the line that makes the list readable, and the reason most
                rows never need opening — which is also why it is the one prose block in the
                review that had no measure on it: at 13px in a 1050px column it set 165
                characters to the line, two and a half times the 60–64ch the type contract
                names, on the most-read sentence in the product. */}
            <span
              className={cn(
                "mt-1 max-w-[64ch] text-[13px] leading-[1.5] text-ink-2",
                open ? "block" : "line-clamp-2",
              )}
            >
              {citation ? <span className="font-mono text-ink-3">{`${citation} `}</span> : null}
              {claim}
            </span>

            <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-3">
              <span>{humanise(finding.candidate.pattern)}</span>
              {/* The separator as its own element rather than as a literal `· ` inside the
                  phrase. Written into the string, its two sides were set by two mechanisms at
                  two values — the container's `gap-x-2.5` before it and a single space after
                  — so the dot had 12px on one side and 5px on the other and attached itself
                  to the next word, and a screen reader read it aloud as punctuation inside
                  the phrase. Both gaps now come from the same `gap-x-2.5`. */}
              {delta && delta !== "unchanged" ? (
                <>
                  <span aria-hidden="true" className="text-ink-3">
                    ·
                  </span>
                  <span>{humanise(delta)} this review</span>
                </>
              ) : null}
              <RowState finding={finding} decision={decision} />
            </span>
          </span>

          {/* `self-center`, so the strip and the chevron ride the row's own centre line with
              the checkbox, the verdict mark and the copy control. The `pt-0.5` that used to
              sit here is gone with them.

              This is the second answer to the same complaint and the first one was too
              literal. The strip's marks were put on the 20.5px line the checkbox and the
              verdict mark shared, which made the marks agree and left the numbers under them
              hanging below — so the right end of the row still read as sitting lower than the
              left, because what an eye compares at that distance is the block, not the row of
              circles inside it. Centring the whole strip is what makes the two ends of a row
              look like two ends of one row.

              The strip once the heavy reviews query has landed, and the room it will take
              until then. Sized from the cheap listing's depth rather than from a flat width,
              so the row is laid out once. */}
          <span className="flex shrink-0 items-center gap-2 self-center">
            {lineage.length > 1 ? (
              <CandidateTrajectory
                lineage={lineage}
                candidateId={finding.candidate.id}
                currentReviewId={review.id}
                className="hidden md:flex"
              />
            ) : (
              <TrajectoryPlaceholder depth={lineageDepth} className="hidden md:flex" />
            )}
            <ChevronDown
              aria-hidden="true"
              className={cn("size-4 text-ink-3 transition", open && "rotate-180")}
            />
          </span>
        </button>

        {/* Only on the row being read. Handing a colleague one finding is not something a
            reader does forty times down a list, and forty copy controls on a docket would be
            forty things to skip past. */}
        {open ? (
          <div className="flex shrink-0 items-center pr-2">
            <CopyButton value={link} label="Copy link to this finding" />
          </div>
        ) : null}
      </div>

      {open ? (
        // `--rule-strong`, the same hairline the decision block below already uses. This is
        // the seam where the row's identifiers stop and the model's argument starts — "the
        // machine assembles, the model judges, the person decides" is the most distinctive
        // idea in the product and it was drawn at a whisper, one value away from invisible,
        // so five stacked zones of an open finding read as one flat sheet. Marked rather than
        // moved: giving the block a ground would paint it the same as the Measured strip
        // inside it, which is the one band that already earns one.
        <div id={panelId} className="animate-expand border-t border-rule-strong">
          <FindingBody
            review={review}
            finding={finding}
            onAnswer={onAnswer}
            onOpenContext={onOpenContext}
          />
          <div className="border-t border-rule-strong px-4 py-4 sm:px-5">
            <DecisionBar review={review} finding={finding} />
          </div>
        </div>
      ) : null}
    </article>
  );
}

/**
 * One disposition, taken on everything that is checked.
 *
 * `/api/decisions/bulk` and `decide_many` have existed all along and had never been called:
 * twelve cleared candidates cost thirty-six clicks. What kept this out was a real argument
 * and a narrower one than it looked — *a bulk waiver needs one reasoning string for twelve
 * different candidates, and a reason that fits twelve findings is usually not a reason.*
 * That is an argument about waiving. Accept and Park already take `reasoning: null`, so they
 * are offered here and Waive is not, which needs no justification beyond the sentence the
 * experience doc already carries.
 */
function BulkBar({
  review,
  selected,
  onClear,
  onDecided,
}: {
  review: Review;
  selected: string[];
  onClear: () => void;
  /** What was decided, so the docket can keep the rows listed and say what happened. */
  onDecided: (candidateIds: string[], message: string) => void;
}) {
  const client = useQueryClient();
  const branchId = review.repository.branch_id;

  const decide = useMutation({
    mutationFn: (disposition: "accept" | "park") =>
      api.decideMany(review.id, selected, disposition),
    onSuccess: async (_result, disposition) => {
      const decided = [...selected];
      onClear();
      // Written back rather than merged: a bulk answer is a set of rows, and re-reading the
      // branch is one request either way. The row-by-row bar is the one that cannot afford it.
      await client.invalidateQueries({ queryKey: ["decisions", branchId] });
      onDecided(
        decided,
        `${plural(decided.length, "candidate")} ${dispositionOf(disposition).label.toLowerCase()} by the team.`,
      );
    },
  });

  /** The disposition in flight, so the button that was pressed is the one that spins. */
  const running = decide.isPending ? decide.variables : null;

  return (
    <div className="grid gap-2.5 rounded-lg border border-rule-strong bg-surface px-4 py-2.5 shadow-rim">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-[13px] font-semibold text-ink">
          {plural(selected.length, "candidate")} selected
        </span>
        <div className="flex flex-wrap items-center gap-2">
          {/* A spinner in the pressed button, because this request fans out over a dozen
              candidates and then invalidates and refetches the whole branch. The only
              feedback it had was three buttons going inert, which is indistinguishable from
              a press that did nothing. The per-row `DecisionBar` has done both of these
              since it was written; this bar is where the twelve-candidate case lives. */}
          <Button
            variant="secondary"
            size="sm"
            disabled={decide.isPending}
            onClick={() => decide.mutate("accept")}
          >
            {running === "accept" ? <Spinner label="" /> : null}
            Accept all
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={decide.isPending}
            onClick={() => decide.mutate("park")}
          >
            {running === "park" ? <Spinner label="" /> : null}
            Park all
          </Button>
          <Button variant="ghost" size="sm" disabled={decide.isPending} onClick={onClear}>
            Clear
          </Button>
        </div>
        {/* Waiving is the one disposition that cannot be taken in a batch, and a reader who
            has just been offered two of three is owed the reason. */}
        <span className="text-[11.5px] leading-5 text-ink-2">
          Waiving stays one at a time: a reason that fits twelve findings is not a reason.
        </span>
      </div>

      {/* A failure across twelve candidates used to look exactly like a decision that was
          never pressed: the buttons dimmed, re-enabled, and nothing on screen said anything.
          The selection needs no rescuing — `onClear` is called inside `onSuccess`, so a
          refusal has already left every checked row checked — which is what makes offering
          the same disposition again the whole of the way out. */}
      {decide.error ? (
        <ErrorNotice
          error={decide.error}
          title="Those decisions were not recorded"
          action={
            decide.variables ? (
              <Button
                variant="secondary"
                size="sm"
                disabled={decide.isPending}
                onClick={() => decide.mutate(decide.variables!)}
              >
                Try {dispositionOf(decide.variables).label.toLowerCase()} again
              </Button>
            ) : null
          }
        />
      ) : null}
    </div>
  );
}

/**
 * The question the review is waiting on, listed as what it is: the first item.
 *
 * Or the record of the round once it has been answered, which is the same item at its next
 * state rather than a different one. `rejudging` is the run the answers started, and while it
 * is in flight the card stays where it was and says what was recorded and what is happening
 * because of it. It used to vanish — the page navigated to the run's own address, and the
 * round a person had just spent ten minutes on left the screen along with everything else.
 */
function ClarificationCard({
  review,
  answers,
  rejudging,
  notice,
  open,
  onToggle,
}: {
  review: Review;
  answers: RoundAnswers;
  /** The rejudgement these answers started, while it is still running. */
  rejudging: ReviewRun | null;
  notice?: ReturnType<typeof useRejudgementNotice>;
  open: boolean;
  onToggle: () => void;
}) {
  const recorded = !awaitsAnswers(review) && rejudging;
  // The docket row twenty lines away names what its disclosure reveals; this one announced
  // that it was expanded and never said what it had expanded, on the docket's first item and
  // the one thing nothing below it can be finished without.
  const panelId = `round-panel-${review.id}`;
  return (
    <section className="relative overflow-hidden rounded-lg border border-rule bg-surface shadow-rim">
      {/* The amber as an edge, which is the device every row below this card already uses.
          Same span, same three pixels, same `z-[1]` over the ground it is drawn on. Two
          differences: a card is one item, so nothing cuts the edge into per-row segments; and
          this section has a border, so `inset-y-0` resolves against the padding box and the
          card's own hairline stays wrapped around the amber rather than being replaced by it.

          An unanswered round used to say "waiting on you" by painting its whole header in
          `--held-soft` — a chromatic fill about 1,000x64px, on the surface whose first rule is
          that a hue arrives as a mark. The wash tokens that replaced the `-soft` ones are
          capped at the size of a pill for exactly this reason: past that a hue has stopped
          signalling and started tinting a panel, and a reader who meets four tinted panels
          stops reading any of them as meaning anything. So the ground went neutral and the
          signal moved onto the three carriers a verdict states itself with everywhere else in
          this file — a glyph, a word and a left edge.

          `--held-edge` rather than `--held`, because three pixels of colour is a graphic:
          the graphic tier is the saturated half of the pair and has 3:1 to clear, where the
          text tier is held to 4.5:1 and would spend that headroom on a bar nobody reads a
          letterform in.

          Only while the round is open. A recorded round is not waiting on anybody, and an
          edge it kept would be the loudest thing on a card whose whole message is that the
          work has moved on. Positioned rather than a `border-l` on the section for the reason
          the row's is: this way the two states are the same geometry, and the card's own
          `overflow-hidden` cuts the edge square against the `rounded-lg` corner instead of
          tapering it into the hairline above it. */}
      {recorded ? null : (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-[3px] border-l-[3px] border-l-held-edge"
        />
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className={cn(
          // `group`, for the chevron below. This card is the docket's first item and, by its
          // own copy, the blocker for everything under it, and it was the one row-shaped
          // control in the feature that answered the pointer with nothing at all. The fill
          // still cannot carry it, for a reason that survived the ground moving: fill is what
          // says *which of the two states this is* — `--surface-2` for a header strip on a
          // panel, `--sunken` for the answered round receding into an inset — so a hover that
          // moved the fill would be a state change drawn in the one channel already spoken
          // for. The glyph carries it instead, on both branches and in both themes.
          "group flex w-full min-h-14 items-start gap-3 px-4 py-3 text-left transition sm:px-5",
          recorded ? "bg-sunken" : "bg-surface-2",
        )}
      >
        {/* The glyph half of the same statement, in the text tier: this one sits at 15px
            beside a sentence rather than as a rule down a card, and it is read as a mark. */}
        <Mark
          shape={recorded ? "check" : "pause"}
          className={cn(
            "mt-px size-[15px] shrink-0",
            recorded ? "text-ink-3" : "text-held",
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold text-ink">
            {recorded
              ? `Round ${roundOf(review)} answered`
              : `${plural(review.questions.length, "question")} unanswered`}
          </span>
          {/* "re-judges what it touches" invited the reading that answering is cheap and
              local. It is neither: `select_rejudgements_node` returns every candidate,
              because an answer is about intent and intent bears on all of them. The API
              layer already said so — `api.ts`, "minutes of model work" — and the surface a
              person actually presses the button on did not. */}
          <span className="mt-0.5 block text-[12.5px] leading-[1.5] text-ink-2">
            {recorded
              // No claim about rejudging: answering does not always rejudge. *Conclude with
              // remaining uncertainty* seals the review without selecting a candidate, and
              // the note below reads the run's own stage rather than assuming.
              ? "Your answers are on this review's case revision."
              : "Nothing below can be finished until these are answered. Answering completes this review's case revision and judges every candidate again, which is minutes of model work."}
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "mt-0.5 size-4 shrink-0 text-ink-3 transition group-hover:text-ink",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <div id={panelId} className="animate-expand border-t border-rule py-3">
          {recorded && rejudging ? (
            <RoundRecorded
              review={review}
              answers={answers}
              run={rejudging}
              notice={notice}
            />
          ) : (
            <ClarificationRound review={review} answers={answers} bare />
          )}
        </div>
      ) : null}
    </section>
  );
}

/** Which round of this revision is on screen. */
function roundOf(review: Review): number {
  return review.questions[0]?.round ?? review.round;
}

/**
 * What was just recorded, and what it set going — said where the reader pressed the button.
 *
 * The estimate is here rather than only beside the lineage because this is the moment of
 * commitment: half an hour of model work starts on this press, and a number a reader has to
 * scroll to find is a number they find out about afterwards. `NotifyWhenDone` is here for the
 * same reason — the point of work that survives a closed tab is being told it does.
 *
 * The answers come from the round's own state, which the page holds, so they survive this
 * card being collapsed and reopened. A reload loses them and the block says so rather than
 * inventing them; by then the review has been superseded and its banner points at the round
 * that actually holds the answers.
 */
function RoundRecorded({
  review,
  answers,
  run,
  notice,
}: {
  review: Review;
  answers: RoundAnswers;
  run: ReviewRun;
  notice?: ReturnType<typeof useRejudgementNotice>;
}) {
  const said = review.questions.map((question) => ({
    question,
    value: answers.values[question.id]?.trim() || "",
    skipped: answers.skipped.has(question.id) || !answers.values[question.id]?.trim(),
  }));
  // Whether the page still holds what was said, which is not the same as anything having been
  // typed. A skip is an answer — the deliberate kind, and the one the round's other button
  // produces for every question at once — and it carries no text. Asking "did anybody type
  // something" meant a round answered entirely by skipping reported itself as unreadable and
  // labelled every deliberate skip "Answered", which is the one distinction this product
  // keeps everywhere else.
  const held = review.questions.some(
    (question) =>
      Boolean(answers.values[question.id]?.trim()) || answers.skipped.has(question.id),
  );
  return (
    <div className="grid gap-3 px-4 sm:px-5">
      <ol className="grid gap-2">
        {said.map((item) => (
          <li key={item.question.id} className="rounded-md border border-rule bg-surface-2 px-3 py-2">
            <div className="text-[12.5px] font-semibold leading-5 text-ink">
              <Prose>{item.question.text}</Prose>
            </div>
            <div className="mt-1 text-[12.5px] leading-5 text-ink-2">
              {held ? (
                item.skipped ? (
                  <span className="text-ink-3">Recorded as skipped</span>
                ) : (
                  item.value
                )
              ) : (
                // A reload between answering and this render loses the text, and the block
                // says what it knows rather than where to find it: what was said is on the
                // case revision this review opened, and the snapshot on screen is the one
                // taken *before* it — so "reopen this review" pointed at a record that will
                // never hold these answers. The next one does, and its banner links there.
                <span className="text-ink-3">Recorded on this review's case revision</span>
              )}
            </div>
          </li>
        ))}
      </ol>
      <RejudgementNote run={run} notice={notice} />
    </div>
  );
}

/**
 * The end of the work, said as the end of the work.
 *
 * Reaching the bottom is the one moment in the product worth marking, and it used to be an
 * empty rail reading "Nothing here". Marked in ink rather than in the cleared green: "worked
 * through" is the state the page is in, not a verdict anything was given.
 */
function WorkedThrough({
  total,
  decided,
  onReadReport,
}: {
  /** Every candidate in the review, which is the one total the sentence partitions. */
  total: number;
  decided: number;
  onReadReport?: () => void;
}) {
  return (
    // `h2`, a sibling of the group headings rather than a child of one. This block stands
    // where a section's list would, under the page's `h1`.
    <div className="flex flex-col items-center rounded-lg border border-rule bg-surface px-5 py-10 text-center shadow-rim">
      <span className="flex size-9 items-center justify-center rounded-full border border-rule-strong text-ink">
        <Mark shape="check" className="size-[17px]" />
      </span>
      <h2 className="mt-3 text-[15px] font-semibold tracking-tight text-ink">Worked through</h2>
      {/* One total, partitioned. This used to add two overlapping sets and call the second
          "others": a cleared candidate that was accepted is in both, so a three-candidate
          review that came back cleared and was then accepted read "3 candidates were decided
          by the team and 3 others came back cleared" — six implied where there were three.
          At the other end a first review read "0 candidates were decided by the team and 7
          others came back cleared", where "others" named nothing. A review is worked through
          exactly when every candidate is either decided or cleared, so those two are the
          partition and the sentence says so. */}
      <p className="mt-1.5 max-w-[52ch] text-[13px] leading-6 text-ink-2">
        Nothing in this review is waiting on a person.{" "}
        {decided
          ? `${decided} of ${plural(total, "candidate")} ${decided === 1 ? "was" : "were"} decided by the team${
              decided === total ? "." : "; the rest came back cleared."
            }`
          : `All ${plural(total, "candidate")} came back cleared.`}
      </p>
      {/* A way on, not a dead end: the record of what was just decided, and the next review
          against it. Reaching the bottom of the list is the moment both are wanted. */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {onReadReport ? (
          <Button variant="secondary" size="sm" onClick={onReadReport}>
            Read the report
          </Button>
        ) : null}
        <ButtonLink to="/start" variant="ghost" size="sm">
          Run the next review
        </ButtonLink>
      </div>
    </div>
  );
}

export function Docket({
  review,
  findings,
  decisions,
  lineage,
  answers,
  filter,
  onFilterChange,
  openId,
  onOpen,
  settledHere,
  onSettledHere,
  selected,
  onSelectedChange,
  onOpenContext,
  onReadReport,
  onReadDelta,
  lineageDepth = 0,
  rejudging = null,
  rejudgementNotice,
}: {
  review: Review;
  /**
   * The review's findings, in the order a reviewer meets them.
   *
   * Sorted by the page rather than here. The sort is the only expensive thing this list does
   * and both this and the head's counts want the same answer, so doing it in each of them
   * meant sorting the whole review twice on every render of the page — every keystroke,
   * every filter press, and every four-second run poll.
   */
  findings: Finding[];
  decisions: Map<string, Decision>;
  lineage: Review[];
  answers: RoundAnswers;
  /**
   * The rejudgement this review's answers started, while it is still running.
   *
   * Keeps the round on screen after it has been answered, as the record of what was said and
   * what it set going. Without it the item vanished the moment the server accepted the
   * answers — the one thing on the docket that had just been worked on, gone with no sign
   * that anything had happened.
   */
  rejudging?: ReviewRun | null;
  /**
   * The page's offer to notify when the rejudgement lands.
   *
   * Owned above this component because this component does not outlive the run it is about:
   * the run leaves `/api/reviews/runs` the moment it finishes, so the card unmounts and any
   * effect inside it goes too. See `useRejudgementNotice`.
   */
  rejudgementNotice?: ReturnType<typeof useRejudgementNotice>;
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  /** The candidate id whose row is open, or `"clarification"`, or null for none. */
  openId: string | null;
  onOpen: (id: string | null) => void;
  /**
   * Candidates that settled while you were looking at them, and therefore stay listed.
   *
   * Deciding a candidate settles it, so under the Attention filter the row you just acted on
   * no longer matches — and a row that vanishes at the instant you act on it takes with it
   * any way to check what you did, or to change your mind. The counts move immediately,
   * because they are the truth; the row stays, showing the decision on it, until you change
   * the filter and ask the list a different question.
   *
   * Held by the page, because this component is unmounted by a trip to the Report and back —
   * which is exactly the trip the retained row is there to survive.
   */
  settledHere: string[];
  onSettledHere: (update: (kept: string[]) => string[]) => void;
  /** The candidates checked for a decision taken on all of them at once. */
  selected: string[];
  onSelectedChange: (update: (current: string[]) => string[]) => void;
  onOpenContext?: () => void;
  onReadReport?: () => void;
  /** The way to the surface the empty review's own sentence names. */
  onReadDelta?: () => void;
  /**
   * How many revisions this lineage has, according to the cheap listing.
   *
   * `lineage` above is the reviews themselves, which is the heavy request and arrives
   * seconds later — so until it lands no row draws a trajectory and, when it does, up to
   * 248px appears on the right of every row at once and every claim rewraps under the
   * reader's eye. This is the depth known from the request that has already answered, and it
   * is used for nothing but reserving the space the strip will take.
   */
  lineageDepth?: number;
}) {
  const { pathname } = useLocation();
  const [query, setQuery] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const waiting = awaitsAnswers(review);
  const delta = useMemo(() => deltaIndexOf(review), [review]);

  const { attention, settledFindings, decided } = useMemo(() => {
    const attention: Finding[] = [];
    const settledFindings: Finding[] = [];
    for (const finding of findings) {
      const decision = decisions.get(finding.candidate.id);
      (needsAttention(finding, decision) ? attention : settledFindings).push(finding);
    }
    return {
      attention,
      settledFindings,
      decided: findings.filter((finding) => decisions.has(finding.candidate.id)).length,
    };
  }, [findings, decisions]);

  const matching = useMemo(
    () => (filter === "all" ? findings : filter === "attention" ? attention : settledFindings),
    [filter, findings, attention, settledFindings],
  );

  const visible = useMemo(() => {
    const shown = new Set(matching.map((finding) => finding.candidate.id));
    const wanted = query.trim().toLowerCase();
    return findings.filter((finding) => {
      const listed =
        shown.has(finding.candidate.id) ||
        settledHere.includes(finding.candidate.id) ||
        finding.candidate.id === openId;
      if (!listed) return false;
      // The text filter narrows what the chips left, rather than replacing it: the reader
      // asked two questions and both of their answers still hold.
      return !wanted || searchableText(finding).includes(wanted);
    });
  }, [findings, matching, settledHere, openId, query]);

  /**
   * The groups the list is read in.
   *
   * Two, where there is a review to have moved since and both halves have something in them:
   * a heading over every row is a heading that says nothing. Where there is no predecessor
   * there is no movement to group on — and that is the review most likely to be a wall — so
   * a long first review groups on the pattern the detector recorded, which is a fact the
   * machine already measured rather than one this surface invented.
   */
  const sections = useMemo(() => {
    const moved = visible.filter((finding) => movedSincePrevious(delta, finding.candidate.id));
    const carried = visible.filter((finding) => !movedSincePrevious(delta, finding.candidate.id));
    if (review.previous_review_id && moved.length && carried.length) {
      return [
        { label: `Moved since review ${review.sequence - 1}`, findings: moved },
        { label: "Carried forward", findings: carried },
      ];
    }

    const patterns = new Set(visible.map((finding) => finding.candidate.pattern));
    if (!review.previous_review_id && visible.length >= WALL && patterns.size > 1) {
      // In the order the list already has, so the group holding the most urgent finding is
      // the first group — the sort inside a group stays what needs a human first, and the
      // groups inherit that rather than re-ranking anything.
      return [...patterns].map((pattern) => ({
        label: humanise(pattern),
        findings: visible.filter((finding) => finding.candidate.pattern === pattern),
      }));
    }

    return [{ label: null as string | null, findings: visible }];
  }, [visible, delta, review.previous_review_id, review.sequence]);

  /**
   * The next thing that still wants a person, in the order the list shows them.
   *
   * Deciding hands you the next one rather than leaving you on a settled row. This is the
   * rhythm the two-pane version never had — and it is not the interface concluding you were
   * finished, because you asked for it by taking a decision.
   */
  function advance(from: string): Finding | null {
    const wants = (finding: Finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id));
    // Positioned in the whole list, not among the outstanding ones. By the time this runs the
    // row it starts from has just settled, so it is no longer in that shorter list — asking
    // it for "the one after this" got back "nothing, so start at the top", and deciding the
    // fourth of six items sent you back to the first.
    const at = visible.findIndex((finding) => finding.candidate.id === from);
    const next = visible.slice(at + 1).find(wants) ?? visible.find(wants);
    onOpen(next ? next.candidate.id : null);
    return next ?? null;
  }

  // The row that just settled under an open panel is the signal to move on. Watching the
  // decision map rather than the button is what makes this work for the keyboard shortcuts
  // too, which are bound at the document and never touch this component.
  //
  // The cursor's identity is half of the condition, and leaving it out is a bug that reads
  // as the interface fighting you: landing on an already-settled row — which the Settled and
  // All filters exist to let you do — is not the same event as a row settling under you, and
  // a version that only watched the flag bounced straight off every one you opened.
  const settledUnderCursor =
    openId && openId !== "clarification"
      ? !needsAttention(
          findings.find((finding) => finding.candidate.id === openId) ?? findings[0],
          decisions.get(openId),
        )
      : false;
  const cursor = useRef({ id: openId, settled: settledUnderCursor });
  /** The row the docket moved the cursor to on its own, which is the one that takes focus. */
  const advanced = useRef<string | null>(null);
  useEffect(() => {
    const stayed = cursor.current.id === openId;
    if (stayed && settledUnderCursor && openId && !cursor.current.settled) {
      onSettledHere((kept) => (kept.includes(openId) ? kept : [...kept, openId]));
      const decision = decisions.get(openId);
      const next = advance(openId);
      // Written before the re-render `advance` triggers, so the row that opens reads it on
      // the same pass it mounts its panel on.
      advanced.current = next ? next.candidate.id : null;
      // What happened, and what is now under you. From the keyboard, scrolled past the bar,
      // the fade on three buttons was the entire report on a decision — and once the cursor
      // moves on its own, "which row am I on now" is a question the screen answers only by
      // being looked at.
      setAnnouncement(
        [
          decision ? `${dispositionOf(decision.disposition).label}.` : "Settled.",
          next
            ? `Now on ${next.candidate.participants[0]?.qualified_name ?? next.candidate.summary}, ${verdictOf(next.verdict).label.toLowerCase()}.`
            : "Nothing else is waiting on a person.",
        ].join(" "),
      );
    }
    cursor.current = { id: openId, settled: settledUnderCursor };
    // `advance` closes over the current list, which is exactly the list this should walk.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settledUnderCursor, openId]);

  /**
   * Walking the list, selecting a row, and closing the one that is open.
   *
   * Bound at the document, like the decision keys, and behind the same three guards. It used
   * to be a React `onKeyDown` on this component's own div, which only fires while focus is
   * inside it — and recording a decision unmounts the button that was pressed, so focus fell
   * to `<body>` and `j` stopped working until the reader clicked back into the list. `A`
   * still worked, which is a half-dead keyboard with nothing on screen to explain it.
   */
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!isPlainShortcut(event)) return;
      // Every key below closes the open row or moves off it, and either one unmounts the
      // decision bar — where a half-written waiver reason lives as component state, with no
      // warning and nothing to undo it with. So the reveal owns the keyboard while it is
      // open, the same way a modal does one level up. This is one guard rather than a check
      // per key because it is one rule: `docs/experience.md`, never navigate away from
      // unsaved input. Escape was the reachable one — a single Tab out of the textarea, past
      // where the reveal's own handler applies — but `j` and `k` walk off the row just as
      // destructively, and only Escape was ever reported.
      if (hasOpenReveal()) return;

      if (event.key === "Escape") {
        if (!openId) return;
        event.preventDefault();
        onOpen(null);
        return;
      }

      if (event.key === "x" || event.key === "X") {
        if (!openId || openId === "clarification") return;
        event.preventDefault();
        onSelectedChange((current) =>
          current.includes(openId)
            ? current.filter((id) => id !== openId)
            : [...current, openId],
        );
        return;
      }

      const step =
        event.key === "ArrowDown" || event.key === "j"
          ? 1
          : event.key === "ArrowUp" || event.key === "k"
            ? -1
            : 0;
      if (!step) return;
      // The same condition the card is rendered under, and the same one `defaultOpen` uses.
      // Listed only while `waiting`, the walk lost the row the docket had just opened: with a
      // round answered and its rejudgement running, `indexOf("clarification")` was -1, so
      // ArrowUp took the nothing-is-open branch and jumped to the bottom of the list.
      const ids = [
        ...(waiting || rejudging ? ["clarification"] : []),
        ...visible.map((finding) => finding.candidate.id),
      ];
      if (!ids.length) return;
      const at = openId ? ids.indexOf(openId) : -1;
      const to = at === -1 ? (step > 0 ? 0 : ids.length - 1) : at + step;
      if (to < 0 || to >= ids.length) return;
      event.preventDefault();
      // The walked-to row takes focus the same way an advanced-to row does. `advanced` was
      // written only by the settle effect, so walking the docket with `j`/`k` opened rows
      // while DOM focus stayed wherever it had been — typically a filter chip — and the next
      // Tab left the list entirely. Moving focus onto the row button is also what makes the
      // walk audible: the screen reader reads the row it lands on. Deliberately not also fed
      // to the live region, which would then say the same thing twice and would be talking
      // over every keystroke of the walk.
      advanced.current = ids[to];
      onOpen(ids[to]);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [visible, waiting, openId, onOpen, onSelectedChange]);

  /**
   * What the search did, said into the region that is already mounted.
   *
   * Typing narrows the list to a count printed in a static span, which reaches nobody who is
   * not looking at it — the same complaint the settle announcement was added to answer, one
   * control over. The chips need nothing: they are `aria-pressed` buttons, so the press
   * itself is announced.
   *
   * Debounced, because this fires on a keystroke and an announcement per character is a
   * region that talks over the typing. Keyed on the query alone so a decision landing under
   * the reader cannot overwrite what the settle effect just said — the counts are read from
   * the render the query changed on, which is the render that already recomputed them.
   */
  const reportable = query.trim();
  const shown = visible.length;
  const of = matching.length;
  useEffect(() => {
    // Clearing the box restores the list the chips describe, which the chips already say.
    if (!reportable) return;
    const timer = window.setTimeout(() => {
      setAnnouncement(`${shown} of ${of} match “${reportable}”.`);
    }, 400);
    return () => window.clearTimeout(timer);
    // The counts belong to the query, and re-running on them would announce every decision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportable]);

  // The end of the work is a state, and it is reached the moment nothing is outstanding —
  // not the moment the list empties. `visible` deliberately retains the rows that settled
  // under you this session, so deciding the last outstanding candidate left it non-empty and
  // the one moment in the product worth marking was skipped in the very session that earned
  // it: you got a list of settled rows and silence.
  const workedThrough = !attention.length && !waiting && Boolean(findings.length);
  const selectable = new Set(visible.map((finding) => finding.candidate.id));
  const checked = selected.filter((id) => selectable.has(id));

  return (
    <div className="mx-auto w-full max-w-[76rem] px-4 py-4 sm:px-6 sm:py-5">
      <Progress
        total={findings.length}
        settled={settledFindings.length}
        filter={filter}
        onFilterChange={onFilterChange}
        counts={{
          attention: attention.length,
          settled: settledFindings.length,
          all: findings.length,
        }}
        query={query}
        onQueryChange={setQuery}
        matched={{ shown: visible.length, of: matching.length }}
      />

      {/* One region, mounted for as long as the docket is, empty most of the time. A region
          created at the same moment as its content is a region a screen reader may never
          read — which is what a `{success ? <LiveRegion/> : null}` is. */}
      <LiveRegion>{announcement}</LiveRegion>

      {/* Pinned under the surface strip, because selecting rows is something a reviewer does
          while working *down* a long docket — with `x` on the open row, or by checkbox — and
          a bar that renders once between the progress strip and the list is several screens
          above the rows it acts on by the time three are checked. 5.75rem is the 48px topbar
          plus the 44px strip, which is the same measurement `scroll-mt-24` on a row is taken
          against, and `z-10` keeps it under the strip's own `z-20`. */}
      {checked.length ? (
        <div className="sticky top-[5.75rem] z-10 mt-3">
          <BulkBar
            review={review}
            selected={checked}
            onClear={() => onSelectedChange(() => [])}
            onDecided={(decided, message) => {
              // The same rule a single decision follows: a row that settles under you stays
              // listed until you ask the list a different question. Twelve rows vanishing at
              // once takes with them any way to check what was just done to them.
              onSettledHere((kept) => [
                ...kept,
                ...decided.filter((id) => !kept.includes(id)),
              ]);
              setAnnouncement(message);
            }}
          />
        </div>
      ) : null}

      <div className="mt-4 grid gap-3">
        {waiting || rejudging ? (
          <ClarificationCard
            review={review}
            answers={answers}
            rejudging={rejudging}
            notice={rejudgementNotice}
            open={openId === "clarification"}
            onToggle={() => onOpen(openId === "clarification" ? null : "clarification")}
          />
        ) : null}

        {/* Above the rows it is about, because the rows below it are the ones that settled
            under you and the sentence is what they add up to. */}
        {workedThrough ? (
          <WorkedThrough
            total={findings.length}
            decided={decided}
            onReadReport={onReadReport}
          />
        ) : null}

        {!visible.length ? (
          workedThrough ? null : (
            <div className="rounded-lg border border-rule bg-surface px-5 py-10 text-center shadow-rim">
              <p className="text-[13px] text-ink-2">
                {!findings.length
                  ? "This review composed no findings. The delta still describes what was analysed."
                  : query.trim()
                    ? `Nothing in this review matches “${query.trim()}”.`
                    : "Choose another filter to see the rest of this review."}
              </p>
              {/* The one branch whose named destination is genuinely another surface, and
                  therefore the one that cannot get there by itself. The other two name a
                  control that is a few pixels above this panel and on screen — the search box
                  the reader just typed into, and the chips — so a duplicate of either buys
                  nothing. `WorkedThrough` above already proves the pattern with "Read the
                  report". */}
              {!findings.length && onReadDelta ? (
                <div className="mt-4">
                  <Button variant="secondary" size="sm" onClick={onReadDelta}>
                    Read the delta
                  </Button>
                </div>
              ) : null}
            </div>
          )
        ) : (
          sections
            .filter((section) => section.findings.length)
            .map((section) => {
              // What every row in this group agrees about, said once above them instead of
              // once each. Thirty rows reading `domain.orders.` before the name they differ
              // by is thirty copies of one fact, and the fact is the least useful half.
              const shared = sharedNamespace(section.findings);
              return (
                <section key={section.label ?? "all"}>
                  {/* `h2`, over the `h3` each row carries. The outline used to run h1, then
                      this at h3, then every row inside it at h2 — so heading navigation, the
                      fastest way down a long list with a screen reader, reported every
                      candidate as a peer of the group containing it and jumping by heading
                      walked out of a group rather than through it. An ungrouped docket now
                      skips a level instead, which is a best-practice miss where the inversion
                      was an active lie about what contains what.

                      No `px-1`. Four pixels of inset put the heading off the left edge of the
                      card below it, the list's own edge and the search box above it — a
                      near-alignment, which reads as a mistake where a clear step would not. */}
                  {section.label || shared ? (
                    <Label
                      as="h2"
                      className="mb-1.5 flex flex-wrap items-baseline gap-x-2 text-ink-2"
                    >
                      {/* No `?? "All"`. Where a section has no label the heading exists only
                          to hoist the namespace the rows share, and the fallback invented a
                          word that is also the name of a filter chip a few pixels above it —
                          so a reader working the Attention filter was headed "ALL 3 IN ports",
                          which claims the list is unfiltered at the exact moment it is not.
                          Nothing on the docket prints "All" except the chip that means it. */}
                      {section.label ? <span>{section.label}</span> : null}
                      <span className="font-mono tabular-nums text-ink-3">
                        {section.findings.length}
                      </span>
                      {shared ? (
                        <span className="font-normal normal-case tracking-normal text-ink-3">
                          in{" "}
                          <span className="font-mono text-[11px] text-ink-2">{shared}</span>
                        </span>
                      ) : null}
                    </Label>
                  ) : null}
                  {/* Two groups mean two lists, and two lists called the same thing are one
                      list as far as anything reading the page is concerned. So the group's
                      own heading names it — "Candidates carried forward" — and the name is
                      only the bare word when the docket is a single ungrouped list. */}
                  <ul
                    aria-label={
                      section.label ? `Candidates ${section.label.toLowerCase()}` : "Candidates"
                    }
                    // `divide-y` here rather than `border-b` on each row, because this is the
                    // element that knows where a row sits among its siblings. Written on the
                    // row it was `border-b … last:border-b-0` on an `<article>` that is the
                    // only child of its `<li>`, so `:last-child` matched every row and the
                    // rule never painted once: six candidates rendered as one unbroken sheet,
                    // on the surface whose design system calls hairlines its primary
                    // structural device.
                    //
                    // It separates two things now, not one. The `<li>` spans the list's whole
                    // content box, so this hairline reaches across the three pixels of the
                    // verdict edge as well as the row's words — which is what lets that edge
                    // run its row's full height and still be cut once per row. In the other
                    // axis the two abut rather than overlap: the edge is positioned against
                    // the `<article>`, whose box ends where this border begins, so the border
                    // is the whole of the break. Delete this and the edges of a same-verdict
                    // run fuse; `test_the_verdict_edge_is_cut_only_by_the_row_rule` in
                    // `tests/browser/` is where that is caught, colour included — dropping
                    // `divide-rule` and keeping `divide-y` leaves `currentColor`, which is a
                    // near-black line the width of the panel.
                    className="divide-y divide-rule overflow-hidden rounded-lg border border-rule bg-surface shadow-rim"
                  >
                    {section.findings.map((finding) => (
                      <li key={finding.candidate.id}>
                        <DocketRow
                          review={review}
                          finding={finding}
                          decision={decisions.get(finding.candidate.id)}
                          delta={deltaStateOf(delta, finding.candidate.id)}
                          lineage={lineage}
                          lineageDepth={lineageDepth}
                          hoistedNamespace={shared ?? undefined}
                          open={openId === finding.candidate.id}
                          takeFocus={advanced.current === finding.candidate.id}
                          selected={selected.includes(finding.candidate.id)}
                          selecting={Boolean(checked.length)}
                          link={`${window.location.origin}${pathname}?candidate=${encodeURIComponent(finding.candidate.id)}`}
                          onSelect={(next) =>
                            onSelectedChange((current) =>
                              next
                                ? [...current, finding.candidate.id]
                                : current.filter((id) => id !== finding.candidate.id),
                            )
                          }
                          onToggle={() =>
                            onOpen(openId === finding.candidate.id ? null : finding.candidate.id)
                          }
                          onAnswer={() => onOpen("clarification")}
                          onOpenContext={onOpenContext}
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })
        )}
      </div>

      {/* What the filters cannot count: "settled" includes everything ArchCompass cleared by
          itself, and this is the part the team did. The keys that used to be printed here
          moved up beside the control they act on.

          Not while the review is worked through: `WorkedThrough` states the same partition of
          the same total a few hundred pixels above, and one number printed twice on one
          screen in two wordings is a reader checking whether they disagree. The line survives
          for every review that is *not* finished, which is the case it was written for. Left
          on the column's own edge rather than inset by `px-1`, for the reason the group
          heading above it is. */}
      {findings.length && !workedThrough ? (
        <p className="mt-3 text-[11px] text-ink-3">
          {decided
            ? `${decided} of ${plural(findings.length, "candidate")} decided by the team.`
            : "Nothing decided by the team yet."}
        </p>
      ) : null}
    </div>
  );
}
