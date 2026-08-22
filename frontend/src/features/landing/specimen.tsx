import { type CSSProperties, useCallback, useEffect, useState } from "react";

import { cn } from "../../lib/cn";
import { type Tone, strengthOf, verdictOf } from "../../lib/format";
import { prefersReducedMotion } from "../../lib/motion";
import { Mark } from "../../ui/mark";
import { Mono } from "../../ui/meta";
import { type Bearing, BEARINGS } from "./bearings";

/**
 * The finding, pinned to the element of the atlas it was made against.
 *
 * The map beside this says what the machine built; this says what the model made of one
 * thing on it. Keeping them one figure rather than two is the whole argument of the hero:
 * the candidate is a place on a map somebody can point at, the verdict rests on a policy
 * somebody wrote, and both are on screen at once.
 *
 * Every field is shaped like the record it stands for — see `bearings.ts`, which is where
 * that argument is made in full.
 */

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink",
  marked: "text-ink",
  material: "text-material",
  held: "text-held",
  cleared: "text-cleared",
};

/**
 * The showcase interval, and the pause a reader's own choice earns.
 *
 * Two seconds is a demonstration, not a reading: it shows a visitor that there are three of
 * these and that the picker moves between them, in the time it takes to notice the figure at
 * all. It is deliberately shorter than the ninety-odd words a specimen carries, because the
 * cycle is no longer how anybody reads one — a hover stops it, and touching the picker buys
 * five seconds on the specimen you asked for before the showcase resumes.
 */
const SHOWCASE_MS = 2000;
const HELD_MS = 5000;

/**
 * The showcase makes one pass and then stops, which is the difference between a
 * demonstration and a carousel.
 *
 * Three verdicts is the whole vocabulary. Six seconds teaches that there are three of them
 * and that the picker moves between them, and after that the movement has nothing left to
 * say — it is only taking a ninety-word specimen away from somebody in the middle of reading
 * it, for ever, on the first screen of the page. So the pass ends where it began, on the
 * first specimen, and the reader gets to finish that one. The picker is how anybody sees the
 * other two again, which is what a picker is for; the pause control replays it.
 */
const SHOWCASE_STEPS = BEARINGS.length;

/**
 * The picker, the cycle, and which node of the atlas is lit — one hook, because all three
 * are the same piece of state and the map and the callout both need it.
 */
export function useSpecimen() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  // Two pieces, because a second click on the same button has to restart the five seconds.
  // `held` is the state the timer reads; `chose` is a counter that only ever goes up, so the
  // effect re-runs — and the hold restarts — even when `held` was already true.
  const [held, setHeld] = useState(false);
  const [chose, setChose] = useState(0);
  // The reader's own stop, which is not the hover pause: leaving the figure must not undo a
  // control somebody pressed.
  const [stopped, setStopped] = useState(false);
  const [steps, setSteps] = useState(0);

  const finished = steps >= SHOWCASE_STEPS;
  const showcasing = !stopped && !finished;

  useEffect(() => {
    if (paused || !showcasing) return;
    if (prefersReducedMotion()) return;
    if (held) {
      const hold = setTimeout(() => setHeld(false), HELD_MS);
      return () => clearTimeout(hold);
    }
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % BEARINGS.length);
      setSteps((count) => count + 1);
    }, SHOWCASE_MS);
    return () => clearInterval(timer);
  }, [paused, held, chose, showcasing]);

  const select = useCallback((next: number) => {
    setIndex(next);
    setHeld(true);
    setChose((count) => count + 1);
  }, []);

  /** Stop it where it is, or run the pass again from the top. */
  const toggleShowcase = useCallback(() => {
    if (showcasing) {
      setStopped(true);
      return;
    }
    setSteps(0);
    setHeld(false);
    setStopped(false);
  }, [showcasing]);

  return {
    index,
    select,
    showcasing,
    toggleShowcase,
    bearing: BEARINGS[index],
    /**
     * Spread onto the specimen and onto the picker, and onto nothing larger.
     *
     * This used to go on the whole hero section, which at eleven seconds a specimen was a
     * courtesy and at two is the feature's off switch: the hero is most of a first screen,
     * so a cursor resting anywhere in it — which is where a cursor rests — meant the
     * showcase never ran once. What earns a pause is the thing somebody is reading, not
     * the screen it happens to be on.
     */
    holdProps: {
      onMouseEnter: () => setPaused(true),
      onMouseLeave: () => setPaused(false),
      onFocusCapture: () => setPaused(true),
      onBlurCapture: () => setPaused(false),
    },
  };
}

/** What `useSpecimen` hands back to be spread onto the figure. */
export type HoldProps = ReturnType<typeof useSpecimen>["holdProps"];

function Specimen({ bearing, hidden }: { bearing: Bearing; hidden: boolean }) {
  const strength = strengthOf(bearing.policy.strength);
  const verdict = verdictOf(bearing.verdict);
  const bore = bearing.also ? 2 : 1;

  return (
    <div
      role="group"
      aria-label={verdict.label}
      // `visibility: hidden` already takes the subtree out of the accessibility tree in a
      // browser. `aria-hidden` says the same thing to anything that has no layout to read
      // it from — jsdom, and any tooling that walks the DOM rather than the render tree.
      aria-hidden={hidden || undefined}
      // `invisible` rather than `hidden`: the box has to keep its height for the grid track
      // to be sized by it, which is the entire point of stacking them.
      className={cn("col-start-1 row-start-1 flex flex-col", hidden && "invisible")}
    >
      {/* What the verdict rests on. The strength is a glyph and a weight, never a hue: a
          required policy is the one to read first, not an alarm. */}
      <div className="border-b border-rule bg-surface-2 px-4 py-3">
        <Mono
          className={cn(
            "flex items-center gap-1.5 text-[9.5px] font-semibold uppercase tracking-[0.14em]",
            strength.tone === "marked" ? "text-ink" : "text-ink-3",
          )}
        >
          <Mark shape={strength.glyph} className="size-3" />
          {strength.label} · {bearing.origin}
        </Mono>
        <h3 className="mt-1.5 font-display text-[13.5px] font-semibold leading-[1.36] tracking-tight text-ink">
          {bearing.policy.title}
        </h3>
        <Mono className="mt-1 block text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
          {bearing.policy.id}
        </Mono>
      </div>

      <div className="flex-1 px-4 pb-4 pt-3.5">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <Mark
            shape={verdict.glyph}
            className={cn("size-[14px] self-center", TONE_TEXT[verdict.tone])}
          />
          <span
            className={cn(
              "font-display text-[17px] font-semibold leading-tight tracking-tight",
              TONE_TEXT[verdict.tone],
            )}
          >
            {verdict.label}
          </span>
          <Mono className="text-[11px] text-ink-3 [overflow-wrap:anywhere]">
            {bearing.candidate}
          </Mono>
        </div>

        <h3 className="mt-2 font-display text-sm font-semibold leading-[1.4] text-ink">
          {bearing.finding}
        </h3>
        <p className="mt-2.5 text-[13px] leading-[1.6] text-ink-2">{bearing.reasoning}</p>

        {bearing.hinge ? (
          <p className="mt-3 rounded-md border border-held/30 bg-held-soft px-3 py-2.5 text-[12.5px] leading-[1.55] text-ink-2">
            <span className="font-semibold text-held">Hinges on:</span> {bearing.hinge}
          </p>
        ) : null}
      </div>

      {/* Retrieval pulled these; only some of them bore. Both numbers are recorded, and the
          difference between them is the point. */}
      <div className="border-t border-rule bg-surface-2 px-4 py-2.5">
        <Mono className="block text-[10.5px] text-ink-3">
          <span className="font-semibold text-ink">{bearing.retrieved}</span> retrieved ·{" "}
          <span className="font-semibold text-ink">{bore}</span> bore on the judgement
        </Mono>
        <Mono className="mt-1 block text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
          {bearing.source}
        </Mono>
      </div>
    </div>
  );
}

/**
 * One cell, three specimens in it.
 *
 * All three are rendered and the inactive two are held at `visibility: hidden`, so the grid
 * track is exactly as tall as the tallest and the callout never changes height as they
 * cycle. This replaced a `min-h` measured off one browser at one text size, which had three
 * pixels of headroom: at a 20px root size the held specimen wrapped one extra line and
 * pushed everything under it down every few seconds.
 */
export function SpecimenCallout({
  index,
  hold,
  className,
  style,
}: {
  index: number;
  hold?: HoldProps;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      style={style}
      {...hold}
      // Named as a group because it is one: the policy above and the finding below are a
      // single specimen that changes together, and a reader arriving by keyboard should be
      // told that before the pieces arrive one at a time.
      role="group"
      aria-label="A policy and the finding it produced"
      // The one lift on the page. A callout floating over the map is the other thing besides
      // a drawer that genuinely leaves the surface.
      className={cn(
        "grid overflow-hidden rounded-md border border-rule bg-surface shadow-hero",
        className,
      )}
    >
      {BEARINGS.map((bearing, position) => (
        <Specimen key={bearing.policy.id} bearing={bearing} hidden={position !== index} />
      ))}
    </div>
  );
}

/**
 * The three verdicts, as the map's legend and as the way to move between the specimens.
 *
 * These were two things — a legend under the copy and a tab strip under the card — saying
 * the same three words a hand's width apart. One thing that does both is not a saving; it is
 * the honest shape, because "what does the red node mean" and "show me the red one" are the
 * same question asked twice.
 */
export function SpecimenPicker({
  index,
  onSelect,
  showcasing,
  onToggleShowcase,
  hold,
  className,
}: {
  index: number;
  onSelect: (index: number) => void;
  /** Whether the pass is still running, which is what the control reports and reverses. */
  showcasing?: boolean;
  onToggleShowcase?: () => void;
  hold?: HoldProps;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label="Example bearings"
      {...hold}
      className={cn("flex flex-wrap items-center gap-x-1 gap-y-2", className)}
    >
      {BEARINGS.map((bearing, position) => {
        const verdict = verdictOf(bearing.verdict);
        const selected = position === index;
        return (
          <button
            key={bearing.policy.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onSelect(position)}
            className={cn(
              "inline-flex min-h-11 items-center gap-1.5 rounded-sm px-2.5 font-mono text-[10px] uppercase tracking-[0.13em] transition",
              selected ? "bg-sunken text-ink" : "text-ink-3 hover:text-ink",
            )}
          >
            <Mark shape={verdict.glyph} className={cn("size-[13px]", TONE_TEXT[verdict.tone])} />
            {verdict.label}
          </button>
        );
      })}
      <Mono className="ml-1.5 text-[10px] uppercase tracking-[0.13em] text-ink-3">
        Three verdicts, no score
      </Mono>
      {/* Something that moves on its own has to have an off switch, and this one had none:
          not a control, not a pause on hovering the headline, nothing. It sits in the picker
          because the picker is already the thing that decides which specimen is on show, and
          it carries the same 44px floor as its siblings for the same reason they do. */}
      {onToggleShowcase ? (
        <button
          type="button"
          // One name in both states, with `aria-pressed` carrying which one it is in — the
          // shape every other toggle in this product takes. A name that swapped to "Play"
          // would be a second control wearing the first one's box, and pressed would then
          // have to mean the opposite of what it says.
          aria-label="Pause the showcase"
          aria-pressed={!showcasing}
          onClick={onToggleShowcase}
          className={cn(
            "ml-auto inline-flex min-h-11 items-center rounded-sm px-2.5 font-mono text-[10px] uppercase tracking-[0.13em] transition",
            showcasing ? "text-ink-3 hover:text-ink" : "bg-sunken text-ink",
          )}
        >
          Pause
        </button>
      ) : null}
    </div>
  );
}
