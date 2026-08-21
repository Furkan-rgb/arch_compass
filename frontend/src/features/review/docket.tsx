import { useEffect, useMemo, useRef, useState } from "react";

import type { Decision, Finding, Review } from "../../api";
import { cn } from "../../lib/cn";
import { dispositionOf, humanise, plural, splitQualified, verdictOf } from "../../lib/format";
import { Mark } from "../../ui/mark";
import { TONE_EDGE, TONE_TEXT } from "../../ui/meta";
import { Button, ButtonLink, ToggleButton } from "../../ui/button";
import { ChevronDown, DriftedIcon } from "../../ui/icons";
import { ClarificationRound } from "./clarification";
import { DecisionBar } from "./decision-bar";
import { FindingBody } from "./finding-detail";
import { CandidateTrajectory } from "./trajectory";
import {
  type QueueFilter,
  decisionIsStale,
  deltaStateOf,
  movedSincePrevious,
  needsAttention,
  orderedFindings,
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

/** How far through the work this review is, and what is left. */
function Progress({
  total,
  settled,
  filter,
  onFilterChange,
  counts,
}: {
  total: number;
  settled: number;
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  counts: { attention: number; settled: number; all: number };
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
      <div className="flex min-w-0 items-center gap-3">
        {/* One segment per candidate, filled as it settles. Ink and rule, never a verdict
            hue: how far through you are is not a grade anything was given. */}
        <span aria-hidden="true" className="flex shrink-0 items-center gap-[3px]">
          {Array.from({ length: Math.min(total, 24) }, (_, index) => (
            <span
              key={index}
              className={cn(
                "block h-3.5 w-[5px] rounded-xs",
                index < settled ? "bg-ink" : "bg-rule-strong",
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
          <ToggleButton key={id} pressed={filter === id} onClick={() => onFilterChange(id)}>
            {label}
            <span className="tabular-nums opacity-70">{count}</span>
          </ToggleButton>
        ))}
      </div>
    </div>
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
  lineage,
  open,
  hoistedNamespace,
  onToggle,
  onAnswer,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  decision?: Decision;
  lineage: Review[];
  open: boolean;
  hoistedNamespace?: string;
  onToggle: () => void;
  onAnswer?: () => void;
  onOpenContext?: () => void;
}) {
  const descriptor = verdictOf(finding.verdict);
  const identity = finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary;
  const { namespace, leaf } = splitQualified(identity);
  const delta = deltaStateOf(review, finding.candidate.id);
  const settled = !needsAttention(finding, decision);
  const panelId = `finding-panel-${finding.candidate.id}`;
  const ref = useRef<HTMLButtonElement>(null);

  // Opening a row that the keyboard walked to has to bring it into view, or `j` past the
  // fold silently expands something below the screen.
  useEffect(() => {
    if (open) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [open]);

  return (
    <article
      aria-labelledby={`finding-${finding.candidate.id}`}
      className={cn(
        // The verdict as an edge. A docket is worked down a column, and the question asked
        // of the whole column at once — where does the red start — is not one a mark inside
        // a row can answer: at any size that fits beside a name, a glyph has to be looked
        // *at*. An edge is read without being looked at, costs no horizontal space, and is
        // a rule rather than a card, which is the structure this system already uses.
        "border-b border-l-[3px] border-rule last:border-b-0",
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
      <button
        ref={ref}
        type="button"
        data-candidate={finding.candidate.id}
        aria-expanded={open}
        aria-controls={panelId}
        title={identity}
        onClick={onToggle}
        className={cn(
          "flex w-full min-h-14 items-start gap-3 px-4 py-3 text-left transition sm:px-5",
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
            {!settled ? (
              <span
                className={cn(
                  "text-[10px] font-bold uppercase tracking-[0.11em]",
                  TONE_TEXT[descriptor.tone],
                )}
              >
                {descriptor.label}
              </span>
            ) : null}
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

/** The question the review is waiting on, listed as what it is: the first item. */
function ClarificationCard({
  review,
  open,
  onToggle,
}: {
  review: Review;
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
          <span className="mt-0.5 block text-[12.5px] leading-[1.5] text-ink-2">
            Nothing below can be finished until these are answered. Answering produces the next
            case revision and re-judges what it touches.
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn("mt-0.5 size-4 shrink-0 text-ink-3 transition", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="animate-expand border-t border-rule py-3">
          <ClarificationRound review={review} bare />
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
  decisions,
  lineage,
  filter,
  onFilterChange,
  openId,
  onOpen,
  onOpenContext,
  onReadReport,
}: {
  review: Review;
  decisions: Map<string, Decision>;
  lineage: Review[];
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  /** The candidate id whose row is open, or `"clarification"`, or null for none. */
  openId: string | null;
  onOpen: (id: string | null) => void;
  onOpenContext?: () => void;
  onReadReport?: () => void;
}) {
  const findings = orderedFindings(review);
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;

  const attention = findings.filter((finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  );
  const settledFindings = findings.filter(
    (finding) => !needsAttention(finding, decisions.get(finding.candidate.id)),
  );
  const decided = findings.filter((finding) => decisions.has(finding.candidate.id)).length;

  const matching =
    filter === "all" ? findings : filter === "attention" ? attention : settledFindings;

  /**
   * Candidates that settled while you were looking at them, and therefore stay listed.
   *
   * Deciding a candidate settles it, so under the Attention filter the row you just acted on
   * no longer matches — and a row that vanishes at the instant you act on it takes with it
   * any way to check what you did, or to change your mind. The counts move immediately,
   * because they are the truth; the row stays, showing the decision on it, until you change
   * the filter and ask the list a different question.
   */
  const [settledHere, setSettledHere] = useState<string[]>([]);
  useEffect(() => setSettledHere([]), [filter]);

  const visible = useMemo(() => {
    const shown = new Set(matching.map((finding) => finding.candidate.id));
    return findings.filter(
      (finding) =>
        shown.has(finding.candidate.id) ||
        settledHere.includes(finding.candidate.id) ||
        finding.candidate.id === openId,
    );
  }, [findings, matching, settledHere, openId]);

  // Two sections, and only where there is a review to have moved since and both have
  // something in them. A heading over every row is a heading that says nothing.
  const moved = visible.filter((finding) => movedSincePrevious(review, finding.candidate.id));
  const carried = visible.filter((finding) => !movedSincePrevious(review, finding.candidate.id));
  const split = Boolean(review.previous_review_id) && moved.length > 0 && carried.length > 0;
  const sections = split
    ? [
        { label: `Moved since review ${review.sequence - 1}`, findings: moved },
        { label: "Carried forward", findings: carried },
      ]
    : [{ label: null as string | null, findings: visible }];

  /**
   * The next thing that still wants a person, in the order the list shows them.
   *
   * Deciding hands you the next one rather than leaving you on a settled row. This is the
   * rhythm the two-pane version never had — and it is not the interface concluding you were
   * finished, because you asked for it by taking a decision.
   */
  function advance(from: string) {
    const wants = (finding: Finding) =>
      needsAttention(finding, decisions.get(finding.candidate.id));
    // Positioned in the whole list, not among the outstanding ones. By the time this runs the
    // row it starts from has just settled, so it is no longer in that shorter list — asking
    // it for "the one after this" got back "nothing, so start at the top", and deciding the
    // fourth of six items sent you back to the first.
    const at = visible.findIndex((finding) => finding.candidate.id === from);
    const next = visible.slice(at + 1).find(wants) ?? visible.find(wants);
    onOpen(next ? next.candidate.id : null);
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
  useEffect(() => {
    const stayed = cursor.current.id === openId;
    if (stayed && settledUnderCursor && !cursor.current.settled && openId) {
      setSettledHere((kept) => (kept.includes(openId) ? kept : [...kept, openId]));
      advance(openId);
    }
    cursor.current = { id: openId, settled: settledUnderCursor };
    // `advance` closes over the current list, which is exactly the list this should walk.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settledUnderCursor, openId]);

  /** Walk the rows. Ignored while something typeable has focus. */
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    if (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
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

  return (
    <div onKeyDown={onKeyDown} className="mx-auto w-full max-w-[76rem] px-4 py-4 sm:px-6 sm:py-5">
      <Progress
        total={findings.length}
        settled={settledFindings.length}
        filter={filter}
        onFilterChange={onFilterChange}
        counts={{ attention: attention.length, settled: settledFindings.length, all: findings.length }}
      />

      <div className="mt-4 grid gap-3">
        {waiting ? (
          <ClarificationCard
            review={review}
            open={openId === "clarification"}
            onToggle={() => onOpen(openId === "clarification" ? null : "clarification")}
          />
        ) : null}

        {!visible.length ? (
          filter === "attention" && !waiting && findings.length ? (
            <WorkedThrough review={review} decided={decided} onReadReport={onReadReport} />
          ) : (
            <div className="rounded-lg border border-rule bg-surface px-5 py-10 text-center shadow-rim">
              <p className="text-[13px] text-ink-3">
                {findings.length
                  ? "Choose another filter to see the rest of this review."
                  : "This review composed no findings. The delta still describes what was analysed."}
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
                    <h3 className="mb-1.5 flex flex-wrap items-baseline gap-x-2 px-1 text-[10px] font-bold uppercase tracking-[0.13em] text-ink-2">
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
                    </h3>
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
                          lineage={lineage}
                          hoistedNamespace={shared ?? undefined}
                          open={openId === finding.candidate.id}
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
          itself, and this is the part the team did. */}
      {findings.length ? (
        <p className="mt-3 px-1 text-[11px] text-ink-3">
          {decided
            ? `${decided} of ${plural(findings.length, "candidate")} decided by the team.`
            : "Nothing decided by the team yet."}{" "}
          <span className="font-mono">j</span> and <span className="font-mono">k</span> walk the
          list; <span className="font-mono">A</span>, <span className="font-mono">P</span> and{" "}
          <span className="font-mono">W</span> decide the open one.
        </p>
      ) : null}
    </div>
  );
}
