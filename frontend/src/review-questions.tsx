import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { ErrorPanel, Group } from "./components";
import {
  ANSWER_DRAFTS,
  draftsAreKept,
  dropDrafts,
  useQuestionDrafts,
} from "./question-drafts";
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
 * What is recorded is the pair: the question as the review asked it, and the answer as the
 * reader wrote it. This used to be one composed line — the question's subject welded to the
 * reply with a dash — because the case had five lists of sentences and nowhere to keep a pair.
 * The line existed for a real reason: a case entry is read with no question beside it, so "they
 * shouldn't rely on it" entered `assumptions` from a live run with its "it" referring to
 * nothing. Composing fixed that and paid for it twice. The reader was shown an answer that
 * restated the question directly above it, and the stages that re-judge the case were handed
 * the join instead of the question — so the one piece of context that made the reply legible
 * was the one thing they could never read.
 *
 * The case holds the pair now, which means nothing here composes anything. The reader types
 * their answer, sees it beside the question it answers, and that is what saves. Both halves
 * stay attributed: the question is shown as the review's, muted and labelled as such, and the
 * answer is theirs and editable to the last moment.
 *
 * What leaves here is the reference and the answer, and nothing that decides how it is
 * weighed. This used to compose the whole `CaseUpdate` — reading the pinned snapshot,
 * appending to the right lists, setting statement kinds — and then patch the case. The server
 * does that now, resolving each `Q-n` against the review's own report, because provenance a
 * client composes is provenance a client can omit: a revision written that way had silently
 * lost the link to the question that produced it. So this component no longer needs the case
 * at all, and no longer needs to know what a case field is for.
 *
 * It sits after the verdicts, never before them. A review that opens by asking for a better
 * case has put its price ahead of its value, which is the tax elicitation exists to remove.
 *
 * What is typed here is drafted to the browser as it is written (`question-drafts`), because
 * this is the one screen in the product where the reader supplies more than a click and the
 * work is theirs alone: a reload, a second tab, a citation followed and come back from used to
 * end with five empty boxes. There is deliberately no prompt on the way out, either — the
 * answers are still here when the reader returns, so a dialog asking them to confirm leaving
 * would be charging them for a loss that no longer happens.
 */

type CaseField = OpenQuestion["answer_belongs_in"];

/** One answer on its way to the workspace: which question, and what the reader typed. */
export type SubmittedAnswer = {
  question_reference: string;
  recorded_text: string;
};

/** The force an answer carries once it is in the case, said in the reader's terms. */
const FIELD_LABEL: Record<CaseField, string> = {
  expected_future_changes: "a change you expect",
  confirmed_facts: "something you know to be settled",
  technical_constraints: "something the design is bound by",
  non_goals: "something deliberately ruled out",
  assumptions: "something being taken on trust",
};

export function OpenQuestions({
  reviewId,
  questions,
  nextRevision,
  pending,
  disabled,
  error,
  onSubmit,
  renderCitations,
  renderDiscussion,
}: {
  /** The review these questions belong to, and the review its drafts are stored under. */
  reviewId: string;
  questions: OpenQuestion[];
  nextRevision: number | null;
  pending: boolean;
  /** True when the loop cannot be walked — the repository is no longer indexed. */
  disabled: boolean;
  error: unknown;
  /**
   * Record the answers. Resolves once the workspace has them, which is the moment the drafts
   * below stop being the only copy and are dropped.
   *
   * Deliberately a promise rather than a call whose outcome is inferred from `pending` falling
   * back to false: recording answers starts the second pass, and that navigates the reader to
   * the new review — so the render where the mutation settles frequently never arrives at this
   * component. A rejection leaves every draft where it is, because a save that failed is the
   * case the reader most needs their words back for.
   */
  onSubmit: (answers: SubmittedAnswer[]) => Promise<unknown>;
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
  // One piece of state, because there is one thing the reader writes. There used to be a
  // second — what they made of the line composed from their answer — and holding the two apart
  // was the whole cost of composing: an edit had to stick against recomposition, an adopted
  // suggestion had to clear it, and the box that saved was not the box they typed into.
  //
  // It is state that survives the page now. Every route into it is unchanged — this still
  // writes nothing the reader did not type — but a browser that is closed on a half-answered
  // review opens on the same half-answered review.
  const [answers, setAnswers] = useQuestionDrafts(ANSWER_DRAFTS, reviewId);
  // Asked once, on the way in: whether a draft is genuinely being kept is a property of the
  // browser, and it decides whether this screen may say so.
  const [kept] = useState(draftsAreKept);
  const answered = questions.filter((item) => (answers[item.reference] ?? "").trim());

  // Grouped by the force each answer carries, for the preview only. What is submitted is a
  // flat list keyed by question, because that force is the question's property and the server
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
      {/* The second sentence is conditional because it is a promise. In a browser that
          refuses storage there is no draft, and telling a reader their work is safe while it
          is not would be this page inventing a fact about their own machine — so the sentence
          is printed by the mechanism that keeps it, or not at all. It is also the reason
          leaving this page asks nothing: there is nothing to confirm the loss of. */}
      <p className="mb-3 max-w-[82ch] text-ui leading-[1.6] text-ink-2">
        The verdicts above rest on these. Answer what you know and leave the rest — the
        review carries on against what you write, and a verdict that turned on one of these
        can come out the other way.
        {kept
          ? " Nothing is recorded until you carry on, and what you write is kept in this browser until then — so you can go and check, or come back tomorrow."
          : null}
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
              spent a reader's attention to do it. It is still carried — it names what the
              question is about, which is what titles a discussion of it. */}
          <p className="mb-2 max-w-[78ch] text-body leading-[1.65] text-ink-2">
            {current.what_the_review_saw}
          </p>
          <p className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui leading-[1.6] text-ink-2">
            <span>{current.why_it_matters}</span>
            {renderCitations(current.supporting_references || [])}
          </p>
          {/* Offered answers, when the review could enumerate them. Pressing one is the
              reader's act — it fills the box below, still editable, and nothing is selected
              until they press. The box is the standing "other": a typed answer needs no
              option to exist, and an edited option stops matching and reads as their own.
              `aria-pressed` compares against the box, not a second piece of state, so the
              two can never disagree about what will be recorded. */}
          {(current.answer_options?.length ?? 0) > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Offered answers">
              {current.answer_options!.map((option) => {
                const taken = (answers[current.reference] ?? "").trim() === option;
                return (
                  <button
                    key={option}
                    type="button"
                    disabled={disabled || pending}
                    aria-pressed={taken}
                    className={cn(
                      "cursor-pointer rounded-pill border border-accent-rule bg-surface px-3 py-1.5",
                      "text-left text-ui leading-[1.4] text-ink hover:bg-accent-soft",
                      "aria-pressed:border-accent-ink aria-pressed:bg-accent-soft aria-pressed:text-accent-ink",
                      "disabled:cursor-not-allowed disabled:opacity-55",
                    )}
                    onClick={() => {
                      setAnswers((existing) => ({
                        ...existing,
                        // Pressing the taken one again empties the box: an offer can be
                        // declined, and the reader is back to their own words.
                        [current.reference]: taken ? "" : option,
                      }));
                      if (!taken) answerRef.current?.focus();
                    }}
                  >
                    {option}
                  </button>
                );
              })}
            </div>
          ) : null}
          {/* The box is the component. A question the reader cannot answer in place is a
              question that sends them somewhere else to find the right field. */}
          <label className="mt-2 block">
            <span className="mb-1 block text-meta text-ink-3 [&_code]:text-meta">
              {(current.answer_options?.length ?? 0) > 0
                ? "Or write your own — "
                : "Your answer — "}
              {FIELD_LABEL[current.answer_belongs_in]} (
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

      {/* Shown before it is saved, never after, and still editable here rather than
          read-only. Saving without the user seeing what enters their case is what §6C.4
          forbids, so this is what makes the button honest — and it is where someone who
          answered five questions in five separate screens reads back what they said as one
          thing.

          It shows the pair, because the pair is what is recorded. The question is the
          review's and is printed as it was asked; the answer is the reader's and stays in a
          box until the moment it saves. Nothing here restates the question in the reader's
          own words any more: that was the composed line, and it was the same sentence twice
          on one screen. */}
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
            Each answer is recorded beside the question it answers, so the next pass reads
            both — it sees the case and not this page. The question is the review's words;
            the answer is yours, and you can still change it here.
          </p>
          <ul className="m-0 pl-4 text-ui leading-[1.6] text-ink-2 [&_code]:text-meta [&_code]:text-accent-ink">
            {(Object.entries(previewGroups) as [CaseField, OpenQuestion[]][]).map(
              ([field, items]) => (
                <li key={field}>
                  <code>{field}</code>
                  <ul className="mt-[3px] mb-2 list-none pl-3">
                    {items.map((item) => (
                      // Laid out as "+ <question over box>" so it keeps reading as a diff:
                      // what is changing is one exchange being added to the case, and it
                      // should not start looking like a form.
                      <li
                        key={item.reference}
                        className="mb-2 grid grid-cols-[auto_1fr] items-start gap-x-2 gap-y-1"
                      >
                        <span aria-hidden className="pt-1 font-semibold text-accent-ink">
                          +
                        </span>
                        {/* Muted and attributed, because a reader has to be able to tell
                            which half of the pair is theirs. Nothing they type can reach
                            this line (invariant 25 read the other way round: the advisor's
                            question is not edited into the user's voice either). */}
                        <span className="text-meta leading-[1.5] text-ink-3">
                          Asked: {item.question}
                        </span>
                        <Textarea
                          rows={2}
                          className="col-start-2 min-h-0 px-2 py-1"
                          aria-label={`Your answer to ${item.reference}`}
                          disabled={disabled || pending}
                          value={answers[item.reference] ?? ""}
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [item.reference]: event.target.value,
                            }))
                          }
                        />
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

      {/* The one error surface this app has, rather than a coloured sentence that happened
          to be written here: an answer the server refused is refused for a reason it names,
          and the strip is what carries the server's own words everywhere else.

          No retry on it. The button directly below is the retry — it is still enabled, it
          still holds every answer that failed to save, and a second "Try again" a line above
          it would be the same press wearing a different word. */}
      {error ? (
        <ErrorPanel error={error} />
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
          const recording = answered.map((item) => ({
            question_reference: item.reference,
            recorded_text: (answers[item.reference] ?? "").trim(),
          }));
          onSubmit(recording).then(
            // Stored, so the draft has done its job and is dropped from the browser. Only the
            // drafts, though: the boxes keep what is in them while the second pass starts, and
            // blanking them under the reader would read as their words being thrown away at
            // the exact moment they were accepted.
            () =>
              dropDrafts(
                ANSWER_DRAFTS,
                reviewId,
                recording.map((pair) => pair.question_reference),
              ),
            // The failure is already on screen, from the `error` this component is given. What
            // it must not also do is forget the answers it failed to save.
            () => undefined,
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
