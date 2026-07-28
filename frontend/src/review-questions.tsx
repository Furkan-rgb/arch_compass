import { useState } from "react";

import type { ArchitectureCase, CaseUpdate, OpenQuestion } from "./types";

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
 * It sits after the verdicts, never before them. A review that opens by asking for a better
 * case has put its price ahead of its value, which is the tax elicitation exists to remove.
 */

type CaseField = OpenQuestion["answer_belongs_in"];

/** Which case list an answer joins, and how it reads once it is in there. */
const FIELD_LABEL: Record<CaseField, string> = {
  expected_future_changes: "a change you expect",
  confirmed_facts: "something you know to be settled",
  technical_constraints: "something the design is bound by",
  non_goals: "something deliberately ruled out",
  assumptions: "something being taken on trust",
};

/** The two fields whose entries are statements rather than plain lines. */
const STATEMENT_KIND = {
  confirmed_facts: "fact",
  assumptions: "assumption",
} as const;

const PLAIN_FIELDS = [
  "expected_future_changes",
  "technical_constraints",
  "non_goals",
] as const;

/**
 * The revision an answered set would produce: the case as the review saw it, plus what was
 * written, and nothing else touched.
 *
 * Only answered fields appear. A `CaseUpdate` leaves an absent field alone, so a reader who
 * answers one of five questions cannot silently rewrite the other four lists — which is what
 * submitting the whole case form does, and the reason this composes an update rather than
 * reusing it.
 */
export function composeAnswerUpdate(
  snapshot: ArchitectureCase,
  grouped: Partial<Record<CaseField, string[]>>,
): CaseUpdate {
  const update: CaseUpdate = {};
  for (const field of PLAIN_FIELDS) {
    const added = grouped[field]?.filter((text) => text.trim());
    if (added?.length) {
      update[field] = [...(snapshot[field] ?? []), ...added.map((text) => text.trim())];
    }
  }
  for (const [field, kind] of Object.entries(STATEMENT_KIND) as [
    keyof typeof STATEMENT_KIND,
    (typeof STATEMENT_KIND)[keyof typeof STATEMENT_KIND],
  ][]) {
    const added = grouped[field]?.filter((text) => text.trim());
    if (added?.length) {
      update[field] = [
        ...(snapshot[field] ?? []),
        // The kind is fixed by which list the statement joins, so it is set here rather
        // than asked for — the same reasoning the case form applies.
        ...added.map((text) => ({ text: text.trim(), kind })),
      ];
    }
  }
  return update;
}

/** Answers keyed by question, regrouped by the case field each one belongs in. */
export function groupByField(
  questions: OpenQuestion[],
  answers: Record<string, string>,
): Partial<Record<CaseField, string[]>> {
  const grouped: Partial<Record<CaseField, string[]>> = {};
  for (const question of questions) {
    const text = (answers[question.reference] ?? "").trim();
    if (!text) continue;
    const field = question.answer_belongs_in;
    grouped[field] = [...(grouped[field] ?? []), text];
  }
  return grouped;
}

export function OpenQuestions({
  questions,
  snapshot,
  nextRevision,
  pending,
  disabled,
  error,
  onSubmit,
  renderCitations,
}: {
  questions: OpenQuestion[];
  /** The case as this review saw it. Absent while it is still loading. */
  snapshot: ArchitectureCase | undefined;
  nextRevision: number | null;
  pending: boolean;
  /** True when the loop cannot be walked — the repository is no longer indexed. */
  disabled: boolean;
  error: unknown;
  onSubmit: (update: CaseUpdate) => void;
  renderCitations: (references: string[]) => React.ReactNode;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const grouped = groupByField(questions, answers);
  const answered = questions.filter((item) => (answers[item.reference] ?? "").trim());
  const canSubmit = Boolean(snapshot) && answered.length > 0 && !pending && !disabled;

  return (
    <div className="overview__group questions">
      <h3>What the case does not say</h3>
      <p className="questions__lead">
        Each of these would settle verdicts above. Answer what you know and leave the rest —
        what you write becomes a new revision of the case, and a review against it can reach
        a different verdict.
      </p>

      <ol className="questions__list">
        {questions.map((item) => (
          <li key={item.reference} className="question">
            <p className="question__ask">
              <code className="question__ref">{item.reference}</code>
              {item.question}
            </p>
            <p className="question__unknown">{item.unknown}</p>
            <p className="question__why">
              <span>{item.why_it_matters}</span>
              {renderCitations(item.supporting_references || [])}
            </p>
            <label className="question__answer-field">
              <span className="question__target">
                Your answer — {FIELD_LABEL[item.answer_belongs_in]} (
                <code>{item.answer_belongs_in}</code>)
              </span>
              <textarea
                rows={2}
                disabled={disabled || pending}
                value={answers[item.reference] ?? ""}
                placeholder={disabled ? "" : "Leave blank to skip this one."}
                onChange={(event) =>
                  setAnswers((current) => ({
                    ...current,
                    [item.reference]: event.target.value,
                  }))
                }
              />
            </label>
          </li>
        ))}
      </ol>

      {/* Shown before it is saved, never after. Pre-filling from a question is allowed and
          saving without the user seeing what enters their case is not, so the diff is the
          thing that makes the button honest rather than a courtesy. */}
      {answered.length > 0 ? (
        <div className="questions__preview">
          <p className="questions__preview-head">
            {answered.length} of {questions.length} answered. Revision{" "}
            {nextRevision ?? "?"} will add:
          </p>
          <ul>
            {(Object.entries(grouped) as [CaseField, string[]][]).map(([field, texts]) => (
              <li key={field}>
                <code>{field}</code>
                <ul>
                  {texts.map((text) => (
                    <li key={text}>+ {text}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          <p className="questions__preview-note">
            This does not change the review you are reading. Both reviews stay, each pinned
            to the case revision it ran against.
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="questions__error">
          {error instanceof Error ? error.message : "The answer could not be saved."}
        </p>
      ) : null}

      <button
        type="button"
        className="button button--primary questions__submit"
        disabled={!canSubmit}
        title={
          disabled
            ? "The repository this review ran against is no longer indexed."
            : undefined
        }
        onClick={() => {
          if (!snapshot) return;
          onSubmit(composeAnswerUpdate(snapshot, grouped));
        }}
      >
        {pending
          ? "Reviewing…"
          : answered.length === 0
            ? "Answer at least one to continue"
            : `Save revision & review again`}
      </button>
    </div>
  );
}
