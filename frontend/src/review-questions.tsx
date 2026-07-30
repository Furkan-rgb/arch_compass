import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { Group } from "./components";
import type { OpenQuestion } from "./types";

/* One step of the walk. A square the size of a control, holding a number that has to line
   up down the row — so the numerals are tabular and the box has a floor rather than a
   width. Answered is filled; the one you are on is ringed twice, because "where am I" and
   "what have I done" are two different questions being asked of the same row. */
const step =
  "h-7 min-w-7 cursor-pointer rounded-control border border-rule bg-transparent px-2 text-ui tabular-nums text-ink-3";
const stepIdle = "hover:border-accent-rule hover:text-ink-2";
const stepAnswered = "border-accent-rule bg-accent-soft text-accent-ink";
const stepCurrent =
  "border-accent-ink font-semibold text-accent-ink shadow-[inset_0_0_0_1px_var(--accent-ink)]";

/**
 * The questions a review asks, and the box each answer is written into.
 *
 * The advisor supplies the question; the user supplies the answer; only the answer enters
 * the case, and only as a revision they have seen (master plan §6C.4, invariant 25). This
 * component is that rule made walkable: it never writes an answer, never pre-fills one, and
 * never saves without showing what is about to be added.
 *
 * Answers batch into one revision rather than saving as they are typed. A person reading a
 * review answers what they know and skips what they do not, and each of those answers is
 * part of the same act of correcting the record — six revisions for six sentences would make
 * the history unreadable and re-run the review five times more than anyone wanted.
 *
 * What is recorded is the answer joined to the circumstance it settles, not the answer
 * alone. A reply is written against a question that is on screen and reads perfectly there;
 * the case keeps only the reply, and nothing downstream ever sees the question again. "They
 * shouldn't rely on it" entered `assumptions` from a live run and its "it" refers to nothing
 * — not for the second pass, which judges against the case snapshot alone, and not for a
 * person reading their own case a month later. §6C.4 allows exactly this repair: pre-filling
 * from the question is permitted, saving something the user has not seen is not. So the
 * joined line is composed here, shown in the preview, and editable there before it saves.
 *
 * What leaves here is the reference and the line, and nothing that decides where it goes.
 * This used to compose the whole `CaseUpdate` — reading the pinned snapshot, appending to the
 * right lists, setting statement kinds — and then patch the case. The server does that now,
 * resolving each `Q-n` against the review's own report, because provenance a client composes
 * is provenance a client can omit: a revision written that way had silently lost the link to
 * the question that produced it. So this component no longer needs the case at all.
 *
 * It sits after the verdicts, never before them. A review that opens by asking for a better
 * case has put its price ahead of its value, which is the tax elicitation exists to remove.
 */

type CaseField = OpenQuestion["answer_belongs_in"];

/** One answer on its way to the workspace: which question, and the line the reader saw. */
export type SubmittedAnswer = {
  question_reference: string;
  recorded_text: string;
};

/** Which case list an answer joins, and how it reads once it is in there. */
const FIELD_LABEL: Record<CaseField, string> = {
  expected_future_changes: "a change you expect",
  confirmed_facts: "something you know to be settled",
  technical_constraints: "something the design is bound by",
  non_goals: "something deliberately ruled out",
  assumptions: "something being taken on trust",
};

/**
 * The answer joined to the circumstance it settles, as one line that stands on its own.
 *
 * A case entry is read with no question beside it — by the second pass, which judges against
 * the case snapshot and nothing else, by every later review, and by whoever opens the case
 * editor. So the subject has to be in the sentence. `unknown` is the review's own statement
 * of the circumstance the case does not settle ("whether a second sink implementation is
 * intended"), which makes it the one phrase already written to be the subject of this line.
 *
 * Deterministic, and no model is asked. Text a model wrote into a case unseen is what
 * invariant 25 exists to prevent, and a rephrasing call would be exactly that with a nicer
 * result. This composes; the reader edits. Grammar is left alone rather than guessed at —
 * lowercasing the answer's first word would damage `SQLite` and `BUILT_IN_VOICES`, which is
 * worse than a capital letter after a dash, and the box in the preview is right there.
 */
export function composeCaseLine(question: OpenQuestion, answer: string): string {
  const written = answer.trim();
  if (!written) return "";
  const subject = question.unknown.trim().replace(/[.?;:,\s]+$/, "");
  if (!subject) return written;
  const opening = subject.charAt(0).toUpperCase() + subject.slice(1);
  const joined = `${opening} — ${written}`;
  return /[.!?]$/.test(joined) ? joined : `${joined}.`;
}

export function OpenQuestions({
  questions,
  nextRevision,
  pending,
  disabled,
  error,
  onSubmit,
  renderCitations,
  renderDiscussion,
}: {
  questions: OpenQuestion[];
  nextRevision: number | null;
  pending: boolean;
  /** True when the loop cannot be walked — the repository is no longer indexed. */
  disabled: boolean;
  error: unknown;
  onSubmit: (answers: SubmittedAnswer[]) => void;
  renderCitations: (references: string[]) => React.ReactNode;
  /**
   * The per-question discussion, supplied rather than built here so this component stays
   * free of data fetching and testable without a query client. `adopt` fills the answer
   * box; nothing the discussion returns reaches the case by any other route.
   */
  renderDiscussion?: (
    question: OpenQuestion,
    adopt: (text: string) => void,
  ) => React.ReactNode;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // What the reader typed, and separately what they made of the line composed from it. An
  // edit sticks rather than being recomposed on the next keystroke — the line is theirs once
  // they touch it — which is why the two are held apart instead of one being derived.
  const [edits, setEdits] = useState<Record<string, string>>({});
  const answered = questions.filter((item) => (answers[item.reference] ?? "").trim());

  const lineFor = (question: OpenQuestion): string => {
    const written = (answers[question.reference] ?? "").trim();
    if (!written) return "";
    return edits[question.reference] ?? composeCaseLine(question, written);
  };

  const lines = Object.fromEntries(
    questions.map((item) => [item.reference, lineFor(item)]),
  );
  // Grouped by destination for the preview only. What is submitted is a flat list keyed by
  // question, because which list an answer joins is the question's property and the server
  // reads it from the review rather than taking this component's word for it.
  const previewGroups = answered.reduce<Partial<Record<CaseField, OpenQuestion[]>>>(
    (groups, item) => ({
      ...groups,
      [item.answer_belongs_in]: [...(groups[item.answer_belongs_in] ?? []), item],
    }),
    {},
  );
  const canSubmit = answered.length > 0 && !pending && !disabled;

  // One question on screen, and a last step that is the preview. Not a scroll of five
  // cards: each of these takes real thought about the reader's own project, and five at
  // once is read as a form to get through rather than five separate decisions. Nothing is
  // gated behind anything — every step is reachable from the row of numbers, and an answer
  // stays exactly as typed while they move around, because revisiting is the point.
  const reviewStep = questions.length;
  const [at, setAt] = useState(0);
  const current = at < reviewStep ? questions[at] : undefined;

  /**
   * The answer box takes focus as this screen arrives, and again on each question.
   *
   * A frame late rather than declared with `autoFocus`, because the tab strip changes
   * section on mousedown and the browser focuses the tab it was pressed on *after* that
   * handler returns — so a box focused during the same commit is focused and then
   * immediately un-focused. One frame later is the only place this can win. The box is
   * the whole of what there is to do here, so arriving with the cursor anywhere else is
   * asking the reader to go and find it.
   */
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const asking = current?.reference;
  useEffect(() => {
    if (!asking) return;
    const frame = requestAnimationFrame(() => answerRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [asking]);

  return (
    // The questions read as an invitation, not as a defect: they are what the reader can do
    // to sharpen the verdicts above, so this whole block carries the accent rather than the
    // warning colour.
    //
    // "What it needs to know", not "what the case does not say": most runs start with
    // nothing written down, so naming a gap in a case reads as the reader's omission when
    // it is the advisor asking for what would settle its own verdicts.
    <Group label="What it needs to know">
      <p className="mb-3 max-w-[82ch] text-ui leading-[1.6] text-ink-2">
        The verdicts above rest on these. Answer what you know and leave the rest — the
        review carries on against what you write, and a verdict that turned on one of these
        can come out the other way.
      </p>

      {/* One question at a time, with every step reachable from this row. Numbered rather
          than dotted: a reader who wants to change what they said about the second one
          should be able to go straight to it, and a dot gives them nothing to aim at.
          Answered steps are filled, so "what have I not done" is legible without counting. */}
      <nav
        className="mb-3 flex max-w-[82ch] flex-wrap items-center gap-1"
        aria-label="Questions"
      >
        {questions.map((item, index) => (
          <button
            key={item.reference}
            type="button"
            className={cn(
              step,
              (answers[item.reference] ?? "").trim() && stepAnswered,
              index === at ? stepCurrent : stepIdle,
            )}
            aria-current={index === at ? "step" : undefined}
            aria-label={`Question ${index + 1} of ${questions.length}${
              (answers[item.reference] ?? "").trim() ? ", answered" : ", not answered"
            }`}
            title={item.question}
            onClick={() => setAt(index)}
          >
            {index + 1}
          </button>
        ))}
        <button
          type="button"
          className={cn(step, "min-w-0", at === reviewStep ? stepCurrent : stepIdle)}
          aria-current={at === reviewStep ? "step" : undefined}
          onClick={() => setAt(reviewStep)}
        >
          Review
        </button>
        <span className="ml-auto text-meta text-ink-3">
          {answered.length} of {questions.length} answered
        </span>
      </nav>

      {current ? (
        <div
          className="max-w-[82ch] rounded-panel border border-accent-rule bg-accent-soft p-[var(--card-pad)]"
          key={current.reference}
        >
          <p className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-read leading-[1.5] font-semibold">
            <code className="rounded-pill border border-accent-rule bg-surface px-2 py-px font-mono text-meta font-normal tracking-[.04em] text-accent-ink">
              {current.reference}
            </code>
            {current.question}
          </p>
          {/* What was seen, not the question with its question mark removed. `unknown` is
              no longer shown as prose: it said the same thing as the line above it and
              spent a reader's attention to do it. It is still carried, and it is what the
              recorded case line is composed from — a subject, not a description. */}
          <p className="mb-2 max-w-[78ch] text-body leading-[1.65] text-ink-2">
            {current.what_the_review_saw}
          </p>
          <p className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui leading-[1.6] text-ink-2">
            <span>{current.why_it_matters}</span>
            {renderCitations(current.supporting_references || [])}
          </p>
          {/* The box is the component. A question the reader cannot answer in place is a
              question that sends them somewhere else to find the right field. */}
          <label className="mt-2 block">
            <span className="mb-1 block text-meta text-ink-3 [&_code]:text-meta">
              Your answer — {FIELD_LABEL[current.answer_belongs_in]} (
              <code>{current.answer_belongs_in}</code>)
            </span>
            <Textarea
              ref={answerRef}
              rows={3}
              className="text-body"
              disabled={disabled || pending}
              value={answers[current.reference] ?? ""}
              placeholder={disabled ? "" : "Leave blank to skip this one."}
              onChange={(event) => {
                const { value } = event.target;
                setAnswers((existing) => ({
                  ...existing,
                  [current.reference]: value,
                }));
              }}
            />
          </label>
          {/* Below the box, not above it. Someone who knows their answer should be able to
              type it and move on without reading past an invitation to discuss it first. */}
          {renderDiscussion?.(current, (text) => {
            setAnswers((existing) => ({ ...existing, [current.reference]: text }));
            // A suggestion adopted after the composed line was edited would otherwise be
            // invisible — the old edit would still be what saves. The reader changed their
            // answer, so the line composed from it is the one to show them again.
            setEdits(({ [current.reference]: _replaced, ...rest }) => rest);
          })}
        </div>
      ) : null}

      <div className="mt-3 flex max-w-[82ch] gap-2 [&_[data-slot=button]]:text-ui">
        <Button
          type="button"
          disabled={at === 0}
          onClick={() => setAt((position) => Math.max(0, position - 1))}
        >
          Back
        </Button>
        <Button
          type="button"
          disabled={at >= reviewStep}
          onClick={() => setAt((position) => Math.min(reviewStep, position + 1))}
        >
          {at === reviewStep - 1 ? "Review what will be recorded" : "Next question"}
        </Button>
      </div>

      {/* Shown before it is saved, never after, and editable here rather than read-only.
          Pre-filling from a question is allowed and saving without the user seeing what
          enters their case is not, so the diff is what makes the button honest — and once
          the line being saved is composed rather than typed verbatim, showing it is not
          enough on its own. The reader has to be able to correct it. */}
      {at === reviewStep && answered.length > 0 ? (
        <div
          data-slot="answer-preview"
          className="mt-4 rounded-panel border border-dashed border-accent-rule bg-surface p-[var(--card-pad)]"
        >
          <p className="mb-2 text-ui font-semibold text-ink-2">
            {answered.length} of {questions.length} answered. Carrying on will record
            revision {nextRevision ?? "?"} of the case, adding:
          </p>
          <p className="mb-2 max-w-[76ch] text-ui leading-[1.55] text-ink-3">
            Each line joins your answer to what it settles, so it still means something read
            on its own — in the case editor, and to the next pass, which sees the case and
            not these questions. Edit any of them.
          </p>
          <ul className="m-0 pl-4 text-ui leading-[1.6] text-ink-2 [&_code]:text-meta [&_code]:text-accent-ink">
            {(Object.entries(previewGroups) as [CaseField, OpenQuestion[]][]).map(
              ([field, items]) => (
                <li key={field}>
                  <code>{field}</code>
                  <ul className="mt-[3px] mb-2 list-none pl-3">
                    {items.map((item) => (
                      // Laid out as "+ <box>" so it keeps reading as a diff: what is
                      // changing is still one line being added to one list, and it should
                      // not start looking like a form.
                      <li
                        key={item.reference}
                        className="mb-2 grid grid-cols-[auto_1fr] items-start gap-x-2 gap-y-1"
                      >
                        <span aria-hidden className="pt-1 font-semibold text-accent-ink">
                          +
                        </span>
                        <Textarea
                          rows={2}
                          className="min-h-0 px-2 py-1"
                          aria-label={`What ${item.reference} adds to ${field}`}
                          disabled={disabled || pending}
                          value={lines[item.reference] ?? ""}
                          onChange={(event) =>
                            setEdits((current) => ({
                              ...current,
                              [item.reference]: event.target.value,
                            }))
                          }
                        />
                        {edits[item.reference] !== undefined ? (
                          <button
                            type="button"
                            className="col-start-2 cursor-pointer justify-self-start border-0 bg-transparent p-0 text-meta text-ink-3 underline not-disabled:hover:text-ink-2"
                            disabled={disabled || pending}
                            onClick={() =>
                              setEdits(({ [item.reference]: _dropped, ...rest }) => rest)
                            }
                          >
                            Reset to suggested
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </li>
              ),
            )}
          </ul>
          <p className="mt-2 text-meta leading-[1.55] text-ink-3">
            The review you are reading is kept as it stands. Carrying on judges the same
            boundaries again against the answered case, and both passes remain readable —
            each pinned to the case revision it ran against, so you can see what your answer
            changed.
          </p>
        </div>
      ) : null}

      {at === reviewStep && answered.length === 0 ? (
        <p className="mt-4 max-w-[78ch] text-ui leading-[1.6] text-ink-3">
          Nothing is answered yet, so there is nothing to record. Go back to any question
          above — answering one is enough to carry on, and skipping the rest is a normal way
          to use this.
        </p>
      ) : null}

      {error ? (
        <p className="mt-3 text-ui text-danger">
          {error instanceof Error ? error.message : "The answer could not be saved."}
        </p>
      ) : null}

      {/* Only on the last step. Submitting is the one thing here that cannot be revisited,
          so it does not sit under a question the reader is still in the middle of. */}
      <Button
        type="button"
        variant="primary"
        className="mt-3"
        hidden={at !== reviewStep}
        disabled={!canSubmit}
        title={
          disabled
            ? "The repository this review ran against is no longer indexed."
            : undefined
        }
        onClick={() => {
          onSubmit(
            answered.map((item) => ({
              question_reference: item.reference,
              recorded_text: lines[item.reference] ?? "",
            })),
          );
        }}
      >
        {pending
          ? "Carrying on…"
          : answered.length === 0
            ? "Answer at least one to continue"
            : answered.length === questions.length
              ? "Continue the review"
              : `Continue with ${answered.length} of ${questions.length} answered`}
      </Button>
    </Group>
  );
}
