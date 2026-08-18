import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { coreApi, type Question, type Review } from "../api";
import { ErrorNotice } from "./ui";

export function QuestionsPanel({ review }: { review: Review }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const resume = useMutation({
    mutationFn: (stop: boolean) => coreApi.answer(review.id, review.questions.map((question) => ({ question_id: question.id, status: skipped.has(question.id) || !values[question.id]?.trim() ? "skipped" as const : "answered" as const, value: skipped.has(question.id) ? null : values[question.id] })), stop),
    onSuccess: async (next) => { await client.invalidateQueries({ queryKey: ["reviews"] }); navigate(`/reviews/${next.id}`); },
  });
  return (
    <section className="rounded-xl border border-primary/30 bg-primary/[0.03] p-6">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-primary">Clarification round {review.questions[0]?.round}</p><h2 className="mt-1 font-display text-2xl font-semibold">The code cannot answer these</h2><p className="mt-2 text-sm text-ink-2">Each response—or explicit skip—becomes part of the next immutable case revision.</p></div><span className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-on-accent">{review.questions.length}</span></div>
      <div className="mt-7 grid gap-7">{review.questions.map((question: Question, index) => <div key={question.id} className="grid gap-3"><label htmlFor={question.id} className="font-medium"><span className="mr-2 text-primary">{index + 1}.</span>{question.text}</label><div className="text-xs text-ink-3">Facet: {question.facet.replaceAll("_", " ")} · Supports {question.candidate_ids.length} candidate{question.candidate_ids.length === 1 ? "" : "s"}</div><textarea id={question.id} value={values[question.id] || ""} disabled={skipped.has(question.id)} onChange={(event) => setValues({ ...values, [question.id]: event.target.value })} className="min-h-28 w-full rounded-lg border border-rule bg-surface p-3 text-sm disabled:opacity-50" placeholder="Answer in your own words" /><label className="flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={skipped.has(question.id)} onChange={(event) => { const next = new Set(skipped); event.target.checked ? next.add(question.id) : next.delete(question.id); setSkipped(next); }} /> Skip explicitly</label></div>)}</div>
      <div className="mt-7 flex flex-wrap gap-3"><button disabled={resume.isPending} onClick={() => resume.mutate(false)} className="rounded-md bg-primary px-4 py-2.5 text-sm font-semibold text-on-accent disabled:opacity-50">Save and continue review</button><button disabled={resume.isPending} onClick={() => resume.mutate(true)} className="rounded-md border border-rule bg-surface px-4 py-2.5 text-sm font-medium">Conclude with remaining uncertainty</button></div>
      {resume.error ? <div className="mt-4"><ErrorNotice error={resume.error} /></div> : null}
    </section>
  );
}
