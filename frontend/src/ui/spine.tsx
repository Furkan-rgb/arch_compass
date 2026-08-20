import { type Tone, verdictOf } from "../lib/format";
import { cn } from "../lib/cn";

const FILL: Record<Tone, string> = {
  neutral: "bg-ink",
  marked: "bg-ink",
  material: "bg-material",
  held: "bg-held",
  cleared: "bg-cleared",
};

/**
 * The three jobs, compressed to ten pixels, at the left edge of a queue row.
 *
 * Three stacked segments: the machine, the model, the person. The machine has always
 * spoken — there is always evidence, that is what raised the candidate at all. The model
 * has once there is a verdict. The person has once there is a standing decision.
 *
 * So `▮▮▯` is judged and waiting on you and `▮▮▮` is settled, and the difference between
 * the Attention and Settled filters is visible before a word has been read. The words stay
 * on the row regardless: this is a scanning aid, never the sole carrier, because a colour
 * never carries meaning alone.
 *
 * It replaces the `opacity-60` a decided row used to get, which said "less important"
 * rather than "further along".
 *
 * ## What the middle segment is for
 *
 * `shows` picks between the two answers, and both of them are right somewhere.
 *
 * - `"verdict"` paints the verdict's hue. A queue whose rows disagree wants that: six rows
 *   that are not all the same grade are worth telling apart at the edge of vision, and the
 *   hue is doing real work.
 * - `"stage"` paints ink. A group where every row holds the same verdict does not: the
 *   header states it once — `ports.* · all held` — and then the column restates it six
 *   times in amber, which is six elements carrying a hue to say something already said.
 *   Stage is what is still varying down that column, so the tick shows measured → judged →
 *   decided and nothing else.
 *
 * The default is `"verdict"`, so a caller that has not thought about which group it is in
 * gets the behaviour it had rather than a column that quietly went grey.
 */
export function Spine({
  verdict,
  decided,
  shows = "verdict",
  className,
}: {
  verdict: string;
  decided?: boolean;
  /** `"stage"` where the group already states the verdict; `"verdict"` where it is mixed. */
  shows?: "verdict" | "stage";
  className?: string;
}) {
  const descriptor = verdictOf(verdict);
  // A verdict string this build has no word for falls back to the neutral tone. Under
  // `"verdict"` that is ink, which is fine — the row's own label says the same. Under
  // `"stage"` it has to read as "the model has not spoken", or an unjudged candidate would
  // claim to be a step further along than it is.
  const judged = descriptor.tone !== "neutral";
  return (
    <span aria-hidden="true" className={cn("flex shrink-0 flex-col gap-0.5 pt-1", className)}>
      <i className="block h-[7px] w-[3px] rounded-xs bg-ink" />
      <i
        className={cn(
          "block h-[7px] w-[3px] rounded-xs",
          shows === "stage" ? (judged ? "bg-ink" : "bg-rule-strong") : FILL[descriptor.tone],
        )}
      />
      <i className={cn("block h-[7px] w-[3px] rounded-xs", decided ? "bg-ink" : "bg-rule-strong")} />
    </span>
  );
}
