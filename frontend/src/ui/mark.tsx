import {
  ArrowLeftRight,
  Circle,
  CircleCheck,
  CircleDashed,
  CircleDot,
  CircleMinus,
  CirclePause,
  CircleSlash,
  CircleX,
  Clock,
  Equal,
  Flag,
  LoaderCircle,
  Minus,
  Plus,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { SVGProps } from "react";

import { cn } from "../lib/cn";
import type { MarkShape } from "../lib/format";

/**
 * The mark a descriptor wears, resolved to an icon.
 *
 * This has been three things. It was literal characters — `▲ ◆ ● ○ ◐` — until it turned out
 * neither Onest nor IBM Plex Mono ships the Geometric Shapes block, so every one fell back to
 * whatever the operating system had and arrived at three optical sizes on three baselines. It
 * was hand-cut SVG after that, which fixed the sizing and left the real problem: a filled
 * triangle, a diamond and a circle are three distinguishable marks and three *meaningless*
 * ones. A reader who had not learnt the key was reading the hue — the exact dependence
 * "a colour never carries meaning alone" exists to prevent.
 *
 * Now it is Lucide. The hand-drawn set was competing with a maintained one on optical
 * consistency and losing; what this file keeps is the part a library cannot supply, which is
 * *which* icon a thing is allowed to wear.
 *
 * Three registers, and the separation is load-bearing rather than decorative:
 *
 * - **A sign** — `alert` `pause` `check`, plus the three states a run can be in — for what is
 *   being **graded**: the model's verdict, and a review's own state.
 * - **A step on a scale** — `solid` `hollow` `dashed` — for a position that is not a grade.
 *   How binding a policy is, mainly. A required policy is the one to read first, not an alarm,
 *   so it may never wear the caution triangle.
 * - **A person's own move** — `flag` `clock` `slash` — for what somebody decided. Accepting a
 *   finding is a commitment to act on it, not a report that it went away, so a decision may
 *   never wear the tick either. Keeping this register apart is where the charter's separation
 *   between the model's verdict and the person's decision becomes visible.
 * - **A difference between two reviews** — `plus` `minus` `swap` `equals` — how a candidate
 *   moved from one revision to the next. These were typed characters (`✓ ~ + =`) for longer
 *   than the geometric shapes were, because `~` and `+` are ASCII and the guard only ever
 *   looked at one Unicode block. A delta is a *comparison*, not a grade — arriving, leaving,
 *   being judged differently — so it reads as diff notation and never borrows a verdict's
 *   sign. The tick that `addressed` used to carry was the clearest case: "raised last time,
 *   gone now" is not the same claim as "assessed and found unproblematic".
 *
 * Every icon here is `aria-hidden`: in all of these places the descriptor's own word sits
 * right beside it, so announcing the mark would say everything twice.
 */
const ICONS: Record<MarkShape, LucideIcon> = {
  // Signs.
  alert: TriangleAlert,
  pause: CirclePause,
  check: CircleCheck,
  failed: CircleX,
  running: LoaderCircle,
  stopped: CircleMinus,
  // Steps on a scale: filled centre, outline, dashed outline.
  solid: CircleDot,
  hollow: Circle,
  dashed: CircleDashed,
  // A person's move.
  flag: Flag,
  clock: Clock,
  slash: CircleSlash,
  // A difference between two reviews. Diff notation on purpose — arrived, left, judged
  // differently, judged the same — because none of the four says whether the candidate is any
  // good, and borrowing a verdict's sign for one of them would say exactly that.
  plus: Plus,
  minus: Minus,
  swap: ArrowLeftRight,
  equals: Equal,
};

/**
 * Lucide draws at stroke 2 on a 24 box, tuned for 20–24px. Almost nothing here renders that
 * large — a verdict on a docket row is 15px and the dense counts are 13px — and a 2 comes out
 * thin and grey once it is scaled down that far. 2.25 holds the weight without closing the
 * counters up.
 */
const STROKE = 2.25;

export function Mark({
  shape,
  className,
  ...props
}: { shape: MarkShape; className?: string } & SVGProps<SVGSVGElement>) {
  const Icon = ICONS[shape];
  return (
    <Icon
      aria-hidden="true"
      focusable="false"
      strokeWidth={STROKE}
      // Sized in `em` by default so a mark is a fixed fraction of the text beside it; every
      // call site that needs a specific size overrides with one.
      className={cn("inline-block size-[1em] shrink-0", className)}
      {...props}
    />
  );
}
