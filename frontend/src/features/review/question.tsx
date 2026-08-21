import type { ReactNode } from "react";

import type { Finding, Question } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Textarea } from "../../ui/field";
import { Mono } from "../../ui/meta";

/**
 * One proposed answer.
 *
 * A real radio, so a keyboard moves through the group with the arrow keys and a screen
 * reader announces it as a choice among several rather than as a button that does something.
 */
function ChoiceRow({
  name,
  checked,
  disabled,
  onSelect,
  children,
}: {
  name: string;
  checked: boolean;
  disabled: boolean;
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex min-h-11 cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm leading-6 transition",
        disabled && "cursor-not-allowed opacity-50",
        checked
          ? "border-rule-strong bg-sunken text-ink"
          : "border-rule bg-surface-2 text-ink hover:border-rule-strong",
      )}
    >
      <input
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
        className="mt-1.5 size-3.5 shrink-0 accent-[var(--ink)]"
      />
      <span className="min-w-0">{children}</span>
    </label>
  );
}

/**
 * One question, and every way there is to answer it.
 *
 * Extracted from the round because the round no longer shows all of them at once: it shows
 * this one. Everything here is controlled — the value, whether the reviewer has taken the
 * menu off, whether it is skipped — because a question is unmounted when you step past it
 * and remounted when you step back, and an answer that lived in here would not survive the
 * trip. The parent holds the whole round's state and this draws one slice of it.
 */
export function QuestionItem({
  question,
  affected,
  value,
  writingOwn,
  skipped,
  onChoose,
  onWriteOwn,
  onWrite,
  onToggleSkip,
  className,
}: {
  question: Question;
  /** The findings this question was raised against, resolved by the round. */
  affected: Finding[];
  value: string;
  /** The reviewer has said none of the proposals fit; the box is theirs. */
  writingOwn: boolean;
  skipped: boolean;
  onChoose: (option: string) => void;
  onWriteOwn: () => void;
  onWrite: (value: string) => void;
  onToggleSkip: () => void;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      {/* The question is the point of the panel, so it is the one thing set at the reading
          size. Nothing else goes above 14px — the facet, the affected candidates and the
          skip are all context for this one sentence.

          Not a `<label>`. It was one, pointing at the box — which only exists where there is
          nothing to pick, so on the common question it named a control that was not there.
          A named element the box points back at works whichever shape the question takes. */}
      <p
        id={`question-${question.id}-text`}
        className="max-w-[54ch] text-[17px] font-medium leading-7 text-ink"
      >
        {question.text}
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Tag>{humanise(question.facet)}</Tag>
        {/* Named, not described: a reviewer wants to know *which* candidates turn on this,
            and a sentence beginning "Affects ports.TaskFormatter is implemented only by…"
            is neither. Not links, either — this is a form with answers in it, and nothing
            here is allowed to unmount it. */}
        <span className="min-w-0 text-xs text-ink-3 wrap-anywhere">
          {affected.length ? (
            <>
              Affects{" "}
              <Mono className="text-[11px] text-ink-2">
                {affected[0].candidate.participants[0]?.qualified_name ??
                  affected[0].candidate.summary}
              </Mono>
              {affected.length > 1
                ? ` and ${plural(affected.length - 1, "other")}`
                : ""}
            </>
          ) : (
            plural(question.candidate_ids.length, "affected candidate")
          )}
        </span>
      </div>

      {question.options.length ? (
        <div
          role="radiogroup"
          aria-label={`Answers to: ${question.text}`}
          className="mt-3 grid gap-1.5"
        >
          {question.options.map((option) => (
            <ChoiceRow
              key={option}
              name={`answer-${question.id}`}
              checked={value === option}
              disabled={skipped}
              onSelect={() => onChoose(option)}
            >
              {option}
            </ChoiceRow>
          ))}
          <ChoiceRow
            name={`answer-${question.id}`}
            checked={writingOwn}
            disabled={skipped}
            onSelect={onWriteOwn}
          >
            <span className="text-ink-2">Something else — I will write it</span>
          </ChoiceRow>
        </div>
      ) : null}

      {/* The box is always reachable, but it only takes the floor when there is no shorter
          way to answer or the reviewer has said none of these fit. A menu that cannot be
          escaped would be a worse question than a blank one — the model proposed these, it
          did not establish them. */}
      {!question.options.length || writingOwn ? (
        <Textarea
          id={`question-${question.id}`}
          aria-labelledby={`question-${question.id}-text`}
          value={value}
          disabled={skipped}
          onChange={(event) => onWrite(event.target.value)}
          className="mt-2.5 min-h-24"
          placeholder="Add the architectural context that is not visible in the code…"
        />
      ) : null}

      <button
        type="button"
        aria-pressed={skipped}
        onClick={onToggleSkip}
        className={cn(
          // A line of text that is still a 44px target: the negative margin keeps the words
          // where they read best and lets the hit area be thumb-sized.
          "-ml-2.5 mt-1.5 inline-flex min-h-11 items-center rounded-sm px-2.5 text-xs font-semibold transition",
          skipped
            ? "bg-sunken text-ink"
            : "text-ink-3 hover:bg-sunken hover:text-ink",
        )}
      >
        {skipped ? "Skipped explicitly — undo" : "Skip explicitly"}
      </button>
    </div>
  );
}
