import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { coreApi, type Question, type Review } from "../api";
import { Button, ErrorNotice, Textarea, cn } from "./ui";

export function QuestionsPanel({ review }: { review: Review }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const resolved = review.questions.filter((question) => skipped.has(question.id) || Boolean(values[question.id]?.trim())).length;
  const resume = useMutation({
    mutationFn: (stop: boolean) => coreApi.answer(review.id, review.questions.map((question) => ({
      question_id: question.id,
      status: skipped.has(question.id) || !values[question.id]?.trim() ? "skipped" as const : "answered" as const,
      value: skipped.has(question.id) || !values[question.id]?.trim() ? null : values[question.id].trim(),
    })), stop),
    onSuccess: async (next) => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
      navigate(`/reviews/${next.id}`);
    },
  });

  function toggleSkip(questionId: string) {
    const next = new Set(skipped);
    if (next.has(questionId)) next.delete(questionId);
    else next.add(questionId);
    setSkipped(next);
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-primary/25 bg-surface shadow-card">
      <div className="border-b border-primary/15 bg-primary-soft px-5 py-5 sm:px-7 sm:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">Clarification round {review.questions[0]?.round}</p>
            <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight">The code cannot answer these</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-2">Your answers become architectural context in the next immutable case revision. Skip anything that should remain explicitly unknown.</p>
          </div>
          <div className="rounded-xl border border-primary/15 bg-surface px-3 py-2 text-right"><div className="font-display text-lg font-semibold tabular-nums">{resolved}/{review.questions.length}</div><div className="text-[10px] font-bold uppercase tracking-wider text-ink-3">resolved</div></div>
        </div>
      </div>

      <div className="divide-y divide-rule">
        {review.questions.map((question: Question, index) => {
          const isSkipped = skipped.has(question.id);
          return <div key={question.id} className="grid gap-4 px-5 py-6 sm:grid-cols-[36px_minmax(0,1fr)] sm:px-7">
            <div className={cn("grid size-8 place-items-center rounded-full text-sm font-bold", isSkipped ? "bg-canvas-strong text-ink-3" : "bg-primary-soft text-primary")}>{index + 1}</div>
            <div className="min-w-0">
              <label htmlFor={question.id} className="font-display text-lg font-semibold leading-6 text-ink">{question.text}</label>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-3"><span className="rounded-full bg-canvas-strong px-2 py-1">{question.facet.replaceAll("_", " ")}</span><span className="px-1 py-1">Affects {question.candidate_ids.length} candidate{question.candidate_ids.length === 1 ? "" : "s"}</span></div>
              <Textarea id={question.id} value={values[question.id] || ""} disabled={isSkipped} onChange={(event) => setValues({ ...values, [question.id]: event.target.value })} className="mt-4 min-h-32" placeholder="Add the architectural context that is not visible in the repository…" />
              <button type="button" aria-label="Skip explicitly" aria-pressed={isSkipped} onClick={() => toggleSkip(question.id)} className={cn("mt-3 rounded-lg px-2 py-1.5 text-xs font-semibold transition", isSkipped ? "bg-canvas-strong text-ink" : "text-ink-3 hover:bg-canvas-strong hover:text-ink")}>
                {isSkipped ? "Marked as explicitly skipped — undo" : "Skip explicitly"}
              </button>
            </div>
          </div>;
        })}
      </div>

      <div className="border-t border-rule bg-canvas-strong/35 px-5 py-5 sm:px-7">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="text-xs leading-5 text-ink-3">Unanswered items are recorded as skipped when you continue.</div>
          <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={resume.isPending} onClick={() => resume.mutate(true)}>Conclude with uncertainty</Button><Button disabled={resume.isPending} onClick={() => resume.mutate(false)}>{resume.isPending ? "Saving context…" : "Save and continue review"}</Button></div>
        </div>
        {resume.error ? <div className="mt-4"><ErrorNotice error={resume.error} /></div> : null}
      </div>
    </section>
  );
}
