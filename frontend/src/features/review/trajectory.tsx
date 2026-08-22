import type { Review } from "../../api";
import { cn } from "../../lib/cn";
import { verdictOf } from "../../lib/format";
import { Mark } from "../../ui/mark";
import { TONE_TEXT } from "../../ui/meta";
import { Label } from "../../ui/panel";

/**
 * What this candidate has been called, review after review.
 *
 * Reviews are immutable and sequenced per branch and case — that is the charter's third
 * commitment and the reason a delta can exist at all — and until now the only thing the
 * interface did with that was print "changed since the last review". A candidate that was
 * cleared, then held, then material is a different thing to decide about than one that
 * arrived material this morning, and nothing on screen said which you were looking at.
 *
 * So the lineage is drawn as what it is: one node per revision, each carrying the verdict
 * that revision reached. Absent means the candidate did not exist yet — a hollow node rather
 * than a gap, because "this is new" is itself the fact.
 *
 * The revision being read is the one at full strength, underlined, its number in ink; the
 * rest of the lineage recedes to 45%. It used to be ringed instead, which stopped working the
 * day the verdict marks became circles — a ring around a circle is two concentric circles and
 * says nothing. Contrast was the better answer anyway: it takes emphasis off the past instead
 * of adding chrome to the present, and an underline plus weight is what this system already
 * uses everywhere else to mean "you are here".
 *
 * It is a strip and not a chart. Four to eight nodes at 11px is a glance; anything that
 * needed a legend would be a dashboard, and the charter is blunt about those.
 *
 * Which is also why it is capped. A branch reviewed weekly for a quarter has a dozen
 * revisions, and the strip was `shrink-0`: it took whatever width it wanted from the row and
 * the claim — the line that makes the docket readable — gave up the difference. The last six
 * are drawn, prefixed with what that leaves out, and the full sequence stays in the sentence
 * below, which is the copy that was already carrying it for anyone not looking at the strip.
 */
const DRAWN = 6;

export function CandidateTrajectory({
  lineage,
  candidateId,
  currentReviewId,
  className,
}: {
  /** The revisions of one branch-and-case, oldest first. */
  lineage: Review[];
  candidateId: string;
  currentReviewId: string;
  className?: string;
}) {
  // One node is not a trajectory, it is a dot. A lineage of one says "first review", which
  // the head already says, so nothing is drawn.
  if (lineage.length < 2) return null;

  const steps = lineage.map((review) => ({
    id: review.id,
    sequence: review.sequence,
    verdict: review.findings.find((finding) => finding.candidate.id === candidateId)?.verdict ?? null,
    current: review.id === currentReviewId,
  }));

  const said = steps
    .map((step) =>
      step.verdict
        ? `review ${step.sequence}: ${verdictOf(step.verdict).label.toLowerCase()}`
        : `review ${step.sequence}: not raised`,
    )
    .join(", ");

  const drawn = steps.slice(-DRAWN);
  const elided = steps.length - drawn.length;

  return (
    <div className={cn("flex min-w-0 max-w-[15rem] items-start gap-2", className)}>
      <span className="sr-only">Across this branch — {said}.</span>
      <div aria-hidden="true" className="flex min-w-0 items-start gap-2">
        <Label className="shrink-0 pt-[3px]">Across</Label>
        {/* The count of what is not drawn, in the same mono the numbers under the nodes are
            set in: a strip that silently began at review 7 would be claiming the candidate
            started there. */}
        {elided ? (
          <span className="shrink-0 pt-[3px] font-mono text-[10px] tabular-nums text-ink-3">
            +{elided}
          </span>
        ) : null}
        <ol className="flex min-w-0 flex-wrap items-center">
          {drawn.map((step, index) => {
            const descriptor = step.verdict ? verdictOf(step.verdict) : null;
            return (
              <li key={step.id} className="flex items-center">
                {index ? <span className="mb-4 block h-px w-3 bg-rule-strong sm:w-4" /> : null}
                <span className="flex w-6 flex-col items-center gap-1 sm:w-7">
                  {/* A fixed box so a verdict mark and the smaller "not raised" dot share one
                      centre line, and the strip stays level whatever each step holds. */}
                  <span className="grid h-[18px] place-items-center">
                    {descriptor ? (
                      <Mark
                        shape={descriptor.glyph}
                        className={cn(
                          "size-[13px]",
                          TONE_TEXT[descriptor.tone],
                          // The revision being read is the one at full strength; the rest of
                          // the lineage recedes. Emphasis by contrast rather than by chrome —
                          // which is also the only option left now that the marks are
                          // themselves circles, because a ring around one reads as two
                          // concentric circles and says nothing.
                          !step.current && "opacity-45",
                        )}
                      />
                    ) : (
                      <span
                        className={cn(
                          "block size-[5px] rounded-full border border-rule-strong",
                          !step.current && "opacity-45",
                        )}
                      />
                    )}
                  </span>
                  <span
                    className={cn(
                      "font-mono text-[10px] leading-none tabular-nums",
                      step.current ? "font-semibold text-ink" : "text-ink-3",
                    )}
                  >
                    {step.sequence}
                  </span>
                  {/* "You are here", as the underline this system already uses for it — a rule
                      and weight, never a hue and never a container. Drawn for every step so the
                      strip does not change height when the read revision changes. */}
                  <span
                    className={cn(
                      "block h-[2px] w-3 rounded-full",
                      step.current ? "bg-ink" : "bg-transparent",
                    )}
                  />
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
