/** The Questions tab: what the run checked, what it still needs asked, and what was answered. */

import { cn } from "@/lib/utils";

import { phoneFlush, sheet } from "../../components";
import { InvestigationDisclosure } from "../../investigation-disclosure";
import { QuestionDiscussion } from "../../question-discussion";
import { Citations } from "../../review-ledger";
import { OpenQuestions, type SubmittedAnswer } from "../../review-questions";
import type {
  OpenQuestion,
  RecordedAnswer,
  ReviewDetail,
} from "../../types";

/**
 * The answers that produced this pass, beside the questions they answered.
 *
 * Read off the case revision this review is pinned to rather than recomposed: the workspace
 * recorded which question each answer answered, which is what makes the join possible at all.
 *
 * The answer prints as the reader typed it. It used to be a line composed from the question
 * and the reply, so this section showed the question and then most of it again underneath —
 * the case now keeps the pair, and what is quoted here is a person's own sentence.
 */
function AnsweredHistory({
  questions,
  answered,
  revision,
}: {
  questions: OpenQuestion[];
  answered: RecordedAnswer[];
  revision: number | undefined;
}) {
  const asked = new Map(questions.map((item) => [item.reference, item]));
  return (
    <section className={cn(sheet, "p-[var(--card-pad)]")} aria-label="Answers already recorded">
      <p className="mb-2 text-ui text-ink-2">
        {answered.length} {answered.length === 1 ? "answer" : "answers"} became case revision{" "}
        {revision ?? "?"}, which is what this pass judged against.
      </p>
      <ol className="m-0 grid list-none gap-3 p-0">
        {answered.map((item) => (
          // Ruled down the side rather than bulleted: each of these is a quotation of the
          // reader's own sentence, under the question it was given for.
          <li
            key={item.question_reference}
            className="grid gap-0.5 border-l-2 border-accent-rule pl-3"
          >
            <code className="text-micro tracking-[.07em] text-ink-3">
              {item.question_reference}
            </code>
            <span className="text-ui leading-[1.5] text-ink-3">
              {asked.get(item.question_reference)?.question ?? "The question it answered."}
            </span>
            <span className="text-ui leading-[1.55] text-ink">{item.recorded_text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function QuestionsTab({
  reviewId,
  investigation,
  holding,
  openQuestions,
  caseRevision,
  askedEarlier,
  answered,
  pending,
  disabled,
  error,
  onSubmit,
}: {
  reviewId: string;
  /** The run's own record of what it read before asking, where it kept one. */
  investigation: ReviewDetail["investigation"];
  holding: boolean;
  /** What this pass is asking, which is empty on a pass that concluded. */
  openQuestions: OpenQuestion[];
  caseRevision: number | undefined;
  /** The questions the asking pass put, which is where their wording lives. */
  askedEarlier: OpenQuestion[];
  answered: RecordedAnswer[];
  pending: boolean;
  /** True when the loop cannot be walked — the repository is no longer indexed. */
  disabled: boolean;
  error: unknown;
  onSubmit: (answers: SubmittedAnswer[]) => Promise<unknown>;
}) {
  const questions = (
    <OpenQuestions
      reviewId={reviewId}
      questions={openQuestions}
      nextRevision={caseRevision === undefined ? null : caseRevision + 1}
      // The run as well as the POST: the mutation settles the moment the answers are
      // recorded, but the reader is still on this page until the second pass announces
      // itself and navigation happens. A button that re-enabled in that stretch took a
      // second click against a case revision the first click had already advanced.
      pending={pending}
      disabled={disabled}
      error={error}
      // `mutateAsync` rather than `mutate`, so the surface hears that the workspace took the
      // answers rather than inferring it: it drops its drafts on that promise, and by the time
      // this mutation settles the run it started has usually navigated the reader away.
      // The rejection is handled there and the failure is rendered from `answer.error`.
      onSubmit={onSubmit}
      renderCitations={(citations) => <Citations references={citations} />}
      renderDiscussion={(question, adopt) => (
        <QuestionDiscussion
          reviewId={reviewId}
          question={question}
          onAdopt={adopt}
          disabled={disabled}
        />
      )}
    />
  );
  return (
    <>
      {/* Before the questions, because it is their warrant: each one is asked on
          the strength of the repository having been checked and stayed silent, and
          a concluded pass keeps the record for the same reason — what was checked
          is part of how the verdicts stood without asking. */}
      {investigation ? (
        <InvestigationDisclosure investigation={investigation} className={phoneFlush} />
      ) : null}
      {holding ? <div className={cn(sheet, "max-w-[96ch] p-[var(--card-pad)]")}>{questions}</div> : null}
      {answered.length > 0 ? (
        <AnsweredHistory
          questions={askedEarlier}
          answered={answered}
          revision={caseRevision}
        />
      ) : null}
    </>
  );
}
