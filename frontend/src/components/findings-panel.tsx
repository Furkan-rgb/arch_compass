import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi, type Finding, type Review } from "../api";
import { Button, Empty, ErrorNotice, Input, StatusBadge, cn } from "./ui";

function DecisionBar({ review, finding }: { review: Review; finding: Finding }) {
  const client = useQueryClient();
  const [reasoning, setReasoning] = useState("");
  const decisions = useQuery({ queryKey: ["decisions", review.repository.branch_id], queryFn: () => coreApi.decisions(review.repository.branch_id) });
  const current = decisions.data?.decisions.find((item) => item.candidate_id === finding.candidate.id);
  const decide = useMutation({
    mutationFn: (disposition: "accept" | "waive" | "park") => coreApi.decide(review.id, finding.candidate.id, disposition, reasoning.trim() || null),
    onSuccess: async () => {
      setReasoning("");
      await client.invalidateQueries({ queryKey: ["decisions", review.repository.branch_id] });
    },
  });

  return <div className="mt-6 rounded-xl border border-rule bg-canvas-strong/45 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><div className="text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Standing decision</div><div className="mt-1 text-sm text-ink-2">{current ? <>The team chose <strong className="text-ink">{current.disposition}</strong> for this candidate.</> : "Record what the team intends to do. This stays separate from ArchCompass's finding."}</div></div>
      {current ? <StatusBadge status={current.disposition} /> : null}
    </div>
    <Input aria-label="Decision reasoning" value={reasoning} onChange={(event) => setReasoning(event.target.value)} className="mt-4" placeholder="Why? Required when waiving a finding." />
    <div className="mt-3 flex flex-wrap gap-2">{(["accept", "park", "waive"] as const).map((item) => <Button key={item} size="sm" variant={current?.disposition === item ? "primary" : item === "waive" ? "danger" : "secondary"} disabled={decide.isPending || (item === "waive" && !reasoning.trim())} onClick={() => decide.mutate(item)}>{item === "accept" ? "Accept work" : item === "park" ? "Park for later" : "Waive"}</Button>)}</div>
    {decide.error ? <div className="mt-3"><ErrorNotice error={decide.error} /></div> : null}
  </div>;
}

function EvidenceBlock({ finding }: { finding: Finding }) {
  if (!finding.evidence.length) return null;
  return <div className="mt-5"><div className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Pinned evidence · {finding.evidence.length}</div><div className="grid gap-2">{finding.evidence.map((evidence, index) => <details key={`${evidence.location?.path}-${index}`} className="group rounded-xl border border-rule bg-canvas-strong/35 open:bg-canvas-strong/65"><summary className="flex list-none items-start justify-between gap-3 p-3.5 text-sm font-semibold"><span>{evidence.description}</span><span className="shrink-0 font-mono text-[10px] font-normal text-ink-3">{evidence.location ? `${evidence.location.path}:${evidence.location.start_line}` : "No location"}</span></summary>{evidence.excerpt ? <pre className="mx-3 mb-3 overflow-x-auto rounded-lg bg-[#151922] p-4 text-xs leading-5 text-[#dce3ef]"><code>{evidence.excerpt}</code></pre> : <p className="px-3 pb-3 text-xs text-ink-3">No source excerpt was pinned.</p>}</details>)}</div></div>;
}

export function FindingsPanel({ review }: { review: Review }) {
  const [filter, setFilter] = useState("all");
  if (!review.findings.length) return <Empty title="No findings">No architectural findings were composed for this review.</Empty>;
  const filters = ["all", "material", "held", "cleared"];
  const visible = filter === "all" ? review.findings : review.findings.filter((finding) => finding.verdict === filter);

  return <div>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="font-display text-xl font-semibold">Architecture findings</h2><p className="mt-1 text-sm text-ink-3">Assessment and team disposition are intentionally recorded separately.</p></div>
      <div className="flex rounded-xl border border-rule bg-surface p-1" aria-label="Filter findings">{filters.map((item) => { const count = item === "all" ? review.findings.length : review.findings.filter((finding) => finding.verdict === item).length; return <button key={item} onClick={() => setFilter(item)} aria-pressed={filter === item} className={cn("rounded-lg px-3 py-2 text-xs font-semibold capitalize transition", filter === item ? "bg-primary text-on-accent" : "text-ink-2 hover:bg-canvas-strong")}>{item} <span className="ml-1 opacity-70">{count}</span></button>; })}</div>
    </div>
    {!visible.length ? <Empty title={`No ${filter} findings`}>Choose another filter to inspect this review.</Empty> : <div className="grid gap-4">{visible.map((finding) => <article id={finding.candidate.id} key={finding.candidate.id} className="overflow-hidden rounded-2xl border border-rule bg-surface shadow-card">
      <div className="p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><div className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{finding.candidate.pattern.replaceAll("_", " ")}</div><h3 className="mt-1 font-display text-xl font-semibold tracking-tight sm:text-2xl">{finding.candidate.summary}</h3></div><StatusBadge status={finding.verdict} /></div>
        <p className="mt-4 max-w-4xl text-[15px] leading-7 text-ink-2">{finding.reasoning}</p>
        {finding.hinge ? <div className="mt-5 rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm leading-6 text-warning"><strong className="block font-semibold">What remains uncertain</strong>{finding.hinge}</div> : null}
        {finding.recommended_response ? <div className="mt-5 rounded-xl border-l-4 border-primary bg-primary-soft px-4 py-3 text-sm leading-6"><strong className="text-ink">Recommended response: </strong><span className="text-ink-2">{finding.recommended_response}</span></div> : null}
        {finding.policies.length ? <div className="mt-5 flex flex-wrap gap-2">{finding.policies.map((bearing) => <span key={bearing.policy_id} title={bearing.reasoning} className="rounded-full border border-rule-strong bg-surface px-2.5 py-1 text-xs font-medium text-ink-2">{bearing.policy_title}</span>)}</div> : null}
        <EvidenceBlock finding={finding} />
        <div className="mt-5 border-t border-rule pt-4 text-xs leading-5 text-ink-3"><span className="font-semibold text-ink-2">Participants: </span>{finding.candidate.participants.map((item) => `${item.role}: ${item.qualified_name}`).join(" · ")}{finding.reused_from_review_id ? <span> · reused from review {finding.reused_from_review_id.slice(0, 10)}</span> : null}</div>
        <DecisionBar review={review} finding={finding} />
      </div>
    </article>)}</div>}
  </div>;
}
