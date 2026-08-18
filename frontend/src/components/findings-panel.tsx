import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi, type Finding, type Review } from "../api";
import { ErrorNotice, StatusBadge } from "./ui";

function DecisionBar({ review, finding }: { review: Review; finding: Finding }) {
  const client = useQueryClient();
  const [reasoning, setReasoning] = useState("");
  const decisions = useQuery({ queryKey: ["decisions", review.repository.branch_id], queryFn: () => coreApi.decisions(review.repository.branch_id) });
  const current = decisions.data?.decisions.find((item) => item.candidate_id === finding.candidate.id);
  const decide = useMutation({ mutationFn: (disposition: "accept" | "waive" | "park") => coreApi.decide(review.id, finding.candidate.id, disposition, reasoning.trim() || null), onSuccess: () => client.invalidateQueries({ queryKey: ["decisions", review.repository.branch_id] }) });
  return <div className="mt-5 border-t border-rule pt-4"><div className="flex flex-wrap items-center gap-2">{current ? <span className="mr-2 text-xs text-ink-3">Team decision: <strong className="text-ink">{current.disposition}</strong></span> : <span className="mr-2 text-xs text-ink-3">No standing decision</span>}{(["accept", "park", "waive"] as const).map((item) => <button key={item} disabled={item === "waive" && !reasoning.trim()} onClick={() => decide.mutate(item)} className="rounded-md border border-rule px-3 py-1.5 text-xs font-medium hover:border-primary disabled:opacity-40">{item}</button>)}</div><input value={reasoning} onChange={(event) => setReasoning(event.target.value)} className="mt-3 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm" placeholder="Decision reasoning (required for waiver)" />{decide.error ? <div className="mt-3"><ErrorNotice error={decide.error} /></div> : null}</div>;
}

function EvidenceBlock({ finding }: { finding: Finding }) {
  return <div className="mt-5 grid gap-3">{finding.evidence.map((evidence, index) => <details key={`${evidence.location?.path}-${index}`} className="rounded-lg border border-rule bg-canvas p-3"><summary className="cursor-pointer text-sm font-medium">{evidence.description}{evidence.location ? <span className="ml-2 font-mono text-xs text-ink-3">{evidence.location.path}:{evidence.location.start_line}</span> : null}</summary>{evidence.excerpt ? <pre className="mt-3 overflow-x-auto rounded-md bg-[#171b20] p-4 text-xs leading-5 text-[#d8dee9]"><code>{evidence.excerpt}</code></pre> : <p className="mt-2 text-xs text-ink-3">No source excerpt was pinned.</p>}</details>)}</div>;
}

export function FindingsPanel({ review }: { review: Review }) {
  if (!review.findings.length) return <div className="rounded-xl border border-dashed border-rule p-10 text-center text-sm text-ink-3">No findings were composed.</div>;
  return <div className="grid gap-4">{review.findings.map((finding) => <article id={finding.candidate.id} key={finding.candidate.id} className="rounded-xl border border-rule bg-surface p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><div className="text-xs font-semibold uppercase tracking-wider text-primary">{finding.candidate.pattern.replaceAll("_", " ")}</div><h2 className="mt-1 font-display text-xl font-semibold">{finding.candidate.summary}</h2></div><StatusBadge status={finding.verdict} /></div><p className="mt-4 leading-7 text-ink-2">{finding.reasoning}</p>{finding.hinge ? <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm"><strong>Uncertainty hinge:</strong> {finding.hinge}</div> : null}{finding.recommended_response ? <div className="mt-4 text-sm"><strong>Recommended response:</strong> {finding.recommended_response}</div> : null}<div className="mt-4 flex flex-wrap gap-2">{finding.policies.map((bearing) => <span key={bearing.policy_id} title={bearing.reasoning} className="rounded-full border border-rule px-2.5 py-1 text-xs text-ink-2">{bearing.policy_title}</span>)}</div><EvidenceBlock finding={finding} /><div className="mt-4 text-xs text-ink-3">{finding.candidate.participants.map((item) => `${item.role}: ${item.qualified_name}`).join(" · ")}{finding.reused_from_review_id ? ` · reused from ${finding.reused_from_review_id}` : ""}</div><DecisionBar review={review} finding={finding} /></article>)}</div>;
}
