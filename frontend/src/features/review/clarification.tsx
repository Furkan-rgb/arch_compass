import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/field";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";

/**
 * A clarification round.
 *
 * Not a chat. Each question is a numbered item in a form with its own reason for existing,
 * the candidates it affects, an answer, and an explicit skip. Submitting produces the next
 * case revision and the next review — which is why the button says so.
 */
export function ClarificationRound({
  review,
  className,
}: {
  review: Review;
  className?: string;
}) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  const answered = review.questions.filter((question) => Boolean(values[question.id]?.trim()));
  const resolved = review.questions.filter(
    (question) => skipped.has(question.id) || Boolean(values[question.id]?.trim()),
  );

  const resume = useMutation({
    mutationFn: (stop: boolean) =>
      api.answer(
        review.id,
        review.questions.map((question) => {
          const value = values[question.id]?.trim();
          const skip = skipped.has(question.id) || !value;
          return {
            question_id: question.id,
            status: skip ? ("skipped" as const) : ("answered" as const),
            value: skip ? null : value,
          };
        }),
        stop,
      ),
    onSuccess: async (next) => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
      navigate(`/reviews/${next.id}`);
    },
  });

  function toggleSkip(questionId: string) {
    setSkipped((current) => {
      const next = new Set(current);
      if (next.has(questionId)) next.delete(questionId);
      else next.add(questionId);
      return next;
    });
  }

  return (
    <section
      aria-labelledby="clarification-heading"
      className={cn(
        "animate-fade overflow-hidden rounded-lg border border-held/35 bg-surface shadow-panel",
        className,
      )}
    >
      <header className="border-b border-held/25 bg-held-soft/50 px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <Label className="text-held">
              Clarification round {review.questions[0]?.round ?? 1}
            </Label>
            <h2
              id="clarification-heading"
              className="mt-1.5 font-display text-xl font-semibold tracking-tight text-ink sm:text-2xl"
            >
              The repository cannot answer these
            </h2>
            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-ink-2">
              Answers are recorded on the architecture case as a new revision, and the affected
              candidates are judged again. Skip anything that should stay explicitly unknown.
            </p>
          </div>
          <div className="rounded-md border border-rule bg-surface px-3 py-2 text-center">
            <div className="font-display text-lg font-semibold tabular-nums text-ink">
              {resolved.length}/{review.questions.length}
            </div>
            <div className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink-3">
              resolved
            </div>
          </div>
        </div>
      </header>

      <ol className="divide-y divide-rule">
        {review.questions.map((question, index) => {
          const isSkipped = skipped.has(question.id);
          const affected = review.findings.filter((finding) =>
            question.candidate_ids.includes(finding.candidate.id),
          );
          return (
            <li key={question.id} className="px-4 py-4 sm:px-5">
              <div className="flex gap-3">
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold",
                    isSkipped ? "bg-sunken text-ink-3" : "bg-accent-soft text-accent",
                  )}
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <label
                    htmlFor={`question-${question.id}`}
                    className="block font-display text-base font-semibold leading-6 text-ink"
                  >
                    {question.text}
                  </label>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <Tag>{humanise(question.facet)}</Tag>
                    <span className="text-xs text-ink-3">
                      {affected.length ? (
                        <>
                          Affects {affected[0].candidate.summary}
                          {affected.length > 1
                            ? ` and ${plural(affected.length - 1, "other candidate")}`
                            : ""}
                        </>
                      ) : (
                        plural(question.candidate_ids.length, "affected candidate")
                      )}
                    </span>
                  </div>
                  <Textarea
                    id={`question-${question.id}`}
                    value={values[question.id] || ""}
                    disabled={isSkipped}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [question.id]: event.target.value }))
                    }
                    className="mt-2.5 min-h-24"
                    placeholder="Add the architectural context that is not visible in the code…"
                  />
                  <button
                    type="button"
                    aria-pressed={isSkipped}
                    onClick={() => toggleSkip(question.id)}
                    className={cn(
                      "mt-2 rounded-sm px-2 py-1 text-xs font-semibold transition",
                      isSkipped
                        ? "bg-sunken text-ink"
                        : "text-ink-3 hover:bg-sunken hover:text-ink",
                    )}
                  >
                    {isSkipped ? "Skipped explicitly — undo" : "Skip explicitly"}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <footer className="border-t border-rule bg-sunken/40 px-4 py-3.5 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <p className="text-xs leading-5 text-ink-3">
            Anything left blank is recorded as skipped. Nothing is inferred on your behalf.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={resume.isPending}
              onClick={() => resume.mutate(true)}
            >
              Conclude with remaining uncertainty
            </Button>
            <Button disabled={resume.isPending} onClick={() => resume.mutate(false)}>
              {resume.isPending ? (
                <>
                  <Spinner /> Saving context…
                </>
              ) : (
                "Save and rejudge"
              )}
            </Button>
          </div>
        </div>
        <LiveRegion>
          {`${answered.length} answered, ${skipped.size} skipped, of ${review.questions.length} questions.`}
        </LiveRegion>
        {resume.error ? (
          <div className="mt-3">
            <ErrorNotice error={resume.error} />
          </div>
        ) : null}
      </footer>
    </section>
  );
}
