/** The card at the top of a second pass: which verdicts the reader's answers moved. */

import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

import { sheet } from "../../components";
import { Cite } from "../../review-ledger";
import { answersBehind, type verdictChanges } from "./verdict-changes";
import type { OpenQuestion, RecordedAnswer } from "../../types";

export function WhatAnswersChanged({
  changes,
  total,
  questions,
  answered,
}: {
  changes: ReturnType<typeof verdictChanges>;
  total: number;
  /** The questions the first pass asked, where that pass has loaded. */
  questions: OpenQuestion[];
  /** What the answered revision recorded. Empty for a revision authored by hand. */
  answered: RecordedAnswer[];
}) {
  return (
    // Ruled down its accent side: what the reader's own answers did is a result about this
    // page, not one more panel on it. The `!` on the phone width: `sheet` strips its side
    // walls there, and this card's left edge is not a wall — it is the accent saying
    // "conclusion". Both rules live in the same breakpoint, so importance settles what
    // source order cannot promise.
    <section className={cn(sheet, "border-l-[3px] border-l-primary p-[var(--card-pad)] max-sm:border-l-[3px]!")}>
      <p className="m-0 flex items-start gap-2 text-body leading-reading">
        <ArrowRight size={15} aria-hidden className="mt-1 flex-none text-accent-ink" />
        <span>
          {changes.length === 0 ? (
            <>
              <strong>Your answers changed no verdict.</strong> All {total} came out the
              same way against the answered case — which is a result, not a wasted round: it
              means those verdicts never rested on what you were asked about.
            </>
          ) : (
            <>
              <strong>
                {changes.length} of {total}{" "}
                {changes.length === 1 ? "verdict" : "verdicts"} changed
              </strong>{" "}
              because of what you answered. Same repository, same atlas, same model — the
              only difference between the two passes is what the case now says.
            </>
          )}
        </span>
      </p>
      {changes.length > 0 ? (
        <ul className="m-0 mt-3 grid list-none gap-2 p-0">
          {changes.map((item) => {
            const behind = answersBehind(item.reference, questions, answered);
            return (
              <li
                key={item.reference}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui"
              >
                <Cite reference={item.reference} />
                <code className="text-meta text-ink-2">{item.title}</code>
                <span className="text-ui text-ink-2">
                  {item.from ? "should change" : "earning its place"} →{" "}
                  <strong className="text-ink">
                    {item.to ? "should change" : "earning its place"}
                  </strong>
                </span>
                {/* The sentence that did it, where one can be named. Absent rather than
                    guessed at: a verdict can move because a question about another boundary
                    changed what the case says overall, and claiming a cause there would be
                    inventing one.

                    Indented under the row it explains and given the full width of it,
                    because the whole point is that this is the sentence the reader wrote —
                    their words, under the question that drew them out. */}
                {behind.length > 0 ? (
                  <ul className="mt-[2px] mb-1 grid w-full list-none gap-1 border-l-2 border-accent-rule pl-3">
                    {behind.map((answer) => (
                      <li key={answer.question} className="grid gap-0.5 text-ui">
                        <span className="text-ink-3">{answer.question}</span>
                        <span className="text-ink-2">{answer.recordedText}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
