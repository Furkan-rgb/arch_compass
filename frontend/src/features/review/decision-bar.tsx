import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type DecisionDisposition, type Finding, type Review } from "../../api";
import { absoluteTime, verdictOf } from "../../lib/format";
import { DispositionBadge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Input } from "../../ui/field";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion } from "../../ui/states";
import { decisionIsStale } from "./attention-queue";

const CHOICES: Array<{ id: DecisionDisposition; label: string; help: string }> = [
  { id: "accept", label: "Accept and act", help: "The team intends to act on this finding." },
  { id: "park", label: "Park for now", help: "Acknowledged, deliberately not now." },
  { id: "waive", label: "Waive", help: "The team disagrees or accepts the trade-off." },
];

/**
 * The human half of the review, kept visibly separate from the model's half.
 *
 * A standing decision belongs to the branch, not to this review: it survives the next run
 * and is what the team, rather than ArchCompass, has decided. Waiving needs a reason,
 * because a waiver with no reasoning is the one decision nobody can audit later.
 *
 * A decision also records the verdict it was taken against. When that no longer matches
 * what ArchCompass says, this leads with the discrepancy rather than with the decision:
 * the team settled a different question, and nothing withdraws the old record on their
 * behalf — it is stated, and the same three dispositions are offered again.
 */
export function DecisionBar({ review, finding }: { review: Review; finding: Finding }) {
  const client = useQueryClient();
  const [reasoning, setReasoning] = useState("");
  const branchId = review.repository.branch_id;
  const decisions = useQuery({
    queryKey: ["decisions", branchId],
    queryFn: () => api.decisions(branchId),
  });
  const current = decisions.data?.decisions.find(
    (item) => item.candidate_id === finding.candidate.id,
  );
  const stale = decisionIsStale(finding, current);
  const decide = useMutation({
    mutationFn: (disposition: DecisionDisposition) =>
      api.decide(review.id, finding.candidate.id, disposition, reasoning.trim() || null),
    onSuccess: async () => {
      setReasoning("");
      await client.invalidateQueries({ queryKey: ["decisions", branchId] });
    },
  });

  return (
    <section aria-labelledby="standing-decision">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Label>
            <span id="standing-decision">Standing decision</span>
          </Label>
          <p className="mt-1.5 text-sm leading-6 text-ink-2">
            {current ? (
              <>
                Recorded by <span className="font-medium text-ink">{current.author}</span> on{" "}
                {absoluteTime(current.decided_at)}.
                {current.reasoning ? (
                  <span className="mt-1 block text-ink-3">“{current.reasoning}”</span>
                ) : null}
              </>
            ) : (
              "ArchCompass does not decide this. Record what the team intends to do."
            )}
          </p>
        </div>
        {current ? <DispositionBadge disposition={current.disposition} /> : null}
      </div>

      {stale && current ? (
        <div className="mt-3 border-l-2 border-held bg-held-soft/60 px-3.5 py-3">
          <div className="text-[10px] font-bold uppercase tracking-[0.11em] text-held">
            Decided against a different verdict
          </div>
          <p className="mt-1.5 max-w-[58ch] text-[13px] leading-6 text-ink-2">
            The team decided this when ArchCompass called it{" "}
            <span className="font-semibold text-ink">
              {verdictOf(current.finding_verdict).label.toLowerCase()}
            </span>
            . This review calls it{" "}
            <span className="font-semibold text-ink">
              {verdictOf(finding.verdict).label.toLowerCase()}
            </span>
            . The record stands as it was made — recording a decision again is what settles
            it against what ArchCompass says now.
          </p>
        </div>
      ) : null}

      <Input
        aria-label="Reasoning for this decision"
        value={reasoning}
        onChange={(event) => setReasoning(event.target.value)}
        className="mt-3"
        placeholder="Why the team decided this. Required to waive."
      />

      <div className="mt-2.5 flex flex-wrap gap-2">
        {CHOICES.map((choice) => (
          <Button
            key={choice.id}
            size="sm"
            title={choice.help}
            variant={
              current?.disposition === choice.id && !stale
                ? "primary"
                : choice.id === "waive"
                  ? "danger"
                  : "secondary"
            }
            disabled={decide.isPending || (choice.id === "waive" && !reasoning.trim())}
            onClick={() => decide.mutate(choice.id)}
          >
            {choice.label}
          </Button>
        ))}
      </div>

      {decide.isSuccess ? <LiveRegion>Standing decision recorded.</LiveRegion> : null}
      {decide.error ? (
        <div className="mt-3">
          <ErrorNotice error={decide.error} />
        </div>
      ) : null}
    </section>
  );
}
