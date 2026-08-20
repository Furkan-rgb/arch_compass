import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useMemo } from "react";

import { api, type Decision, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { useScrollEdges } from "../../lib/motion";
import {
  dispositionOf,
  humanise,
  plural,
  splitQualified,
  verdictOf,
  verdictRank,
} from "../../lib/format";
import { Badge } from "../../ui/badge";
import { Spine } from "../../ui/spine";
import { ToggleButton } from "../../ui/button";
import { EmptyState } from "../../ui/states";

export type QueueSelection = { kind: "clarification" } | { kind: "finding"; candidateId: string };

export type QueueFilter = "attention" | "settled" | "all";

/**
 * What the team has decided about each candidate on this branch, by candidate.
 *
 * Read through the same query key the decision bar writes through, so recording a decision
 * updates the queue in the same tick rather than on the next reload. A standing decision
 * belongs to the branch, not to the review — it outlives this snapshot.
 */
export function useStandingDecisions(review: Review | undefined): Map<string, Decision> {
  const branchId = review?.repository.branch_id;
  const decisions = useQuery({
    queryKey: ["decisions", branchId],
    queryFn: () => api.decisions(branchId!),
    enabled: Boolean(branchId),
  });
  return useMemo(
    () => new Map((decisions.data?.decisions ?? []).map((item) => [item.candidate_id, item])),
    [decisions.data],
  );
}

/** Where a candidate stands against the previous review, said in one word. */
export function deltaStateOf(review: Review, candidateId: string): string | null {
  if (review.delta.new.includes(candidateId)) return "new";
  if (review.delta.changed.some((item) => item.candidate_id === candidateId)) return "changed";
  if (review.delta.unchanged.includes(candidateId)) return "unchanged";
  return null;
}

/** Whether this candidate is one of the ones that moved since the review before. */
export function movedSincePrevious(review: Review, candidateId: string): boolean {
  const state = deltaStateOf(review, candidateId);
  return state === "new" || state === "changed";
}

/**
 * Whether the team decided this against a judgement that has since changed.
 *
 * `StandingDecision` records the verdict it was taken against — that is what
 * `finding_verdict` is for, and it crosses the boundary on every decision. Until now
 * nothing in the interface read it, so a team that accepted a material finding and then saw
 * it re-judged `held` after answering a clarification was never told: the row stayed
 * settled and silent.
 *
 * The decision is not withdrawn or amended by this. It is a record and records do not
 * change. What this says is that the record was made about something else.
 */
export function decisionIsStale(finding: Finding, decision?: Decision | null): boolean {
  return Boolean(decision && decision.finding_verdict !== finding.verdict);
}

/**
 * Whether this candidate still wants something from a person.
 *
 * Three ways to stop wanting one: ArchCompass cleared it, or the team decided what to do
 * about it, or both. The second is why this takes the decision — a waived material finding
 * is settled, and a queue that keeps asking about it is a queue people stop trusting. The
 * exception is a decision taken against a different verdict, which is not a settled
 * question but an open one nobody has been shown yet.
 */
export function needsAttention(finding: Finding, decision?: Decision | null): boolean {
  if (decisionIsStale(finding, decision)) return true;
  return finding.verdict !== "cleared" && !decision;
}

/**
 * The order a reviewer meets candidates in.
 *
 * What moved comes first. The charter says the second visit is the important one and that
 * what a returning reviewer wants is the short list of what is different — and this sort
 * used to be verdict rank and then the summary *alphabetically*, which put two new findings
 * wherever their sentences happened to fall among thirty unchanged ones.
 *
 * Movement leads and the verdict orders within it, which is only an honest ranking because
 * the list is grouped under headings that say so. A flat list that put a moved-and-cleared
 * candidate above an unmoved material one would be claiming a priority nothing supports.
 */
export function orderedFindings(review: Review): Finding[] {
  return [...review.findings].sort((left, right) => {
    const moved =
      Number(movedSincePrevious(review, right.candidate.id)) -
      Number(movedSincePrevious(review, left.candidate.id));
    if (moved !== 0) return moved;
    const rank = verdictRank(left.verdict) - verdictRank(right.verdict);
    if (rank !== 0) return rank;
    return left.candidate.summary.localeCompare(right.candidate.summary);
  });
}

/** Whether a filter would show this finding at all. */
export function inFilter(
  finding: Finding,
  filter: QueueFilter,
  decision?: Decision | null,
): boolean {
  if (filter === "all") return true;
  return needsAttention(finding, decision) === (filter === "attention");
}

/** The row a reader is on, moved by a key. Returns null when there is nowhere to go. */
function neighbour(
  ids: string[],
  current: string | undefined,
  step: number,
): string | null {
  if (!ids.length) return null;
  const at = current ? ids.indexOf(current) : -1;
  if (at === -1) return ids[step > 0 ? 0 : ids.length - 1];
  const next = at + step;
  if (next < 0 || next >= ids.length) return null;
  return ids[next];
}

/**
 * The list a reviewer works down.
 *
 * Ordered by what moved and then by what needs a human, and grouped so the second visit
 * reads as the short list of what is different followed by everything carried forward.
 * Clarification sits above both when the review is waiting, because nothing below it can be
 * finished until it is answered.
 *
 * This is the one thing on the page that is touched a hundred times in a sitting, so it
 * moves from the keyboard: the arrow keys and `j`/`k` walk the rows and open what they land
 * on. That is not a shortcut for power users; it is the difference between triage and
 * clicking.
 */
export function AttentionQueue({
  review,
  selection,
  onSelect,
  filter,
  onFilterChange,
  onReadReport,
  className,
}: {
  review: Review;
  selection: QueueSelection | null;
  onSelect: (selection: QueueSelection) => void;
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  /** Offered when the review is worked through, because reading it is what happens next. */
  onReadReport?: () => void;
  className?: string;
}) {
  const list = useScrollEdges<HTMLDivElement>();
  const decisions = useStandingDecisions(review);
  const findings = orderedFindings(review);
  const attention = findings.filter((finding) =>
    needsAttention(finding, decisions.get(finding.candidate.id)),
  );
  const settled = findings.filter(
    (finding) => !needsAttention(finding, decisions.get(finding.candidate.id)),
  );
  const matching = findings.filter((finding) =>
    inFilter(finding, filter, decisions.get(finding.candidate.id)),
  );
  // Whatever is open stays listed. Deciding a candidate settles it, and a row vanishing from
  // under the cursor at the moment you act on it loses your place in the list — so the
  // counts move immediately and the row does not.
  //
  // Except when it was the last one. Holding a settled row in an otherwise empty attention
  // filter says one thing still wants a person when nothing does, and deciding the last
  // item is exactly the moment the page should say the work is finished.
  const visible =
    matching.length &&
    selection?.kind === "finding" &&
    !matching.some((finding) => finding.candidate.id === selection.candidateId)
      ? findings.filter(
          (finding) =>
            matching.includes(finding) || finding.candidate.id === selection.candidateId,
        )
      : matching;
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;

  // Two groups, and only when there is a review to have moved since and both groups have
  // something in them. A heading over every row in the list is a heading that says nothing.
  const moved = visible.filter((finding) => movedSincePrevious(review, finding.candidate.id));
  const carried = visible.filter((finding) => !movedSincePrevious(review, finding.candidate.id));
  const grouped = Boolean(review.previous_review_id) && moved.length > 0 && carried.length > 0;
  const groups: Array<{ label: string | null; findings: Finding[] }> = grouped
    ? [
        { label: `Moved since review ${review.sequence - 1} · ${moved.length}`, findings: moved },
        { label: `Carried forward · ${carried.length}`, findings: carried },
      ]
    : [{ label: null, findings: visible }];

  /**
   * Walk the rows.
   *
   * Bound to the scroller rather than to the document, so it never competes with a text
   * field elsewhere on the page — and `j`/`k` are ignored while something typeable has
   * focus, because a reviewer writing a waiver's reasoning means the letter.
   */
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    if (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
      return;
    }
    const step =
      event.key === "ArrowDown" || event.key === "j"
        ? 1
        : event.key === "ArrowUp" || event.key === "k"
          ? -1
          : 0;
    if (!step) return;
    const rows = Array.from(
      list.ref.current?.querySelectorAll<HTMLButtonElement>("[data-candidate]") ?? [],
    );
    const next = neighbour(
      rows.map((row) => row.dataset.candidate ?? ""),
      selection?.kind === "finding" ? selection.candidateId : undefined,
      step,
    );
    if (!next) return;
    event.preventDefault();
    onSelect({ kind: "finding", candidateId: next });
    const row = rows.find((item) => item.dataset.candidate === next);
    row?.focus();
    row?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="border-b border-rule px-3 py-3">
        <h2 className="font-display text-sm font-semibold tracking-tight text-ink">
          Attention queue
        </h2>
        <p className="mt-0.5 text-xs text-ink-3">What this review needs from a human</p>
        <div
          role="group"
          aria-label="Filter the queue"
          className="mt-2.5 flex gap-1 rounded-md border border-rule bg-sunken/60 p-0.5"
        >
          {(
            [
              ["attention", "Attention", attention.length],
              ["settled", "Settled", settled.length],
              ["all", "All", findings.length],
            ] as const
          ).map(([id, label, count]) => (
            <ToggleButton
              key={id}
              pressed={filter === id}
              onClick={() => onFilterChange(id)}
              className="flex-1 justify-center"
            >
              {label}
              <span className="tabular-nums opacity-70">{count}</span>
            </ToggleButton>
          ))}
        </div>
      </div>

      {/* `overflow-y-auto` alone makes this a scroller sideways too — CSS resolves the
          other axis to `auto` — and one long dotted identifier then drags the rail out to
          its full width. Clipping the axis nothing should ever scroll on is half the fix;
          the other half is that no row is allowed to be wider than its column.

          The fade is the vertical counterpart: this list is usually taller than the rail,
          and an overlay scrollbar the platform hides until you touch it leaves the last
          visible row sliced against the footer's rule with nothing saying there is more. */}
      <div
        ref={list.ref}
        onKeyDown={onKeyDown}
        data-edge-top={list.edges.top}
        data-edge-bottom={list.edges.bottom}
        className="scroll-edge scrollbar-slim min-h-0 flex-1 overflow-y-auto overflow-x-clip"
      >
        {waiting ? (
          <button
            type="button"
            onClick={() => onSelect({ kind: "clarification" })}
            aria-current={selection?.kind === "clarification" ? "true" : undefined}
            className={cn(
              "w-full border-b border-rule border-l-2 border-l-held bg-held-soft/60 px-3 py-2.5 text-left transition",
              selection?.kind === "clarification" ? "bg-held-soft" : "hover:bg-held-soft/80",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-held">
                Clarification
              </span>
              <Badge tone="held" glyph="◆">
                Round {review.questions[0]?.round ?? 1}
              </Badge>
            </div>
            <div className="mt-1.5 text-sm font-semibold leading-5 text-ink">
              {plural(review.questions.length, "open question")}
            </div>
            <p className="mt-1 text-xs leading-5 text-ink-3">
              Answers become case context and the affected candidates are judged again.
            </p>
          </button>
        ) : null}

        {!visible.length ? (
          filter === "attention" && !waiting && findings.length ? (
            <WorkedThrough review={review} decisions={decisions} onReadReport={onReadReport} />
          ) : (
            <EmptyState
              title={findings.length ? "Nothing here" : "No candidates"}
              className="border-0 bg-transparent py-8"
            >
              {findings.length
                ? "Choose another filter to see the rest of this review."
                : "This review composed no findings. The delta still describes what was analysed."}
            </EmptyState>
          )
        ) : (
          <ul aria-label="Candidates" className="grid">
            {groups.map((group) => (
              <li key={group.label ?? "all"}>
                {group.label ? (
                  <h3 className="sticky top-0 z-10 border-b border-rule-strong bg-surface-2 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3">
                    {group.label}
                  </h3>
                ) : null}
                <ul className="grid">
                  {group.findings.map((finding) => (
                    <QueueRow
                      key={finding.candidate.id}
                      review={review}
                      finding={finding}
                      decision={decisions.get(finding.candidate.id)}
                      active={
                        selection?.kind === "finding" &&
                        selection.candidateId === finding.candidate.id
                      }
                      onSelect={() =>
                        onSelect({ kind: "finding", candidateId: finding.candidate.id })
                      }
                    />
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function QueueRow({
  review,
  finding,
  decision,
  active,
  onSelect,
}: {
  review: Review;
  finding: Finding;
  decision?: Decision;
  active: boolean;
  onSelect: () => void;
}) {
  const descriptor = verdictOf(finding.verdict);
  const disposition = decision ? dispositionOf(decision.disposition) : null;
  const stale = decisionIsStale(finding, decision);
  const delta = deltaStateOf(review, finding.candidate.id);
  const identity = finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary;
  const { namespace, leaf } = splitQualified(identity);

  return (
    <li>
      <button
        type="button"
        data-candidate={finding.candidate.id}
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        title={identity}
        className={cn(
          "w-full border-b border-l-2 border-b-rule px-3 py-2.5 text-left transition",
          // Selection is weight and position, never colour: in this interface a hue states
          // a verdict, so a coloured row reads as a grade.
          active ? "border-l-ink bg-sunken" : "border-l-transparent hover:bg-sunken/60",
        )}
      >
        <div className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-2.5">
          {/* Where the verdict glyph used to sit. The glyph moved down beside its own word,
              which is where it always belonged, and the column now carries how far through
              the three jobs this candidate is. */}
          <Spine
            verdict={finding.verdict}
            decided={Boolean(disposition) && !stale}
            className="mt-[3px]"
          />
          <span className="min-w-0">
            {namespace ? (
              <span className="block truncate font-mono text-[10.5px] text-ink-3">{namespace}</span>
            ) : null}
            <span className="block line-clamp-2 font-mono text-[12.5px] font-medium leading-[1.35] text-ink [overflow-wrap:anywhere]">
              {leaf}
            </span>
            <span className="mt-0.5 block line-clamp-2 text-[12.5px] leading-[1.4] text-ink-2 [overflow-wrap:anywhere]">
              {finding.candidate.summary}
            </span>
            <span className="mt-1 block truncate text-[10.5px] text-ink-3">
              <span
                className={cn(
                  "font-semibold",
                  descriptor.tone === "material" && "text-material",
                  descriptor.tone === "held" && "text-held",
                  descriptor.tone === "cleared" && "text-cleared",
                )}
              >
                <span aria-hidden="true" className="mr-1">
                  {descriptor.glyph}
                </span>
                {descriptor.label}
              </span>
              {" · "}
              {humanise(finding.candidate.pattern)}
              {delta ? ` · ${humanise(delta)}` : ""}
            </span>
            {/* The verdict is ArchCompass's; this is the team's, and the two are never
                merged into one word. It is the row's last line because it is the newest
                thing to have happened to the candidate — unless the judgement moved
                underneath it, in which case that is the newest thing. */}
            {stale && decision ? (
              <span className="mt-1 flex items-start gap-1 text-[10.5px] font-semibold leading-snug text-ink">
                <span aria-hidden="true">↺</span>
                {dispositionOf(decision.disposition).label} against{" "}
                {verdictOf(decision.finding_verdict).label.toLowerCase()} — now{" "}
                {descriptor.label.toLowerCase()}
              </span>
            ) : disposition ? (
              <span className="mt-1 flex items-center gap-1 text-[10.5px] font-semibold text-ink-2">
                <span aria-hidden="true">{disposition.glyph}</span>
                {disposition.label} by the team
              </span>
            ) : null}
          </span>
        </div>
      </button>
    </li>
  );
}

/**
 * The end of the work, said as the end of the work.
 *
 * The charter's rule is that the queue is the product and that every surface is the list,
 * something that helps decide an item, or the record of what was decided. Reaching the
 * bottom of the list is the one moment worth marking, and it used to be an empty state
 * reading "Nothing here".
 */
function WorkedThrough({
  review,
  decisions,
  onReadReport,
}: {
  review: Review;
  decisions: Map<string, Decision>;
  onReadReport?: () => void;
}) {
  const decided = review.findings.filter((finding) => decisions.has(finding.candidate.id)).length;
  const cleared = review.findings.filter((finding) => finding.verdict === "cleared").length;
  return (
    <div className="px-3 py-6">
      <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-cleared">
        <span aria-hidden="true" className="mr-1.5">
          ●
        </span>
        <span>Worked through</span>
      </div>
      <p className="mt-2 text-[13px] leading-6 text-ink-2">
        Nothing in this review is waiting on a person.{" "}
        {plural(decided, "candidate")} {decided === 1 ? "was" : "were"} decided by the team and{" "}
        {plural(cleared, "other")} came back cleared.
      </p>
      <div className="mt-3 grid gap-1.5">
        {review.status === "completed" && onReadReport ? (
          <button
            type="button"
            onClick={onReadReport}
            className="rounded-sm border border-rule-strong px-2.5 py-1.5 text-left text-xs font-semibold text-ink transition hover:bg-sunken"
          >
            Read the report →
          </button>
        ) : null}
        <Link
          to="/start"
          className="rounded-sm border border-rule px-2.5 py-1.5 text-xs font-semibold text-ink-2 transition hover:border-rule-strong hover:text-ink"
        >
          Run the next review →
        </Link>
      </div>
    </div>
  );
}
