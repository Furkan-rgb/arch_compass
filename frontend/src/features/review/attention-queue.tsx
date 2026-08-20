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

/** The identifier a row is scanned for, falling back to the sentence when there is none. */
function identityOf(finding: Finding): string {
  return finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary;
}

/**
 * Where a candidate stands against the previous review, written for the person reading it.
 *
 * Only `new` and `changed` are hoistable. "Unchanged" stated over a group says the group is
 * the part of the review nothing happened to, which is exactly what the section heading
 * above it already says, and two ways to say one thing is the bug this whole file is
 * fixing.
 */
function movementOf(review: Review, finding: Finding): string | null {
  const state = deltaStateOf(review, finding.candidate.id);
  if (state === "new") return "New this review";
  if (state === "changed") return "Changed this review";
  return null;
}

/**
 * The facts a row shares with the rows around it.
 *
 * One record read from both ends: whatever is in here the group header states once, and
 * whatever is missing the row still has to say for itself.
 */
type SharedFacts = {
  namespace?: string;
  pattern?: string;
  movement?: string;
  /** Set only where every member holds the same verdict — see `QueueGroup`. */
  verdict?: string;
};

type QueueGroup = {
  key: string;
  /** The heading over a whole section, carried by its first group and by nothing else. */
  section: string | null;
  shared: SharedFacts;
  /** Suppressed where the section heading above is already counting the same rows. */
  count: number | null;
  findings: Finding[];
};

/**
 * The runs of rows that repeat each other, and exactly which facts they repeat.
 *
 * Six consecutive candidates that are all in `ports`, all sole implementations, all new and
 * all held render that one sentence six times — and, because a verdict is a hue, put the
 * held amber on twenty elements to say the thing the first row already said. So the run
 * states it once and the rows below carry only what differs.
 *
 * The rule, derived rather than declared:
 *
 * - **The namespace decides where a run ends.** Consecutive rows are one run while they
 *   share the dotted prefix of their identifier, because that prefix is the longest string
 *   a row repeats and the one the eye has to read past to reach what differs. It also gives
 *   a run a name a reader can hold — a group is a place in the codebase, not a span that
 *   happened to agree about something.
 * - **Every other fact is hoisted only if it is universal.** The pattern, the movement and
 *   the verdict go up to the header when every member has the same one, and stay on the row
 *   where they are true otherwise. That is what keeps a mixed group honest: there the hue
 *   is doing real work, so the row keeps its pill.
 * - **A run of one hoists nothing.** A fact is not shared with anybody until there are two
 *   rows to share it, and a header over a single row is a header that says nothing.
 */
function groupsOf(
  review: Review,
  sections: Array<{ label: string | null; findings: Finding[] }>,
): QueueGroup[] {
  const groups: QueueGroup[] = [];
  for (const section of sections) {
    let index = 0;
    let firstOfSection = true;
    while (index < section.findings.length) {
      const namespace = splitQualified(identityOf(section.findings[index])).namespace;
      let end = index + 1;
      while (
        end < section.findings.length &&
        splitQualified(identityOf(section.findings[end])).namespace === namespace
      ) {
        end += 1;
      }
      const findings = section.findings.slice(index, end);
      const universal = (read: (finding: Finding) => string | null): string | undefined => {
        const first = read(findings[0]);
        return first && findings.every((finding) => read(finding) === first) ? first : undefined;
      };
      const shared: SharedFacts =
        findings.length > 1
          ? {
              namespace: namespace || undefined,
              pattern: universal((finding) => humanise(finding.candidate.pattern)),
              movement: universal((finding) => movementOf(review, finding)),
              verdict: universal((finding) => finding.verdict),
            }
          : {};
      const hoisted = Boolean(
        shared.namespace || shared.pattern || shared.movement || shared.verdict,
      );
      groups.push({
        key: `${section.label ?? "queue"}:${findings[0].candidate.id}`,
        section: firstOfSection ? section.label : null,
        shared,
        count:
          hoisted && !(firstOfSection && section.label && findings.length === section.findings.length)
            ? findings.length
            : null,
        findings,
      });
      firstOfSection = false;
      index = end;
    }
  }
  return groups;
}

/** Whether a group has anything to put above its rows. */
function stated(group: QueueGroup): boolean {
  const { section, shared } = group;
  return Boolean(section || shared.namespace || shared.pattern || shared.movement || shared.verdict);
}

/** The queue item a selection points at, as the string the walk moves between. */
function itemKey(selection: QueueSelection): string {
  return selection.kind === "clarification" ? "clarification" : selection.candidateId;
}

/**
 * The list a reviewer works down.
 *
 * Ordered by what moved and then by what needs a human, and grouped so the second visit
 * reads as the short list of what is different followed by everything carried forward.
 * Clarification sits above both when the review is waiting, because nothing below it can be
 * finished until it is answered — and it sits there as a row, not as a card, because it is
 * an item in this list and the list has one idiom.
 *
 * This is the one thing on the page that is touched a hundred times in a sitting, so it
 * moves from the keyboard: the arrow keys and `j`/`k` walk the rows and open what they land
 * on. That is not a shortcut for power users; it is the difference between triage and
 * clicking. The `‹ 1 of 6 ›` control in the header is the same movement under a pointer,
 * put where the keys that drive it are named rather than across the page in a tab strip.
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
  const decided = findings.filter((finding) => decisions.has(finding.candidate.id)).length;

  // Two sections, and only when there is a review to have moved since and both have
  // something in them. A heading over every row in the list is a heading that says nothing.
  const moved = visible.filter((finding) => movedSincePrevious(review, finding.candidate.id));
  const carried = visible.filter((finding) => !movedSincePrevious(review, finding.candidate.id));
  const split = Boolean(review.previous_review_id) && moved.length > 0 && carried.length > 0;
  const groups = groupsOf(
    review,
    split
      ? [
          { label: `Moved since review ${review.sequence - 1} · ${moved.length}`, findings: moved },
          { label: `Carried forward · ${carried.length}`, findings: carried },
        ]
      : [{ label: null, findings: visible }],
  );

  /**
   * Everything in the queue that a person can be standing on, in the order it is listed.
   *
   * The clarification is one of them. It is listed here because it is a thing needing a
   * person and this is the list of those, so `‹ 2 of 7 ›` counts it and `k` off the first
   * candidate lands on it rather than on nothing.
   */
  const items: QueueSelection[] = [
    ...(waiting ? [{ kind: "clarification" } as const] : []),
    ...visible.map((finding) => ({ kind: "finding", candidateId: finding.candidate.id }) as const),
  ];
  const keys = items.map(itemKey);
  const at = selection ? keys.indexOf(itemKey(selection)) : -1;

  /**
   * Move the reader one item, from a key or from the header's own control.
   *
   * Focus follows the move, and has to: `j`/`k` are bound to the scroller rather than to the
   * document so they never compete with a text field elsewhere on the page, which means a
   * reader who arrived by clicking `›` would otherwise have to click a row before the keys
   * worked again.
   */
  function move(step: number): boolean {
    const next = neighbour(keys, selection ? itemKey(selection) : undefined, step);
    if (!next) return false;
    onSelect(items[keys.indexOf(next)]);
    const row = Array.from(
      list.ref.current?.querySelectorAll<HTMLElement>("[data-queue-item]") ?? [],
    ).find((item) => item.dataset.queueItem === next);
    row?.focus();
    row?.scrollIntoView?.({ block: "nearest" });
    return true;
  }

  /**
   * Walk the rows.
   *
   * `j`/`k` are ignored while something typeable has focus, because a reviewer writing a
   * waiver's reasoning means the letter.
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
    if (move(step)) event.preventDefault();
  }

  // 44px because it is a touch target on a phone, `-my-1.5` because it should not be a 44px
  // hole in the queue header. The box is the target — a pseudo-element cannot be, since
  // getBoundingClientRect ignores an absolutely positioned ::after and a finger does not.
  const stepper =
    "inline-flex size-11 shrink-0 -my-1.5 items-center justify-center rounded-sm text-[13px] text-ink-3 transition hover:bg-sunken hover:text-ink disabled:pointer-events-none disabled:opacity-30";

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="shrink-0 border-b border-rule px-3 py-3">
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

        {/* Position belongs beside the keys that change it. It used to float in the tab
            strip on the other side of the page, a long way from the list it was counting
            and with no control next to it, so the only way to act on the number was to
            already know the keys. */}
        {items.length ? (
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <div role="group" aria-label="Move through the queue" className="flex items-center">
              <button
                type="button"
                aria-label="Previous in the queue"
                disabled={at <= 0}
                onClick={() => move(-1)}
                className={stepper}
              >
                <span aria-hidden="true">‹</span>
              </button>
              {/* A fixed track, so the `›` does not step sideways when the count goes from
                  one digit to two under a reader walking the list. */}
              <span className="min-w-14 px-0.5 text-center font-mono text-[10.5px] tabular-nums text-ink-3">
                {at >= 0 ? at + 1 : "—"} of {items.length}
              </span>
              <button
                type="button"
                aria-label="Next in the queue"
                disabled={at >= items.length - 1}
                onClick={() => move(1)}
                className={stepper}
              >
                <span aria-hidden="true">›</span>
              </button>
            </div>
            <span className="flex shrink-0 items-center gap-1 text-[10px] text-ink-3">
              <kbd className="rounded-xs border border-rule bg-sunken px-1 py-px font-mono text-[10px] leading-none">
                j
              </kbd>
              <kbd className="rounded-xs border border-rule bg-sunken px-1 py-px font-mono text-[10px] leading-none">
                k
              </kbd>
              to walk
            </span>
          </div>
        ) : null}
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
          <ClarificationRow
            review={review}
            active={selection?.kind === "clarification"}
            onSelect={() => onSelect({ kind: "clarification" })}
          />
        ) : null}

        {!visible.length ? (
          filter === "attention" && !waiting && findings.length ? (
            <WorkedThrough review={review} decided={decided} onReadReport={onReadReport} />
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
              <li key={group.key}>
                {stated(group) ? <GroupHeader group={group} /> : null}
                <ul className="grid">
                  {group.findings.map((finding) => (
                    <QueueRow
                      key={finding.candidate.id}
                      review={review}
                      finding={finding}
                      decision={decisions.get(finding.candidate.id)}
                      hoisted={group.shared}
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

      {/* Pinned under the scroller so the column ends on a line rather than on 600px of
          nothing. It counts what the filters cannot: "settled" includes everything
          ArchCompass cleared by itself, and this is the part the team did. */}
      {visible.length ? (
        <div className="shrink-0 border-t border-rule px-3 py-2 text-[10.5px] leading-4 text-ink-3">
          {decided
            ? `${decided} of ${plural(findings.length, "candidate")} decided by the team`
            : "Nothing decided by the team yet"}
        </div>
      ) : null}
    </div>
  );
}

/**
 * What every row under it repeats, said once.
 *
 * The verdict pill is the part worth being careful about. It appears only where the group
 * is homogeneous, and there it is the *only* place the verdict is stated — the rows below
 * drop their own pill and their tick shows how far through the three jobs they are
 * instead. Where the group disagrees there is no pill here at all and every row carries its
 * own, because that is a group whose hue is doing real work.
 */
function GroupHeader({ group }: { group: QueueGroup }) {
  const { section, shared, count } = group;
  const descriptor = shared.verdict ? verdictOf(shared.verdict) : null;
  const facts = [shared.pattern, shared.movement].filter(Boolean) as string[];
  const label = "truncate text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3";

  return (
    <h3 className="sticky top-0 z-10 border-b border-rule-strong bg-surface-2 px-3 py-1.5">
      {section ? <span className={cn("block", label)}>{section}</span> : null}
      {shared.namespace || facts.length || count || descriptor ? (
        <span className={cn("flex items-center gap-2", section && "mt-1")}>
          {/* The namespace is a machine-produced string, so it is mono, and it is the one
              thing in this header that can be arbitrarily long — `truncate` inside a box
              that is allowed to be narrower than it, or the header widens the rail and the
              page goes sideways behind it. */}
          {shared.namespace ? (
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] font-medium text-ink-2">
              <span className="sr-only">Everything below is in </span>
              {shared.namespace}
              <span aria-hidden="true">.*</span>
            </span>
          ) : facts.length ? (
            <span className={cn("min-w-0 flex-1", label)}>{facts.join(" · ")}</span>
          ) : null}
          <span className="ml-auto flex shrink-0 items-center gap-2">
            {count ? (
              <span className="font-mono text-[11px] tabular-nums text-ink-3">
                {count}
                <span className="sr-only"> candidates</span>
              </span>
            ) : null}
            {descriptor ? (
              <Badge
                tone={descriptor.tone}
                glyph={descriptor.glyph}
                className="px-2 py-0.5 text-[9.5px] tracking-[0.07em]"
              >
                All {descriptor.label.toLowerCase()}
              </Badge>
            ) : null}
          </span>
        </span>
      ) : null}
      {shared.namespace && facts.length ? (
        <span className={cn("mt-0.5 block", label)}>{facts.join(" · ")}</span>
      ) : null}
    </h3>
  );
}

/**
 * One candidate, carrying what the header above it did not already say.
 *
 * `hoisted` is the whole difference between the two versions of this row. In a homogeneous
 * group the verdict is gone from here — six amber ticks and six identical pills say the
 * same nothing six times — and the tick shows measured → judged → decided, which is what is
 * still varying down that column. In a mixed group the pill and the hue come back, because
 * there they are the only thing telling two rows apart at the edge of vision.
 */
function QueueRow({
  review,
  finding,
  decision,
  hoisted,
  active,
  onSelect,
}: {
  review: Review;
  finding: Finding;
  decision?: Decision;
  hoisted: SharedFacts;
  active: boolean;
  onSelect: () => void;
}) {
  const descriptor = verdictOf(finding.verdict);
  const disposition = decision ? dispositionOf(decision.disposition) : null;
  const stale = decisionIsStale(finding, decision);
  const delta = deltaStateOf(review, finding.candidate.id);
  const identity = identityOf(finding);
  const { namespace, leaf } = splitQualified(identity);
  const homogeneous = Boolean(hoisted.verdict);
  // What is left once the group has spoken. The pattern and the movement are dropped only
  // where the header states that exact fact for every row, never because they are quiet.
  const words = [
    hoisted.pattern ? null : humanise(finding.candidate.pattern),
    hoisted.movement || !delta ? null : humanise(delta),
  ].filter(Boolean) as string[];

  return (
    <li>
      <button
        type="button"
        data-candidate={finding.candidate.id}
        data-queue-item={finding.candidate.id}
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        title={identity}
        className={cn(
          "w-full min-h-11 border-b border-l-2 border-b-rule px-3 py-2.5 text-left transition",
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
            shows={homogeneous ? "stage" : "verdict"}
            className="mt-[3px]"
          />
          <span className="min-w-0">
            {/* Hoisting the namespace takes it off the eye's path, not out of the record:
                the whole identifier stays on the hover and stays what a screen reader
                reads, because a row that only ever says `Clock` cannot be told from the
                three other `Clock`s in the repository. */}
            {hoisted.namespace ? <span className="sr-only">{identity}</span> : null}
            {!hoisted.namespace && namespace ? (
              <span className="block truncate font-mono text-[10.5px] text-ink-3">{namespace}</span>
            ) : null}
            <span
              aria-hidden={hoisted.namespace ? "true" : undefined}
              className="line-clamp-2 font-mono text-[12.5px] font-medium leading-[1.35] text-ink [overflow-wrap:anywhere]"
            >
              {leaf}
            </span>
            <span className="mt-0.5 line-clamp-2 text-[12.5px] leading-[1.4] text-ink-2 [overflow-wrap:anywhere]">
              {finding.candidate.summary}
            </span>
            {!homogeneous || words.length ? (
              <span className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[10.5px] text-ink-3">
                {homogeneous ? null : (
                  <Badge
                    tone={descriptor.tone}
                    glyph={descriptor.glyph}
                    className="px-1.5 py-0 text-[9.5px] tracking-[0.06em]"
                  >
                    {descriptor.label}
                  </Badge>
                )}
                {words.length ? <span className="min-w-0 truncate">{words.join(" · ")}</span> : null}
              </span>
            ) : null}
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
 * The question the review is waiting on, listed as what it is: an item.
 *
 * It was a tinted card above the list — its own border, its own fill, its own pill — which
 * is three more ways of saying "held" than the one thing on it that means held. The state
 * the page is in is not a grade, so it is structural here: the same row, the same hit area,
 * the same selection, and one glyph in the one hue this file is allowed to spend, because
 * this is the row a reviewer has to find first.
 */
function ClarificationRow({
  review,
  active,
  onSelect,
}: {
  review: Review;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      data-queue-item="clarification"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "w-full min-h-11 border-b border-l-2 border-b-rule px-3 py-2.5 text-left transition",
        active ? "border-l-ink bg-sunken" : "border-l-transparent hover:bg-sunken/60",
      )}
    >
      <div className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-2.5">
        <span
          aria-hidden="true"
          className="mt-[3px] block text-center text-[10px] leading-4 text-held"
        >
          ◆
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3">
            Clarification · round {review.questions[0]?.round ?? 1}
          </span>
          <span className="mt-1 block text-[12.5px] font-semibold leading-[1.35] text-ink">
            {plural(review.questions.length, "open question")}
          </span>
          <span className="mt-0.5 block text-[10.5px] leading-[1.4] text-ink-3">
            Nothing below can be finished until these are answered.
          </span>
        </span>
      </div>
    </button>
  );
}

/**
 * The end of the work, said as the end of the work.
 *
 * The charter's rule is that the queue is the product and that every surface is the list,
 * something that helps decide an item, or the record of what was decided. Reaching the
 * bottom of the list is the one moment worth marking, and it used to be an empty state
 * reading "Nothing here".
 *
 * It is marked in ink rather than in the cleared green. "Worked through" is the state the
 * page is in, not a verdict anything was given, and painting a state in a verdict's hue is
 * the exact mistake that put the held amber across a whole screen.
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
    <div className="flex flex-col items-center px-5 py-10 text-center">
      <span
        aria-hidden="true"
        className="flex size-9 items-center justify-center rounded-full border border-rule-strong text-[13px] text-ink"
      >
        ●
      </span>
      <h3 className="mt-3 font-display text-[15px] font-semibold tracking-tight text-ink">
        Worked through
      </h3>
      <p className="mt-1.5 text-[12.5px] leading-6 text-ink-2">
        Nothing in this review is waiting on a person.{" "}
        {plural(decided, "candidate")} {decided === 1 ? "was" : "were"} decided by the team and{" "}
        {plural(cleared, "other")} came back cleared.
      </p>
      <div className="mt-5 w-full border-t border-rule pt-3 text-left">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3">
          What happens next
        </div>
        <div className="mt-2 grid gap-1.5">
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
    </div>
  );
}
