/**
 * The rules that decide what the docket shows, and in what order.
 *
 * This file used to be a component as well — a rail of rows down the left of the workbench —
 * and the rail is gone: the list and the assessments turned out to be one surface, which is
 * `docket.tsx`. What is left is the part that was always the valuable half. `needsAttention`
 * in particular is the single definition of "settled" in the product, shared by the docket,
 * the head's counts and the reviews page, so no two counts of the same list can disagree.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, type Decision, type Finding, type Review } from "../../api";
import { verdictRank } from "../../lib/format";

export type QueueFilter = "attention" | "settled" | "all";

/**
 * Whether this review is a round somebody can still answer.
 *
 * Here rather than at each of the six places that asked, for the reason `needsAttention` is
 * here: they are one rule, and two of them disagreeing puts a form on a page whose own
 * header says there is nothing to do.
 *
 * `status` alone was that rule and it is not enough. A review is immutable, so a snapshot
 * that asked a question says `awaiting_answers` for ever — true about the moment it was
 * recorded, and not about now. Answer the round and the work moves on; the snapshot does
 * not, so the page kept offering the form. Submitting it did nothing, because the server
 * refuses a submission written against a superseded snapshot — which is the right answer to
 * a request that should never have been offered.
 *
 * `answerable` is the server's answer to exactly this: the round is open, and this snapshot
 * is the one it is open on. Optional in the schema, so an older payload reads as `false` —
 * which errs towards not drawing a control rather than towards drawing a dead one.
 */
export function awaitsAnswers(review: Review): boolean {
  return Boolean(review.answerable) && review.questions.length > 0;
}

/**
 * What the team has decided about each candidate on this branch, by candidate.
 *
 * Read through the same query key the decision bar writes through, so recording a decision
 * updates the queue in the same tick rather than on the next reload. A standing decision
 * belongs to the branch, not to the review — it outlives this snapshot.
 */
export function useStandingDecisions(review: Review | undefined): {
  byCandidate: Map<string, Decision>;
  /**
   * Whether the branch's decisions have actually arrived.
   *
   * An empty map means two different things — nobody has decided anything, and the request
   * is still in flight — and one caller has to tell them apart: the docket picks the row it
   * opens on from what still wants a person, and picking that before the decisions land
   * opens something the team settled last week.
   */
  ready: boolean;
} {
  const branchId = review?.repository.branch_id;
  const decisions = useQuery({
    queryKey: ["decisions", branchId],
    queryFn: () => api.decisions(branchId!),
    enabled: Boolean(branchId),
  });
  const byCandidate = useMemo(
    () => new Map((decisions.data?.decisions ?? []).map((item) => [item.candidate_id, item])),
    [decisions.data],
  );
  return { byCandidate, ready: !branchId || decisions.isSuccess || decisions.isError };
}

/**
 * The delta as three sets of candidate ids, built once for a whole list.
 *
 * The delta arrives as three arrays, and asking "where does this candidate stand" of the
 * arrays is three linear scans. That is fine for one candidate and quadratic for a sort:
 * `orderedFindings`' comparator asks it twice per comparison, so a 40-candidate review on a
 * 35KB delta did the scans some two thousand times, on every render of the page.
 */
export type DeltaIndex = {
  new: Set<string>;
  changed: Set<string>;
  unchanged: Set<string>;
};

export function deltaIndexOf(review: Review): DeltaIndex {
  return {
    new: new Set(review.delta.new),
    changed: new Set(review.delta.changed.map((item) => item.candidate_id)),
    unchanged: new Set(review.delta.unchanged),
  };
}

/**
 * Handed a review, this builds the index for the one question being asked, which is what a
 * caller asking about a single candidate wants. A caller walking a list builds one index with
 * `deltaIndexOf` and hands it in — that is the difference between linear and quadratic here.
 */
function asIndex(source: Review | DeltaIndex): DeltaIndex {
  return "delta" in source ? deltaIndexOf(source) : source;
}

/** Where a candidate stands against the previous review, said in one word. */
export function deltaStateOf(source: Review | DeltaIndex, candidateId: string): string | null {
  const delta = asIndex(source);
  if (delta.new.has(candidateId)) return "new";
  if (delta.changed.has(candidateId)) return "changed";
  if (delta.unchanged.has(candidateId)) return "unchanged";
  return null;
}

/** Whether this candidate is one of the ones that moved since the review before. */
export function movedSincePrevious(source: Review | DeltaIndex, candidateId: string): boolean {
  const delta = asIndex(source);
  return delta.new.has(candidateId) || delta.changed.has(candidateId);
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
 *
 * The index is built before the sort rather than inside the comparator. It is the same three
 * questions either way; the difference is asking them once per candidate instead of once per
 * comparison. Callers memoise the result — this runs on a list a person is reading, and the
 * page around it re-renders on every keystroke and every four-second poll.
 */
export function orderedFindings(review: Review): Finding[] {
  const delta = deltaIndexOf(review);
  return [...review.findings].sort((left, right) => {
    const moved =
      Number(movedSincePrevious(delta, right.candidate.id)) -
      Number(movedSincePrevious(delta, left.candidate.id));
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

