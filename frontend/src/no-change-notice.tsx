import { Info, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

/**
 * The run's answer that nothing has changed, floating where the eye wandered while it
 * waited.
 *
 * Held beside the run rather than on any page, because the answer is the run's: the
 * workspace works the whole partition out and refuses a revision that would repeat the
 * one before it, whichever page asked for it — the review page's New revision button and
 * the start page's Run review land in the same stream and get the same line back.
 *
 * It fades in on arrival and out on dismissal — an element that pops into a corner reads
 * as something breaking, and one that vanishes under the pointer reads as a misclick. The
 * fade is two phases of one state rather than a mounted/unmounted pair, because the exit
 * has to finish before the element may leave the tree. Dismissal is the only way out, so
 * the timestamp ages in place — a check grows stale the moment somebody edits a file, and
 * only the reader knows when they have read it. Reduced motion collapses both fades to a
 * cut.
 */
function checkedAgo(elapsedSeconds: number): string {
  const count = (n: number, unit: string) =>
    `checked ${n} ${unit}${n === 1 ? "" : "s"} ago`;
  const seconds = Math.max(1, elapsedSeconds);
  if (seconds < 60) return count(seconds, "second");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return count(minutes, "minute");
  return count(Math.floor(minutes / 60), "hour");
}

export function NoChangeNotice({ onDismiss }: { onDismiss: () => void }) {
  const [phase, setPhase] = useState<"entering" | "shown" | "leaving">("entering");
  const [checkedAt] = useState(() => Date.now());
  const [now, setNow] = useState(checkedAt);
  useEffect(() => {
    // One frame late, so the browser paints the hidden state first and the transition has
    // somewhere to start from.
    const frame = requestAnimationFrame(() => setPhase("shown"));
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelAnimationFrame(frame);
      window.clearInterval(tick);
    };
  }, []);
  const leave = () => {
    setPhase("leaving");
    window.setTimeout(onDismiss, 200);
  };
  return (
    <Alert
      role="status"
      className={cn(
        "fixed z-40 w-auto max-w-[420px] cursor-pointer border-accent-rule bg-surface pr-9 text-ink shadow-float",
        "top-14 right-[var(--gutter)]",
        "max-sm:inset-x-3 max-sm:right-3 max-sm:max-w-none",
        "transition-[opacity,translate] duration-200 motion-reduce:transition-none",
        phase !== "shown" && "-translate-y-1 opacity-0",
      )}
      onClick={leave}
    >
      <Info aria-hidden className="text-accent-ink" />
      <AlertTitle>Nothing has changed</AlertTitle>
      <AlertDescription className="text-ink-2">
        The code is the same as this revision —{" "}
        {checkedAgo(Math.floor((now - checkedAt) / 1000))}.
      </AlertDescription>
      {/* Not AlertAction: that slot's CSS turns the alert `relative`, which would beat the
          `fixed` above and drop the notice into the page flow. */}
      <button
        type="button"
        aria-label="Dismiss"
        className="absolute top-2.5 right-2.5 cursor-pointer border-0 bg-transparent p-0 text-ink-3 hover:text-ink"
        onClick={leave}
      >
        <X size={14} aria-hidden />
      </button>
    </Alert>
  );
}
