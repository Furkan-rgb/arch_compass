import { useQuery } from "@tanstack/react-query";
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

/**
 * Whether this candidate still wants something from a person.
 *
 * Two ways to stop wanting one: ArchCompass cleared it, or the team decided what to do
 * about it. The second is why this takes the decision — a waived material finding is
 * settled, and a queue that keeps asking about it is a queue people stop trusting.
 */
export function needsAttention(finding: Finding, decision?: Decision | null): boolean {
  return finding.verdict !== "cleared" && !decision;
}

export function orderedFindings(review: Review): Finding[] {
  return [...review.findings].sort((left, right) => {
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

/**
 * The list a reviewer works down.
 *
 * Ordered by what needs a human rather than by detection order: material findings, then
 * held ones waiting on context, then everything that was cleared. Clarification sits at the
 * top when the review is waiting, because nothing below it can be finished until it is
 * answered.
 */
export function AttentionQueue({
  review,
  selection,
  onSelect,
  filter,
  onFilterChange,
  className,
}: {
  review: Review;
  selection: QueueSelection | null;
  onSelect: (selection: QueueSelection) => void;
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
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
  const visible =
    selection?.kind === "finding" &&
    !matching.some((finding) => finding.candidate.id === selection.candidateId)
      ? findings.filter(
          (finding) =>
            matching.includes(finding) || finding.candidate.id === selection.candidateId,
        )
      : matching;
  const waiting = review.status === "awaiting_answers" && review.questions.length > 0;

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
          <EmptyState title={filter === "attention" ? "Nothing waiting" : "Nothing here"} className="border-0 bg-transparent py-8">
            {filter === "attention"
              ? "Everything in this review is either cleared or decided."
              : "Choose another filter to see the rest of this review."}
          </EmptyState>
        ) : (
          <ul aria-label="Candidates" className="grid">
            {visible.map((finding) => {
              const descriptor = verdictOf(finding.verdict);
              const active =
                selection?.kind === "finding" && selection.candidateId === finding.candidate.id;
              const decision = decisions.get(finding.candidate.id);
              const disposition = decision ? dispositionOf(decision.disposition) : null;
              const delta = deltaStateOf(review, finding.candidate.id);
              const identity =
                finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary;
              const { namespace, leaf } = splitQualified(identity);
              return (
                <li key={finding.candidate.id}>
                  <button
                    type="button"
                    onClick={() => onSelect({ kind: "finding", candidateId: finding.candidate.id })}
                    aria-current={active ? "true" : undefined}
                    title={identity}
                    className={cn(
                      "w-full border-b border-l-2 border-b-rule px-3 py-2.5 text-left transition",
                      // Selection is weight and position, never colour: in this interface a
                      // hue states a verdict, so a coloured row reads as a grade.
                      active
                        ? "border-l-ink bg-sunken"
                        : "border-l-transparent hover:bg-sunken/60",
                    )}
                  >
                    <div className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-2.5">
                      {/* Where the verdict glyph used to sit. The glyph moved down beside its
                          own word, which is where it always belonged, and the column now
                          carries how far through the three jobs this candidate is. */}
                      <Spine
                        verdict={finding.verdict}
                        decided={Boolean(disposition)}
                        className="mt-[3px]"
                      />
                      <span className="min-w-0">
                        {namespace ? (
                          <span className="block truncate font-mono text-[10.5px] text-ink-3">
                            {namespace}
                          </span>
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
                        {/* The verdict is ArchCompass's; this is the team's, and the two are
                            never merged into one word. It is the row's last line because it
                            is the newest thing to have happened to the candidate. */}
                        {disposition ? (
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
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
