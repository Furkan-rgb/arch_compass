import { Eye, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

import type { ReviewedBoundary } from "./types";

/**
 * A review that judged everything and is now waiting on a person.
 *
 * Not a results page, and deliberately not a shorter one. Every boundary here has a verdict
 * and those verdicts are stored — what is withheld is presenting them as findings, because
 * they are not yet findings. Measured on the bundled `warehouse-sync` example, four of five
 * first-pass verdicts moved once the questions below were answered, so a page that led with
 * them would be leading with conclusions more likely wrong than right, in the same confident
 * marks a settled verdict wears.
 *
 * What the page still shows is the shape of what was done — how many boundaries, how many
 * verdicts rested on something unstated — because that is what makes the questions worth
 * answering. A page that asked for information while saying nothing about what it had found
 * would be charging the reader before showing them anything, which is the adoption tax
 * elicitation exists to remove. That is the verdict band's job now, and it prints how far the
 * run got rather than how it went.
 *
 * And there is a way past it. Someone reviewing unfamiliar code may genuinely not know
 * whether a second vendor is coming, and "answer my questions or you get nothing" is the
 * same tax in a new shape. Revealing does not resolve anything: the record still says
 * `awaiting_answers`, because nobody answered, and every verdict shown is labelled for what
 * it is. The questions are a strong default, not a gate.
 */

/** How many of these verdicts said outright that they turn on something unstated. */
export function contingentCount(reviewed: ReviewedBoundary[]): number {
  return reviewed.filter((item) => item.hinge).length;
}

/**
 * The hold itself, above everything the review has to say.
 *
 * A banner rather than a tab, because holding is the review's state and not one of its
 * sections: a reader who arrives at a held review has exactly one thing to do, and the
 * button that does it is on the banner.
 */
export function HoldBanner({
  questionCount,
  nextRevision,
  onAnswer,
}: {
  questionCount: number;
  /** The revision the answers will become, where the case is known. */
  nextRevision: number | null;
  onAnswer: () => void;
}) {
  return (
    // Ruled down its left edge in the revision hue, the same mark a verdict that should
    // change wears: this is the review saying it cannot finish, not a note about it.
    <div
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-control border border-material-rule border-l-[3px] border-l-material bg-material-soft px-4 py-2"
      role="status"
    >
      <b className="text-ui text-material">Holding</b>
      <p className="m-0 flex-[1_1_32ch] text-meta leading-[1.5] text-ink-2">
        {questionCount === 1
          ? "One question needs an answer — it could not"
          : `${questionCount} questions need answers — they could not`}{" "}
        be weighed from the code alone. The run resumes the moment{" "}
        {questionCount === 1 ? "it is" : "they are"} answered, and your answers become
        {nextRevision === null ? " the next revision" : ` case revision ${nextRevision}`} of
        the case.
      </p>
      <Button type="button" variant="primary" onClick={onAnswer}>
        {questionCount === 1 ? "Answer 1 question" : `Answer ${questionCount} questions`}
      </Button>
    </div>
  );
}

/**
 * The verdicts a held review has reached, behind the reveal that says what they are.
 *
 * Last, small, and honest about what it costs. Not hidden — someone who cannot answer has to
 * be able to get something — but not offered as an equal path either, because on the example
 * this flow was measured against four of five of these moved once the questions were
 * answered.
 */
export function HeldVerdicts({
  reviewed,
  findings,
}: {
  reviewed: ReviewedBoundary[];
  /** The ledger, rendered only once the reader has asked to see it. */
  findings: ReactNode;
}) {
  const [revealed, setRevealed] = useState(false);

  return (
    <section className="mb-3 grid gap-3">
      {revealed ? (
        <>
          <p className="m-0 flex items-start gap-2 rounded-panel border border-material-rule bg-material-soft px-4 py-3 text-body leading-[1.65] text-ink-2 [&>svg]:mt-[3px] [&>svg]:flex-none">
            <TriangleAlert size={15} aria-hidden />
            <span className="max-w-[92ch]">
              <strong>These verdicts are provisional.</strong> They were reached against a
              case that does not yet say what the questions ask about. On the example this
              flow was measured against, four of five verdicts came out differently once
              those questions were answered — and the one that did not move was not
              predictable in advance. Read them as what the review currently supposes, not as
              what it concludes.
            </span>
          </p>
          {findings}
        </>
      ) : (
        <>
          {/* A plain control, not a primary one: it has to be available — someone reviewing
              unfamiliar code may genuinely not be able to answer — without reading as the
              equal alternative to answering, which the measurements say it is not. */}
          <Button
            type="button"
            className="justify-self-start text-ink-2"
            onClick={() => setRevealed(true)}
          >
            <Eye size={15} aria-hidden /> Show the {reviewed.length} provisional verdicts
            anyway
          </Button>
          <p className="m-0 max-w-[82ch] text-ui leading-[1.6] text-ink-3">
            Nothing here is lost by waiting. This review is kept exactly as it stands whether
            or not anyone answers, and the second pass is a review of its own beside it.
          </p>
        </>
      )}
    </section>
  );
}
