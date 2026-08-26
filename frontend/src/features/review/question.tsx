import { useEffect, useRef, type ReactNode } from "react";

import type { Finding, Question, Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { ToggleButton } from "../../ui/button";
import { Textarea } from "../../ui/field";
import { Mono } from "../../ui/meta";
import { QuestionHelp } from "./question-help";

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
        checked
          ? "border-rule-strong bg-sunken text-ink"
          : "border-rule bg-surface-2 text-ink hover:border-rule-strong",
        // An off option is drawn off, not faded. `opacity-50` composites the row and its
        // words together toward whatever is behind them, which took the text of a skipped
        // question's options to about 2:1 and manufactured a grey belonging to no ramp — and
        // it sat *before* the checked branch, so half of what it set was overwritten anyway.
        // The control film with meta ink says the same thing at a measured contrast.
        disabled && "cursor-not-allowed border-rule-control bg-control text-ink-3",
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
  review,
  value,
  writingOwn,
  skipped,
  asking,
  helpOpen,
  onChoose,
  onWriteOwn,
  onWrite,
  onAsking,
  onHelpOpen,
  onUseDraft,
  onToggleSkip,
  className,
}: {
  question: Question;
  /** The findings this question was raised against, resolved by the round. */
  affected: Finding[];
  /** The whole snapshot, because the help panel's agent answers about this review. */
  review: Review;
  value: string;
  /** The reviewer has said none of the proposals fit; the box is theirs. */
  writingOwn: boolean;
  skipped: boolean;
  /** What is half-typed into the help panel, held by the page rather than by this. */
  asking: string;
  /** Whether the help panel is open, held by the page for the same reason `asking` is. */
  helpOpen: boolean;
  onChoose: (option: string) => void;
  onWriteOwn: () => void;
  onWrite: (value: string) => void;
  onAsking: (value: string) => void;
  onHelpOpen: (open: boolean) => void;
  /** Wording the reviewer took from the agent, with the model that wrote it. */
  onUseDraft: (text: string, model: string) => void;
  onToggleSkip: () => void;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);

  // The qualified name where a candidate has one, and its sentence where it does not — the
  // same fallback the single name used, applied to all of them.
  const names = affected.map(
    (finding) =>
      finding.candidate.participants[0]?.qualified_name ?? finding.candidate.summary,
  );

  /**
   * Follow the box when it appears with words already in it.
   *
   * *Put this in my answer* writes into a box that is above the button in the DOM and does not
   * yet exist, so pressing it mounted a hundred pixels of textarea between the question and
   * the help panel: the panel and the button under the cursor dropped, and nothing said the
   * wording had landed anywhere. `nearest` so a box already on screen is left exactly where it
   * is — the same rule the round uses when it opens the next row.
   *
   * Only where the box arrives filled. Reaching for it by choosing *Something else* empties
   * the value on purpose, and scrolling to an empty box somebody just asked for would be the
   * page moving for no reason.
   */
  const arrivedFilled = (!question.options.length || writingOwn) && Boolean(value);
  useEffect(() => {
    if (!arrivedFilled) return;
    box.current?.scrollIntoView?.({ block: "nearest" });
    // Deliberately keyed on the box appearing rather than on the value, or every keystroke
    // in a long answer would scroll the page a little.
  }, [arrivedFilled]);

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
            here is allowed to unmount it.

            Three names, not one. It named the first and counted the rest — "Affects X and 3
            others" — and whether an answer is safe depends on what it will be applied to, so
            a reviewer with four affected candidates could see a quarter of the question they
            were being asked. Three is where a row of qualified names stops being scannable;
            past that the whole list is on the hover and in the accessible name, which is the
            device the docket's group headings already use for the same reason. */}
        <span
          title={affected.length > 3 ? names.join("\n") : undefined}
          className="min-w-0 text-xs text-ink-3 wrap-anywhere"
        >
          {names.length ? (
            <>
              Affects{" "}
              {names.slice(0, 3).map((name, index) => (
                <span key={name}>
                  {index ? ", " : ""}
                  <Mono className="text-ink-2">{name}</Mono>
                </span>
              ))}
              {names.length > 3 ? ` and ${plural(names.length - 3, "other")}` : ""}
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
        /* `animate-expand` on the wrapper, because this box regularly appears under a press
           somewhere else — *Put this in my answer*, in the panel below it — and an element a
           hundred pixels tall arriving in one frame reads as the page jumping rather than as
           the box opening. The ref is on the wrapper for the same reason: `Textarea` is a
           shared control that forwards no ref, and growing its props to satisfy one call site
           would put a scroll target on every field in the product.

           `min-h-32 field-sizing-content max-h-64` rather than the shared `min-h-24` floor.
           This is the field the charter's whole ask-rather-than-assume loop funnels into and
           its placeholder asks for a paragraph, which is not what four lines and a resize
           corner are for. It grows with what is typed where the browser supports
           `field-sizing`, and is exactly what shipped before where it does not. The floor in
           `ui/field.tsx` is left where it is: every other textarea in the product inherits
           it, including the policy editor's body. */
        <div ref={box} className="animate-expand">
          <Textarea
            id={`question-${question.id}`}
            aria-labelledby={`question-${question.id}-text`}
            value={value}
            disabled={skipped}
            onChange={(event) => onWrite(event.target.value)}
            className="mt-2.5 max-h-64 min-h-32 field-sizing-content"
            placeholder="Add the architectural context that is not visible in the code…"
          />
        </div>
      ) : null}

      {/* Below every way of answering and above the skip, which is where it belongs in the
          order somebody actually works: pick one, write one, work out what is being asked,
          or say you cannot. Putting it above the options would offer help before the reader
          knew whether they needed any. */}
      <QuestionHelp
        question={question}
        review={review}
        draft={asking}
        open={helpOpen}
        onDraft={onAsking}
        onOpenChange={onHelpOpen}
        onUseAnswer={onUseDraft}
      />

      {/* The shared toggle rather than a hand-rolled one, because the hand-rolled one had the
          state backwards twice over: pressed was a fill on an inset token with no border —
          the invert-on-press pattern the design system replaced across the product — and the
          *unpressed* hover painted that same `bg-sunken`, so pointing at "Skip explicitly"
          made it look exactly like a question already skipped, with only the word to tell
          them apart. `ToggleButton` carries the state on an edge appearing. `min-h-11` keeps
          the 44px target the negative margin was written for on a fine pointer too. */}
      <ToggleButton
        pressed={skipped}
        onClick={onToggleSkip}
        className="-ml-2.5 mt-1.5 min-h-11"
      >
        {skipped ? "Skipped explicitly — undo" : "Skip explicitly"}
      </ToggleButton>
    </div>
  );
}
