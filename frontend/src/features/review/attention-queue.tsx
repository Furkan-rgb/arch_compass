import type { Finding, Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural, splitQualified, verdictOf, verdictRank } from "../../lib/format";
import { Badge } from "../../ui/badge";
import { ToggleButton } from "../../ui/button";
import { EmptyState } from "../../ui/states";

export type QueueSelection = { kind: "clarification" } | { kind: "finding"; candidateId: string };

export type QueueFilter = "attention" | "cleared" | "all";

/** Where a candidate stands against the previous review, said in one word. */
export function deltaStateOf(review: Review, candidateId: string): string | null {
  if (review.delta.new.includes(candidateId)) return "new";
  if (review.delta.changed.some((item) => item.candidate_id === candidateId)) return "changed";
  if (review.delta.unchanged.includes(candidateId)) return "unchanged";
  return null;
}

export function needsAttention(finding: Finding): boolean {
  return finding.verdict !== "cleared";
}

export function orderedFindings(review: Review): Finding[] {
  return [...review.findings].sort((left, right) => {
    const rank = verdictRank(left.verdict) - verdictRank(right.verdict);
    if (rank !== 0) return rank;
    return left.candidate.summary.localeCompare(right.candidate.summary);
  });
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
  const findings = orderedFindings(review);
  const attention = findings.filter(needsAttention);
  const cleared = findings.filter((finding) => !needsAttention(finding));
  const visible = filter === "attention" ? attention : filter === "cleared" ? cleared : findings;
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
              ["cleared", "Cleared", cleared.length],
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
          the other half is that no row is allowed to be wider than its column. */}
      <div className="scrollbar-slim min-h-0 flex-1 overflow-y-auto overflow-x-clip p-1.5">
        {waiting ? (
          <button
            type="button"
            onClick={() => onSelect({ kind: "clarification" })}
            aria-current={selection?.kind === "clarification" ? "true" : undefined}
            className={cn(
              "mb-1.5 w-full border-l-2 border-held bg-held-soft/60 px-3 py-2.5 text-left transition",
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
              ? "No finding in this review needs a human decision."
              : "Choose another filter to see the rest of this review."}
          </EmptyState>
        ) : (
          <ul aria-label="Candidates" className="grid">
            {visible.map((finding) => {
              const descriptor = verdictOf(finding.verdict);
              const active =
                selection?.kind === "finding" && selection.candidateId === finding.candidate.id;
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
                      "w-full border-l-2 px-3 py-2.5 text-left transition",
                      // Selection is weight and position, never colour: in this interface a
                      // hue states a verdict, so a coloured row reads as a grade.
                      active
                        ? "border-l-ink bg-sunken"
                        : "border-l-transparent hover:bg-sunken/60",
                    )}
                  >
                    <div className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-2.5">
                      <span
                        aria-hidden="true"
                        className={cn(
                          "mt-[3px] text-[10px] leading-none",
                          descriptor.tone === "material" && "text-material",
                          descriptor.tone === "held" && "text-held",
                          descriptor.tone === "cleared" && "text-cleared",
                        )}
                      >
                        {descriptor.glyph}
                      </span>
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
                            {descriptor.label}
                          </span>
                          {" · "}
                          {humanise(finding.candidate.pattern)}
                          {delta ? ` · ${humanise(delta)}` : ""}
                        </span>
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
