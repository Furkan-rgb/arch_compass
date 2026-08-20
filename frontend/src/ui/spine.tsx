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
 * has once there is a verdict, and takes the verdict's hue. The person has once there is a
 * standing decision.
 *
 * So `▮▮▯` is judged and waiting on you and `▮▮▮` is settled, and the difference between
 * the Attention and Settled filters is visible before a word has been read. The words stay
 * on the row regardless: this is a scanning aid, never the sole carrier, because a colour
 * never carries meaning alone.
 *
 * It replaces the `opacity-60` a decided row used to get, which said "less important"
 * rather than "further along".
 */
export function Spine({
  verdict,
  decided,
  className,
}: {
  verdict: string;
  decided?: boolean;
  className?: string;
}) {
  const descriptor = verdictOf(verdict);
  return (
    <span
      aria-hidden="true"
      className={cn("flex shrink-0 flex-col gap-0.5 pt-1", className)}
    >
      <i className="block h-[7px] w-[3px] bg-ink" />
      <i className={cn("block h-[7px] w-[3px]", FILL[descriptor.tone])} />
      <i className={cn("block h-[7px] w-[3px]", decided ? "bg-ink" : "bg-rule-strong")} />
    </span>
  );
}
