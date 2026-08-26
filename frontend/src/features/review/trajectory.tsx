import type { Review } from "../../api";
import { cn } from "../../lib/cn";
import { verdictOf } from "../../lib/format";
import { Mark } from "../../ui/mark";
import { TONE_TEXT } from "../../ui/meta";

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
    // A fragment, so the sentence is a sibling of the drawn strip rather than a child of it.
    // The docket hides the strip below 768px with `hidden md:flex`, and that class landed on
    // the element the `sr-only` summary lived inside — `display: none` takes a subtree out of
    // the accessibility tree, so on a phone a screen-reader reader lost the whole fact of
    // what this candidate had been called in earlier reviews, which is the only place a row
    // carries its lineage. The sentence now survives every width; only the drawing is
    // desktop-only.
    <>
      <span className="sr-only">Across this branch — {said}.</span>
      {/* No visible label. The word "Across" stood here and told a sighted reader what the
          drawing beside it was already saying: one mark per review, numbered, at the right
          end of a row whose lineage is the only thing they could be counting. It cost about
          56px of a row whose claim is the line the docket exists to make scannable, to name
          something nobody was in doubt about. The sentence above is not the same thing said
          twice — it is the whole fact for a reader who never gets the drawing — and it stays.

          The cap is a guard now rather than a squeeze. `max-w-[15rem]` was 240px, and the
          deepest strip this component can draw is six 28px nodes and five 16px connectors:
          248px, eight pixels over its own cap, so `flex-wrap` below did exactly what it was
          told and put five nodes on one line and the sixth on a second behind a dangling
          connector. 17.5rem is 280px and clears the 274px a six-node strip with a two-digit
          `+N` takes, so the wrap never fires. The width comes out of what the label was
          holding; the rest of it goes back to the claim, and DRAWN rather than this cap is
          what stops a long lineage taking the row. */}
      <div
        aria-hidden="true"
        className={cn("flex min-w-0 max-w-[17.5rem] items-start gap-2", className)}
      >
        {/* The count of what is not drawn, in the same mono the numbers under the nodes are
            set in: a strip that silently began at review 7 would be claiming the candidate
            started there. It is given the mark row's own box, so it sits on the marks' centre
            line by the same 15px-and-`mt-px` recipe they use, rather than by a `pt-[3px]`
            that was tuned against a box height this strip no longer has. */}
        {elided ? (
          <span className="mt-px flex h-[15px] shrink-0 items-center font-mono text-[10px] tabular-nums text-ink-3">
            +{elided}
          </span>
        ) : null}
        <ol className="flex min-w-0 flex-wrap items-center">
          {drawn.map((step, index) => {
            const descriptor = step.verdict ? verdictOf(step.verdict) : null;
            return (
              <li key={step.id} className="flex items-center">
                {/* The connector lies on the mark row's centre line, not on the middle of the
                    node. A node is a column of a mark, a number and an underline, and the
                    middle of that column is nowhere in particular — it was `mb-4` asking the
                    column's total height to place the rule, which left the hairline a pixel
                    and a half below the marks it joins. `self-start` plus 8px from the top of
                    a node whose mark box starts at 1 and is 15 tall lays the rule across 8–9,
                    which is that box's centre. */}
                {index ? (
                  <span className="mt-[8px] block h-px w-3 self-start bg-rule-strong sm:w-4" />
                ) : null}
                <span className="flex w-6 flex-col items-center gap-1 sm:w-7">
                  {/* A fixed box so a verdict mark and the smaller "not raised" dot share one
                      centre line, and the strip stays level whatever each step holds.

                      15px and `mt-px` are two of the three values the checkbox and the verdict
                      mark at the left of the row carry; the third is the `py-3` on the row's
                      own button, which this strip now sits directly under. So the mark row
                      lands 20.5px from the row's top, on the line those two are already on.
                      It was an 18px box under a `pt-0.5` and landed at 23px — two and a half
                      pixels low, which is what made the right end of the row read as sagging
                      against the checkbox. 15 rather than 16 because an even box cannot sit
                      on a half-pixel centre line without a fractional offset, which is the
                      same reason the checkbox is 15px. */}
                  <span className="mt-px grid h-[15px] place-items-center">
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
                          //
                          // 70% rather than 45%, which was never measured. A mark is the whole
                          // content of its node — no word sits beside it — so it is non-text
                          // content carrying meaning, and at 45% a cleared one landed at
                          // 2.01:1 on the row's own ground in light and 2.12:1 in dark, under
                          // the 3:1 floor. At 70% the same mark measures 3.23:1 and 3.49:1,
                          // and the current node still separates from the past by a full step
                          // of weight plus its underline and its ink-weighted number.
                          !step.current && "opacity-70",
                        )}
                      />
                    ) : (
                      <span
                        className={cn(
                          "block size-[5px] rounded-full border border-rule-strong",
                          !step.current && "opacity-70",
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
    </>
  );
}

/**
 * The room the strip will take, held open until the strip itself can be drawn.
 *
 * The trajectory is drawn from the full reviews query, which is deliberately the heavy one
 * and is fired only once the cheap summary listing has shown the lineage has more than one
 * entry. Until it resolves the docket draws no strip, and when it lands up to 274px appears
 * on the right of every row at once and every claim sentence rewraps under the eye of
 * somebody who started reading seconds ago.
 *
 * Not a skeleton and not a flat `w-[17.5rem]`: `max-w-[17.5rem]` is a cap rather than a
 * width, so a two-revision lineage draws about 72px and a fixed reservation would
 * over-reserve and produce a second, smaller shift when the real strip arrived. This draws
 * the real strip's own structure with the contents left out — the same computable `+N`, the
 * same fixed `w-6 sm:w-7` nodes and `w-3 sm:w-4` connectors, on the same centre lines — so
 * the width and the height it holds open are the width and the height the strip takes, at
 * every breakpoint, without either component knowing a number the other does not.
 */
export function TrajectoryPlaceholder({
  depth,
  className,
}: {
  /** How many revisions the lineage has, from the listing that has already answered. */
  depth: number;
  className?: string;
}) {
  if (depth < 2) return null;
  const nodes = Math.min(depth, DRAWN);
  const elided = depth - nodes;
  return (
    // `invisible` rather than an empty box: `visibility: hidden` keeps every one of these
    // elements in the layout and paints none of them, which is exactly what reserving space
    // means. A skeleton would be a second thing to look at for a strip that is decorative
    // once its `sr-only` sentence is a sibling of it.
    <div
      aria-hidden="true"
      className={cn("invisible flex min-w-0 max-w-[17.5rem] items-start gap-2", className)}
    >
      {elided ? (
        <span className="mt-px flex h-[15px] shrink-0 items-center font-mono text-[10px] tabular-nums text-ink-3">
          +{elided}
        </span>
      ) : null}
      <ol className="flex min-w-0 flex-wrap items-center">
        {Array.from({ length: nodes }, (_, index) => (
          <li key={index} className="flex items-center">
            {index ? (
              <span className="mt-[8px] block h-px w-3 self-start bg-rule-strong sm:w-4" />
            ) : null}
            {/* The node's own height, said the way the drawn one says it: a 15px mark box a
                pixel down, a 10px number and a 2px underline, with the same `gap-1` between
                them. The `mt-px` is not padding — it is the pixel that puts the mark row on
                the row's own centre line, and the reservation is wrong by it if it is left
                out. */}
            <span className="flex w-6 flex-col items-center gap-1 sm:w-7">
              <span className="mt-px block h-[15px]" />
              <span className="block h-[10px]" />
              <span className="block h-[2px]" />
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
