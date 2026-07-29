import { Eye, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { formatDate, shortId } from "./components";
import { RunProgress } from "./run-progress";
import type { BoundaryReview, ReviewedBoundary } from "./types";

/**
 * A review that judged everything and is now waiting on a person.
 *
 * Not a results page, and deliberately not a shorter one. Every boundary here has a verdict
 * and those verdicts are stored — what is withheld is presenting them as findings, because
 * they are not yet findings. Measured on the bundled `warehouse-sync` example, four of five
 * first-pass verdicts moved once the questions below were answered, so a page that led with
 * them would be leading with conclusions more likely wrong than right, in the same confident
 * badges a settled verdict wears.
 *
 * What it does show is the shape of what was done — how many boundaries, how many verdicts
 * rested on something unstated — because that is what makes the questions worth answering.
 * A page that asked for information while saying nothing about what it had found would be
 * charging the reader before showing them anything, which is the adoption tax elicitation
 * exists to remove.
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

export function AwaitingAnswers({
  review,
  questionCount,
  reviewed,
  policyCount,
  children,
  findings,
}: {
  review: BoundaryReview;
  questionCount: number;
  reviewed: ReviewedBoundary[];
  policyCount: number;
  /** The questions surface, supplied rather than built here. */
  children: ReactNode;
  /** The held verdicts, rendered only once the reader has asked to see them. */
  findings: ReactNode;
}) {
  const [revealed, setRevealed] = useState(false);
  const contingent = contingentCount(reviewed);
  const reviewId = review.review_id ?? "";

  return (
    <div className="page page--review">
      <header className="review-head">
        <span className="eyebrow">Boundary review · waiting on you</span>
        <h1>{review.report?.case_title}</h1>
        <p className="review-head__meta">
          <strong>{reviewed.length}</strong> boundaries judged ·{" "}
          <strong>{policyCount}</strong> policies presented to each ·{" "}
          <strong>{contingent}</strong>{" "}
          {contingent === 1 ? "verdict rests" : "verdicts rest"} on something the case does
          not say
        </p>
        <dl className="provenance">
          <div>
            <dt>Case revision</dt>
            <dd>rev {review.case_revision}</dd>
          </div>
          <div>
            <dt>Atlas version</dt>
            <dd title={review.atlas_version_id}>{shortId(review.atlas_version_id)}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd title={review.prompt_identity}>{review.reasoning_model}</dd>
          </div>
          <div>
            <dt>Judged</dt>
            <dd>{formatDate(review.created_at)}</dd>
          </div>
        </dl>
      </header>

      {/* The run's own steps, still on screen, because the journey is not over. Every other
          stage ends because the application ended it; this one is waiting on a person, and
          it stays waiting across a reload because it is read from the stored status rather
          than from anything this page remembers. */}
      <RunProgress
        progress={{
          total: reviewed.length,
          boundaries: [],
          verdicts: reviewed.map((item) => item.material),
          judged: reviewed.length,
          eliciting: false,
          summarising: false,
        }}
        awaiting={questionCount}
        heading={
          <>
            Every boundary has been judged. Before those verdicts are worth reporting, the
            review needs to know{" "}
            {questionCount === 1 ? "one thing" : `${questionCount} things`} the case does not
            say — answering carries it on, and the second pass is the one that concludes.
          </>
        }
      />

      {children}

      {/* Last, small, and honest about what it costs. Not hidden — someone who cannot answer
          has to be able to get something — but not offered as an equal path either, because
          on this example four of five of these moved once the questions were answered. */}
      <section className="held">
        {revealed ? (
          <>
            <p className="held__warning">
              <TriangleAlert size={15} aria-hidden />
              <span>
                <strong>These verdicts are provisional.</strong> They were reached against a
                case that does not yet say what the questions above ask about. On the example
                this flow was measured against, four of five verdicts came out differently
                once those questions were answered — and the one that did not move was not
                predictable in advance. Read them as what the review currently supposes, not
                as what it concludes.
              </span>
            </p>
            {findings}
          </>
        ) : (
          <button
            type="button"
            className="button held__reveal"
            onClick={() => setRevealed(true)}
          >
            <Eye size={15} aria-hidden /> Show the {reviewed.length} provisional verdicts
            anyway
          </button>
        )}
        <p className="held__note">
          Nothing here is lost by waiting. This review is kept exactly as it stands, whether
          or not anyone answers — <code>{shortId(reviewId)}</code> ·{" "}
          <Link to="/reviews">All reviews</Link>
        </p>
      </section>
    </div>
  );
}
