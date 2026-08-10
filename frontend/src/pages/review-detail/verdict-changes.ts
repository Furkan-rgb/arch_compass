/** Which verdicts moved between two passes, and which answers moved them. */

import type { OpenQuestion, RecordedAnswer, ReviewedBoundary } from "../../types";

/**
 * What the reader's answers actually changed, read off the two passes.
 *
 * The single most persuasive thing this flow can show, and it costs no model call: both
 * reviews are stored, both judged the same atlas, and the only difference between them is
 * what the case says. A verdict that moved is therefore attributable to the answer and to
 * nothing else — which is the claim elicitation makes, put in front of the person who just
 * did the work.
 *
 * Matched by reference, which is safe precisely because detection is deterministic: the same
 * atlas gives the same boundary the same `BR-nnn` in both passes.
 */
export function verdictChanges(
  before: ReviewedBoundary[],
  after: ReviewedBoundary[],
): { reference: string; title: string; from: boolean; to: boolean }[] {
  const previous = new Map(before.map((item) => [item.reference, item]));
  return after.flatMap((item) => {
    const earlier = previous.get(item.reference);
    if (!earlier || earlier.material === item.material) return [];
    return [
      {
        reference: item.reference,
        title: item.candidate.participants[0]?.qualified_name ?? item.candidate.summary,
        from: earlier.material,
        to: item.material,
      },
    ];
  });
}

/**
 * Which of the reader's answers a boundary's verdict rested on.
 *
 * A question names the boundaries it would settle, and the revision names the questions it
 * answered, so the join is already recorded on both sides and nothing here has to guess. It
 * is the reason the provenance was worth storing: without it a second pass can say four
 * verdicts moved, and cannot say which sentence moved any one of them.
 *
 * A changed verdict may have several answers behind it and may have none — a boundary can
 * move because a question about a *different* boundary changed what the case says overall.
 * Both are reported as what they are rather than forced into a single cause.
 */
export function answersBehind(
  reference: string,
  questions: OpenQuestion[],
  answered: RecordedAnswer[],
): { question: string; recordedText: string }[] {
  const recorded = new Map(answered.map((item) => [item.question_reference, item]));
  return questions.flatMap((question) => {
    if (!(question.supporting_references || []).includes(reference)) return [];
    const answer = recorded.get(question.reference);
    if (!answer) return [];
    return [{ question: question.question, recordedText: answer.recorded_text }];
  });
}
