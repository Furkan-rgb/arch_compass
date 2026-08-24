import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type Decision, type Finding, type Review } from "../../api";
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
import { LiveRegion } from "../../ui/states";
import { ClarificationRound, type RoundAnswers } from "./clarification";
import { DecisionBar } from "./decision-bar";
import { FindingBody } from "./finding-detail";
import { CandidateTrajectory } from "./trajectory";
import {
  type QueueFilter,
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
  // By ratio, not by index. A segment index compared against a raw count is only the same
  // question while the two scales are the same, which they stop being at 25 candidates.
  const filled = total ? Math.round((settled / total) * segments) : 0;

  return (
    <div className="grid gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
        <div className="flex min-w-0 items-center gap-3">
          {/* One segment per candidate, filled as it settles. Ink and rule, never a verdict
              hue: how far through you are is not a grade anything was given. Past `SEGMENTS`
              it is a proportion, and says so on the hover — the count beside it is exact
              either way, which is why the strip is allowed to round. */}
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
                  index < filled ? "bg-ink" : "bg-rule-strong",
                )}
              />
            ))}
          </span>
          <span className="text-[12.5px] text-ink-2">
            <span className="font-mono font-semibold tabular-nums text-ink">{settled}</span> of{" "}
            <span className="font-mono tabular-nums">{total}</span> settled
          </span>
        </div>

        <div role="group" aria-label="Filter the docket" className="flex gap-1">
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
              <span className="tabular-nums opacity-70">{count}</span>
            </ToggleButton>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {/* Three filters was the whole of the navigation, and none of them is "the one about
            SqlAlchemy". A count beside the box rather than under the list, because it is the
            control's own report on what it did — and a count with a control on it is the
            form this document asks numbers to take. */}
        <div className="flex min-w-0 items-center gap-2">
          <Input
            type="search"
            aria-label="Find a candidate in this review"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Find a name, a claim or a pattern"
            className="h-8 min-w-0 max-w-[22rem] py-1 text-[13px]"
          />
          {query.trim() ? (
            <span className="shrink-0 text-[12px] text-ink-3">
              <span className="font-mono tabular-nums text-ink-2">{matched.shown}</span> of{" "}
              <span className="font-mono tabular-nums">{matched.of}</span>
            </span>
          ) : null}
        </div>

        {/* The keys, beside the control they act on. This sentence used to sit below every
            row — forty rows past the list the shortcuts exist to move through — and named
            four of the keys the handler supports. The full list is behind `?`, which the
            shell binds everywhere.

            Only where there is something to press them on. On a phone this was eleven key
            caps and four verbs — the single densest thing above the list — describing a
            keyboard that is not there, and it sat between the reader and the findings. */}
        {hasKeyboard ? (
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-ink-3">
            <Key>j</Key>
            <Key>
              <ArrowDown aria-hidden="true" className="size-3" />
            </Key>
            <Key>k</Key>
            <Key>
              <ArrowUp aria-hidden="true" className="size-3" />
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
            <span aria-hidden="true" className="text-ink-3/50">
              ·
            </span>
            <Key>?</Key>
            <span>all keys</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A literal keystroke, so it is set in mono.
 *
 * A third cap, and deliberately not the shortcut sheet's or the decision bar's: theirs sit on
 * a panel and on an ink fill respectively, and this one sits in a footnote beside the control
 * it describes, where a key at the sheet's size would outweigh the sentence around it.
 */
function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center rounded-xs border border-rule px-1 font-mono text-[10.5px] font-semibold leading-4 text-ink-2">
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

/** What a row says about itself once a person, or nobody, has spoken. */
function RowState({ finding, decision }: { finding: Finding; decision?: Decision }) {
  const stale = decisionIsStale(finding, decision);
  if (decision && !stale) {
    const disposition = dispositionOf(decision.disposition);
    return (
      <span className="flex shrink-0 items-center gap-1.5 text-[11.5px] font-semibold text-ink-2">
        <Mark shape={disposition.glyph} className="size-[13px]" />
        {disposition.label} by the team
      </span>
    );
  }
  if (stale && decision) {
    // The whole sentence, not the word "stale": what a reader needs is the two verdicts, in
    // the order they happened, because that is the entire reason the row is back.
    return (
      <span className="flex shrink-0 items-center gap-1 text-[11.5px] font-semibold text-ink">
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
      className={cn(
        // The verdict as an edge. A docket is worked down a column, and the question asked
        // of the whole column at once — where does the red start — is not one a mark inside
        // a row can answer: at any size that fits beside a name, a glyph has to be looked
        // *at*. An edge is read without being looked at, costs no horizontal space, and is
        // a rule rather than a card, which is the structure this system already uses.
        "border-b border-l-[3px] border-rule last:border-b-0",
        // 48px of opaque topbar and 44px of pinned surface strip, and the docket scrolls with
        // the page — so a row walked *up* to with `k` was aligned flush with the viewport and
        // landed underneath both, hiding the identifier and the verdict of the row just
        // arrived at. 96px clears the pair with four to spare. It was 56px when only the
        // topbar was pinned; the strip was pinned afterwards and this is the measurement that
        // had to move with it.
        "scroll-mt-24",
        settled ? "border-l-transparent" : TONE_EDGE[descriptor.tone],
        open && "bg-surface",
        !open && settled && "bg-transparent",
      )}
    >
      {/* The row's own name, for anything that reads the document rather than looks at it —
          heading navigation being the fastest way down a long list with a screen reader.
          The whole qualified name and the claim, because two candidates in one package share
          a name and a column of identical headings is a column of nothing. What is *drawn*
          drops the namespace where the group above it already said it, which is a different
          question. */}
      <h2 id={`finding-${finding.candidate.id}`} className="sr-only">
        {identity} — {finding.candidate.summary}
      </h2>

      <div className="flex items-stretch">
        {/* Outside the row's own button, because a checkbox inside a button is a control
            inside a control. It is invisible until it is wanted — hovered, focused, or once
            anything at all is selected — so a docket nobody is bulk-deciding looks exactly
            as it did. On a coarse pointer it is simply there: hover is the affordance that
            reveals it, and a finger has none. */}
        <label
          className={cn(
            "flex shrink-0 cursor-pointer items-start pl-3 pt-4 transition sm:pl-4",
            selected || selecting
              ? "opacity-100"
              : "opacity-0 pointer-coarse:opacity-100 focus-within:opacity-100 hover:opacity-100",
          )}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelect(event.target.checked)}
            className="size-4 accent-[var(--ink)]"
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
          className={cn(
            "flex min-w-0 flex-1 min-h-14 items-start gap-3 px-3 py-3 text-left transition sm:px-4",
            open ? "bg-surface" : "hover:bg-surface-2",
          )}
        >
          <Mark
            shape={descriptor.glyph}
            className={cn(
              "mt-px size-[15px] shrink-0",
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
                  from a cleared one. The charter says a verdict is a glyph, a word and a hue, and
                  settling is not a reason to keep one of the three. */}
              <Label as="span" className={settled ? undefined : TONE_TEXT[descriptor.tone]}>
                {descriptor.label}
              </Label>
            </span>

            {/* The claim. This is the line that makes the list readable, and the reason most
                rows never need opening. */}
            <span
              className={cn(
                "mt-1 text-[13px] leading-[1.5] text-ink-2",
                open ? "block" : "line-clamp-2",
              )}
            >
              {finding.candidate.summary}
            </span>

            <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-3">
              <span>{humanise(finding.candidate.pattern)}</span>
              {delta && delta !== "unchanged" ? <span>· {humanise(delta)} this review</span> : null}
              <RowState finding={finding} decision={decision} />
            </span>
          </span>

          <span className="flex shrink-0 items-center gap-2 pt-0.5">
            {lineage.length > 1 ? (
              <CandidateTrajectory
                lineage={lineage}
                candidateId={finding.candidate.id}
                currentReviewId={review.id}
                className="hidden md:flex"
              />
            ) : null}
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
          <div className="flex shrink-0 items-start pr-2 pt-3">
            <CopyButton value={link} label="Copy link to this finding" />
          </div>
        ) : null}
      </div>

      {open ? (
        <div id={panelId} className="animate-expand border-t border-rule">
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

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-rule-strong bg-surface px-4 py-2.5 shadow-rim">
      <span className="text-[13px] font-semibold text-ink">
        {plural(selected.length, "candidate")} selected
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={decide.isPending}
          onClick={() => decide.mutate("accept")}
        >
          Accept all
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={decide.isPending}
          onClick={() => decide.mutate("park")}
        >
          Park all
        </Button>
        <Button variant="ghost" size="sm" disabled={decide.isPending} onClick={onClear}>
          Clear
        </Button>
      </div>
      {/* Waiving is the one disposition that cannot be taken in a batch, and a reader who has
          just been offered two of three is owed the reason. */}
      <span className="text-[11.5px] leading-5 text-ink-3">
        Waiving stays one at a time: a reason that fits twelve findings is not a reason.
      </span>
    </div>
  );
}

/** The question the review is waiting on, listed as what it is: the first item. */
function ClarificationCard({
  review,
  answers,
  open,
  onToggle,
}: {
  review: Review;
  answers: RoundAnswers;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-rule bg-surface shadow-rim">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full min-h-14 items-start gap-3 bg-held-soft px-4 py-3 text-left transition sm:px-5"
      >
        <Mark shape="pause" className="mt-px size-[15px] shrink-0 text-held" />
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold text-ink">
            {plural(review.questions.length, "question")} want
            {review.questions.length === 1 ? "s" : ""} an answer
          </span>
          {/* "re-judges what it touches" invited the reading that answering is cheap and
              local. It is neither: `select_rejudgements_node` returns every candidate,
              because an answer is about intent and intent bears on all of them. The API
              layer already said so — `api.ts`, "minutes of model work" — and the surface a
              person actually presses the button on did not. */}
          <span className="mt-0.5 block text-[12.5px] leading-[1.5] text-ink-2">
            Nothing below can be finished until these are answered. Answering completes this
            review's case revision and judges every candidate again, which is minutes of model
            work.
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn("mt-0.5 size-4 shrink-0 text-ink-3 transition", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="animate-expand border-t border-rule py-3">
          <ClarificationRound review={review} answers={answers} bare />
        </div>
      ) : null}
    </section>
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
  review,
  decided,
  onReadReport,
}: {
  review: Review;
  decided: number;
  onReadReport?: () => void;
}) {
  const cleared = review.findings.filter((finding) => finding.verdict === "cleared").length;
  return (
    <div className="flex flex-col items-center rounded-lg border border-rule bg-surface px-5 py-10 text-center shadow-rim">
      <span className="flex size-9 items-center justify-center rounded-full border border-rule-strong text-ink">
        <Mark shape="check" className="size-[17px]" />
      </span>
      <h3 className="mt-3 text-[15px] font-semibold tracking-tight text-ink">Worked through</h3>
      <p className="mt-1.5 max-w-[52ch] text-[13px] leading-6 text-ink-2">
        Nothing in this review is waiting on a person. {plural(decided, "candidate")}{" "}
        {decided === 1 ? "was" : "were"} decided by the team and {plural(cleared, "other")} came
        back cleared.
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
}) {
  const { pathname } = useLocation();
  const [query, setQuery] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;
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
      const ids = [
        ...(waiting ? ["clarification"] : []),
        ...visible.map((finding) => finding.candidate.id),
      ];
      if (!ids.length) return;
      const at = openId ? ids.indexOf(openId) : -1;
      const to = at === -1 ? (step > 0 ? 0 : ids.length - 1) : at + step;
      if (to < 0 || to >= ids.length) return;
      event.preventDefault();
      onOpen(ids[to]);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [visible, waiting, openId, onOpen, onSelectedChange]);

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

      {checked.length ? (
        <div className="mt-3">
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
        {waiting ? (
          <ClarificationCard
            review={review}
            answers={answers}
            open={openId === "clarification"}
            onToggle={() => onOpen(openId === "clarification" ? null : "clarification")}
          />
        ) : null}

        {/* Above the rows it is about, because the rows below it are the ones that settled
            under you and the sentence is what they add up to. */}
        {workedThrough ? (
          <WorkedThrough review={review} decided={decided} onReadReport={onReadReport} />
        ) : null}

        {!visible.length ? (
          workedThrough ? null : (
            <div className="rounded-lg border border-rule bg-surface px-5 py-10 text-center shadow-rim">
              <p className="text-[13px] text-ink-3">
                {!findings.length
                  ? "This review composed no findings. The delta still describes what was analysed."
                  : query.trim()
                    ? `Nothing in this review matches “${query.trim()}”.`
                    : "Choose another filter to see the rest of this review."}
              </p>
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
                  {section.label || shared ? (
                    <Label
                      as="h3"
                      className="mb-1.5 flex flex-wrap items-baseline gap-x-2 px-1 text-ink-2"
                    >
                      <span>{section.label ?? "All"}</span>
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
                    className="overflow-hidden rounded-lg border border-rule bg-surface shadow-rim"
                  >
                    {section.findings.map((finding) => (
                      <li key={finding.candidate.id}>
                        <DocketRow
                          review={review}
                          finding={finding}
                          decision={decisions.get(finding.candidate.id)}
                          delta={deltaStateOf(delta, finding.candidate.id)}
                          lineage={lineage}
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
          moved up beside the control they act on. */}
      {findings.length ? (
        <p className="mt-3 px-1 text-[11px] text-ink-3">
          {decided
            ? `${decided} of ${plural(findings.length, "candidate")} decided by the team.`
            : "Nothing decided by the team yet."}
        </p>
      ) : null}
    </div>
  );
}
