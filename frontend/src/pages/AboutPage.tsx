import { BookOpen, Play } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Citation, PosterStripe, VERDICT_INK, posterCard } from "@/components/ledger";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { HomeAtlas } from "../home-atlas";
import { JudgingLedger } from "../review-ledger";
import type { RunState } from "../run-progress";
import { REPLAY } from "./HomePage";

/* The same editorial column as the front door, for the same reason: this page states the
   method, it is not a workbench, and it has no context to put in a context row. */
const column = "mx-auto w-[min(1120px,100%)] px-[var(--gutter)]";

const band = "border-t border-rule";
const sectionHead = "m-0 mb-1.5 text-[clamp(21px,2.4vw,26px)]";
const sectionSub = "m-0 mb-[26px] max-w-[62ch] text-body leading-[1.6] text-ink-2";

/* The front door's specimen rule holds here too: the annotated verdict is fabricated, so it
   says so on the line above it. */
const specimen = cn(
  "m-0 mb-2.5 flex items-center gap-2 text-balance font-mono text-micro tracking-[.1em]",
  "text-ink-3 uppercase after:h-px after:flex-1 after:bg-rule after:content-['']",
);

/**
 * The page's two words, worn as chips. Every stage of a review is one of these, and the
 * distinction is the thing this page exists to state — so it is drawn the same way at every
 * stage rather than restated in prose each time.
 *
 * The judged dot borrows `--inference`, the ink the atlas already uses for "a machine
 * inferred this". Not the accent: accent means "you can act on this", and a stage is not
 * an action.
 */
function Lane({ kind }: { kind: "computed" | "judged" }) {
  return (
    <span
      className={cn(
        "flex items-center gap-[7px] rounded-pill border border-rule bg-sunken px-2 py-[3px]",
        "font-mono text-micro tracking-[.07em] whitespace-nowrap text-ink-2 uppercase",
        "before:size-[6px] before:rounded-pill before:content-['']",
        kind === "computed"
          ? "before:bg-ink-3 before:opacity-40"
          : "before:bg-[var(--inference)]",
      )}
    >
      {kind === "computed" ? "computed" : "judged by the model"}
    </span>
  );
}

/** A marker on the anatomy card, and the same mark again at the head of its legend entry. */
function Mark({ letter }: { letter: string }) {
  return (
    <span
      className={cn(
        "grid size-[18px] flex-none place-items-center rounded-pill border border-rule",
        "bg-sunken font-mono text-micro leading-none text-ink-2",
      )}
    >
      {letter}
    </span>
  );
}

/**
 * One verdict with its parts marked — the front door shows what a verdict looks like; this
 * figure says where each part of one comes from. The atoms are the ledger's own, so the
 * dissected specimen cannot drift from the records it explains.
 */
function AnatomyFigure() {
  return (
    <div
      data-slot="verdict-anatomy"
      className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] items-start gap-[26px] max-[880px]:grid-cols-1"
    >
      <article className={cn(posterCard, "rounded-panel pt-[22px] pr-6 pb-5 pl-[18px] shadow-panel")}>
        <PosterStripe verdict="material" />
        <div className="grid gap-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Mark letter="a" />
            <span className="font-mono text-meta text-ink-3 [overflow-wrap:anywhere]">
              orders/adapters/repository_port.py
            </span>
            <span className="rounded-pill border border-rule bg-sunken px-2 py-[3px] font-mono text-micro tracking-[.07em] whitespace-nowrap text-ink-2 uppercase">
              indirection hiding nothing
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <Mark letter="b" />
            <p
              className={cn(
                "m-0 font-display text-head leading-[1.15] font-bold tracking-[-.015em]",
                "[text-shadow:var(--lamp-glow)]",
                VERDICT_INK.material,
              )}
            >
              Remove the boundary.
            </p>
          </div>
          <div className="flex items-start gap-2">
            <Mark letter="c" />
            <p className="m-0 text-ui leading-[1.6] text-ink-2">
              One implementation, one caller, and a signature that repeats the ORM’s own.
              Every change passes through this port unchanged — it costs a hop on every read
              and buys no freedom to vary.
            </p>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <Mark letter="d" />
            <Citation>avoid-pass-through-parameters</Citation>
          </div>
        </div>
      </article>

      <dl className="m-0 grid content-start gap-3.5">
        {[
          {
            letter: "a",
            name: "The boundary, and the shape it was found in",
            says:
              "Written by the sweep, before any model runs. A deterministic detector found " +
              "this boundary and named the structural pattern it matches — the same " +
              "repository surfaces the same candidates every time.",
          },
          {
            letter: "b",
            name: "The verdict",
            says:
              "One of three first-class answers: remove the boundary, give this knowledge " +
              "one owner, or leave it exactly as it is. Chosen by the model, for this " +
              "boundary, against your case.",
          },
          {
            letter: "c",
            name: "The reasoning",
            says:
              "The response schema declares the rationale before the verdict, deliberately: " +
              "a structured-output model fills a schema in order, so the reasoning is " +
              "written before the conclusion it has to carry.",
          },
          {
            letter: "d",
            name: "The bearings",
            says:
              "The policies this verdict leaned on. The model is shown every policy without " +
              "its identifier and answers one bearing per policy, in order — identity is " +
              "attached back by position, so nothing the model writes is ever used as an " +
              "identifier.",
          },
        ].map(({ letter, name, says }) => (
          <div key={letter} className="grid grid-cols-[18px_minmax(0,1fr)] gap-x-2.5">
            <Mark letter={letter} />
            <dt className="m-0 self-center text-ui font-[650]">{name}</dt>
            <dd className="col-start-2 m-0 mt-1 text-ui leading-[1.6] text-ink-2">{says}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/* Where the reading line sits in the viewport: a little above the middle, which is where
   the eye actually is. The rail's fill, the active stage and the dot all resolve against
   this one fraction, so the three can never disagree about where the reader is. */
const READING_LINE = 0.38;

/* Where the rail runs: the number column is 44px wide, the line is down its middle, and it
   starts at the first number's centre. */
const RAIL_X = 22;
const RAIL_TOP = 10;

/* The hysteresis band. A stage takes over only once the reading line is well into it, and
   hands back only once the line has backed well out — so the boundary between two stages
   is a band, not an edge, and one tick of the wheel at that boundary cannot flip the
   figure forward and back. */
const ENTER_PX = 72;
const EXIT_PX = 28;

/* Ease with flat ends: the course cruises through the middle of a stage's prose and pulls
   in as it approaches the next number, so the dot dwells at each station instead of
   gliding through every one at the same speed. */
const smootherstep = (t: number) => t * t * t * (t * (6 * t - 15) + 10);

/**
 * Which stage the reader is on and how far down the course they are, read from where they
 * have scrolled to.
 *
 * One measurement drives both: the stage under the reading line is the active one, and the
 * distance the line has travelled into the list is the blue fill on the rail. Measured on
 * scroll rather than observed by intersection, because the fill is continuous — it moves
 * as the reader moves, not in five steps. Scroll is the reader's own gesture, which is why
 * this needs no reduced-motion still: a course that only advances when the reader moves is
 * already still whenever they are.
 */
function useRunCourse(count: number) {
  const [course, setCourse] = useState({ stage: 0, fillPx: 0, railPx: 0 });
  const listRef = useRef<HTMLOListElement | null>(null);
  const refs = useRef<Array<HTMLLIElement | null>>([]);

  useEffect(() => {
    const measure = () => {
      const list = listRef.current;
      if (!list) return;
      const bounds = list.getBoundingClientRect();
      // jsdom lays nothing out; the course then holds its start, which is a complete
      // drawing rather than a broken one.
      if (bounds.height === 0) return;
      const line = window.innerHeight * READING_LINE;
      const tops = refs.current
        .slice(0, count)
        .map((element) => (element ? element.getBoundingClientRect().top : Infinity));

      // The rail ends at the last number's centre: nothing runs after the record, so no
      // line is drawn past it.
      const railPx = tops[count - 1] - bounds.top + RAIL_TOP / 2;

      // The dot's position, eased station to station. `raw` is where the reading line
      // literally is; the fill re-maps it within each segment so it leaves a number
      // slowly, crosses the prose quickly, and settles into the next number — arriving
      // exactly where the linear line would, just not at a constant speed.
      const raw = Math.min(Math.max(line - bounds.top - RAIL_TOP, 0), railPx);
      const stations = tops.map((top) => top - bounds.top + 2);
      let fillPx = raw;
      for (let index = count - 2; index >= 0; index--) {
        if (raw < stations[index]) continue;
        const span = stations[index + 1] - stations[index];
        if (span > 0 && raw < stations[index + 1]) {
          fillPx = stations[index] + span * smootherstep((raw - stations[index]) / span);
        }
        break;
      }
      fillPx = Math.min(Math.max(fillPx, 0), railPx);

      setCourse((prev) => {
        let stage = prev.stage;
        while (stage < count - 1 && line >= tops[stage + 1] + ENTER_PX) stage += 1;
        while (stage > 0 && line < tops[stage] - EXIT_PX) stage -= 1;
        return { stage, fillPx, railPx };
      });
    };

    let scheduled = false;
    const onScroll = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        measure();
      });
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [count]);

  return { ...course, listRef, refs };
}

/** The specimen run at one moment: how many verdicts have landed, and whether the boundary
    at the count is under the model right now or the run has moved past judging. */
function runAt(judged: number, settled: boolean): RunState {
  return {
    total: REPLAY.length,
    boundaries: REPLAY.map((item) => item.name),
    verdicts: REPLAY.map((item, index) => (index < judged ? item.material : null)),
    judged,
    eliciting: settled,
    summarising: false,
    concluded: false,
  };
}

/**
 * The run the reader scrolls through: one figure per stage, stacked in one cell and
 * crossfaded, each drawn by the app's own run components so the method page cannot show a
 * run the product would not.
 *
 * `aria-hidden` as a whole, deliberately. Five layers of ledger would read as five reviews
 * to a screen reader, and every fact in the figure is already in the stage prose beside it
 * — this is the prose's illustration, not a second copy of the page.
 */
function RunFigure({ stage }: { stage: number }) {
  const material = REPLAY.map((item) => item.material);
  const bearings = REPLAY.map((item) => item.bearings);

  const layers: ReactNode[] = [
    // The atlas, before the sweep: every module drawn and no boundary yet surfaced, which
    // is what a judged count below zero means to the map — nothing judging, nothing landed.
    <HomeAtlas key="atlas" judged={-1} material={material} bearings={bearings} />,
    // The sweep's whole output: every boundary named and queued, none under the model.
    <JudgingLedger
      key="sweep"
      progress={runAt(0, true)}
      foot={<>Complete, not sampled: the five rows exist before any verdict does.</>}
    />,
    // Judgement in flight: three landed, the fourth under the model now.
    <JudgingLedger key="judging" progress={runAt(3, false)} bearings={bearings} />,
    // Held at the question: every verdict in, and the run stopped to ask.
    <div key="asking">
      <JudgingLedger progress={runAt(REPLAY.length, true)} bearings={bearings} />
      <div className="rounded-panel border border-accent-rule bg-accent-soft px-4 py-3">
        <p className="m-0 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui font-semibold">
          <code className="rounded-pill border border-accent-rule bg-surface px-2 py-px font-mono text-micro font-normal tracking-[.04em] text-accent-ink">
            Q-2
          </code>
          Is the duplication between <code>pricing/</code> and <code>invoicing/</code>{" "}
          deliberate?
        </p>
        <p className="m-0 mt-1.5 text-meta leading-[1.5] text-ink-2">
          The run holds at <em>awaiting answers</em>. The answer lands on the case as a new
          revision, and the second pass re-judges against it.
        </p>
      </div>
    </div>,
    // The record: the same finished set, now a file with its provenance on it.
    <div key="record">
      <div className="mb-2.5 flex flex-wrap items-center gap-2.5 rounded-panel border border-rule bg-sunken px-4 py-2.5">
        <span className="min-w-0 overflow-hidden font-mono text-meta text-ellipsis whitespace-nowrap text-ink-2">
          archcompass-review-2026-08-02-a41c9e.md
        </span>
      </div>
      <JudgingLedger progress={runAt(REPLAY.length, true)} bearings={bearings} />
      <p className="m-0 font-mono text-micro text-ink-3">
        pinned: case revision 2 · atlas 3f9c1ab · written once, never rewritten
      </p>
    </div>,
  ];

  return (
    <div aria-hidden data-slot="run-figure">
      <p className={specimen}>Specimen run</p>
      <div className="grid">
        {layers.map((layer, index) => (
          <div
            key={index}
            // The incoming layer rises the last few pixels into place, so a stage change
            // lands on both sides of the page at once — the number pops and the figure
            // settles, one event drawn twice.
            className={cn(
              "[grid-area:1/1] transition-[opacity,transform,visibility] duration-500 ease-out",
              "motion-reduce:translate-y-0 motion-reduce:transition-none",
              index === stage
                ? "visible translate-y-0 opacity-100"
                : "invisible translate-y-[6px] opacity-0",
            )}
          >
            {layer}
          </div>
        ))}
      </div>
    </div>
  );
}

type Stage = {
  number: string;
  name: string;
  lane: "computed" | "judged";
  body: ReactNode;
};

const STAGES: Stage[] = [
  {
    number: "01",
    name: "The atlas",
    lane: "computed",
    body: (
      <>
        The repository is parsed into an atlas — modules, boundaries, dependencies — by
        reading the Python source as syntax, without importing or running any of it. The
        atlas is an immutable snapshot: the same repository produces the same atlas, every
        time, and every later stage works from it rather than from the source tree.
      </>
    ),
  },
  {
    number: "02",
    name: "The sweep",
    lane: "computed",
    body: (
      <>
        Structural detectors walk the atlas and surface every candidate boundary —
        completely, not sampled and not ranked. Three patterns cover both directions a
        boundary can be wrong: an <em>indirection hiding nothing</em> (a port with one
        implementation and nothing to vary), <em>knowledge with no owner</em> (one rule
        restated in several places), and a <em>concept that escaped its package</em>. A
        candidate is not a violation — it is a place worth judging, and each one carries a
        note of what static analysis cannot see about it.
      </>
    ),
  },
  {
    number: "03",
    name: "The judgement",
    lane: "judged",
    body: (
      <>
        One model call per candidate. The call is given three things: your case (what this
        software actually has to do), the candidate itself, and the whole policy corpus —
        nothing is retrieved or ranked, so no verdict can miss a policy a ranker dropped.
        The stage never sees the repository; it judges the evidence the sweep prepared. The
        same port can be dead weight in one case and load-bearing in another, which is why
        this step is a judgement and not a rule.
      </>
    ),
  },
  {
    number: "04",
    name: "Reading the set",
    lane: "judged",
    body: (
      <>
        The one call that sees every verdict at once. On a first pass it may find that the
        code could not answer for itself — then the review stops and asks you. Your answers
        are recorded on the case as question-and-answer pairs, in your words, and become a
        new case revision; the second pass re-judges against that revision and must
        conclude. The ledger attributes every verdict that moved to the answer that moved
        it, and both passes stay readable.
      </>
    ),
  },
  {
    number: "05",
    name: "The record",
    lane: "computed",
    body: (
      <>
        The finished review is written once and never rewritten — pinned to the case
        revision and atlas version it ran against, with source excerpts captured at the
        moment the repository is known to match. Re-running is a second record, not a
        correction of the first. Reading a review only reads.
      </>
    ),
  },
];

/**
 * The five stages as scroll steps, with the run they describe advancing beside them.
 *
 * The prose is the page and the figure is its illustration: below the width where both fit,
 * the figure withdraws and the stages read as they always did, so nothing the page states
 * lives only in the picture.
 */
function StageWalk() {
  const { stage, fillPx, railPx, listRef, refs } = useRunCourse(STAGES.length);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,440px)] gap-x-[clamp(28px,4vw,52px)] max-[999px]:grid-cols-1">
      {/* The bottom margin is the sticky figure's travel: without it the record — the
          tallest layer — runs out of column before the last stage is read, and its top is
          clipped just as it becomes the thing being explained. */}
      <ol
        ref={listRef}
        data-slot="stage-list"
        className="relative m-0 mb-[14vh] grid list-none content-start gap-0 p-0 max-[999px]:mb-0"
      >
        {/* The course down the number column: the rule is the route, the blue fill is how
            far the reader has come, and the dot is where they are — the same accent, and
            the same statement, as the plotted course on the front door. All three are
            geometry over what the numbers already say, so all three are hidden from
            assistive tech. Heights in pixels rather than transitions: the fill is measured
            from the reader's own scroll every frame, and easing it would make the line lag
            the person it is about. */}
        <span
          aria-hidden
          className="absolute w-px -translate-x-1/2 bg-rule-soft"
          style={{ left: RAIL_X, top: RAIL_TOP, height: railPx }}
        />
        <span
          aria-hidden
          className="absolute w-[2px] -translate-x-1/2 rounded-pill bg-primary"
          style={{ left: RAIL_X, top: RAIL_TOP, height: fillPx }}
        />
        {railPx > 0 ? (
          <span
            aria-hidden
            className="absolute size-[7px] -translate-x-1/2 rounded-pill bg-primary shadow-[0_0_0_3px_var(--canvas)]"
            style={{ left: RAIL_X, top: RAIL_TOP + fillPx - 3.5 }}
          />
        ) : null}

        {STAGES.map(({ number, name, lane, body }, index) => (
          <li
            key={number}
            id={`stage-${number}`}
            ref={(element) => {
              refs.current[index] = element;
            }}
            data-active={index === stage || undefined}
            className="grid grid-cols-[44px_minmax(0,1fr)] gap-x-4"
          >
            <div className="flex flex-col items-center pt-[3px]">
              <span className="relative grid place-items-center">
                {/* The arrival: a ring out of the station the course just reached, in the
                    atlas's own "under the model now" vocabulary — spent here on "under
                    the eye now". Keyed mount, so it plays once per arrival and nothing
                    loops while the reader is still. */}
                {index === stage ? <span aria-hidden className="about-station-ring" /> : null}
                {/* On the canvas, over the rail: the number wears the page's own
                    background so the line runs up to it rather than through it, and its
                    ink says which side of the fill it is on — passed, here, or still to
                    come. Remounted on activation so the pop starts from its beginning. */}
                <span
                  key={index === stage ? "reached" : "waiting"}
                  className={cn(
                    "relative rounded-sm bg-[var(--canvas)] px-[3px] py-px font-mono text-meta",
                    "transition-colors duration-300 motion-reduce:transition-none",
                    index === stage
                      ? "about-station-pop font-[650] text-primary"
                      : index < stage
                        ? "text-ink"
                        : "text-ink-3",
                  )}
                >
                  {number}
                </span>
              </span>
            </div>
            {/* The reader's place, marked by ink rather than by a pointer: the stage
                under the eye is at full strength and the others step back a little —
                never below easy legibility, this is emphasis, not a curtain. The prose
                column only: a translucent number cell would let the course show through
                the very digits it is threading. */}
            <div
              className={cn(
                "grid gap-2 transition-opacity duration-300 motion-reduce:transition-none",
                index < STAGES.length - 1 && "pb-9",
                index === stage ? "opacity-100" : "opacity-55",
              )}
            >
              <h3 className="m-0 flex flex-wrap items-center gap-2.5 text-read">
                {name}
                <Lane kind={lane} />
              </h3>
              <p className="m-0 max-w-[62ch] text-body leading-[1.65] text-ink-2">{body}</p>
            </div>
          </li>
        ))}
      </ol>

      {/* Sticky under the app bar, and absent below 1000px rather than stacked: a figure
          that scrolled away from the stages it illustrates would be decoration. */}
      <aside className="max-[999px]:hidden">
        <div className="sticky top-[72px]">
          <RunFigure stage={stage} />
        </div>
      </aside>
    </div>
  );
}

const HONESTY: Array<{ name: string; says: string }> = [
  {
    name: "The whole corpus, every time",
    says:
      "Every judgement sees all the policies. Retrieval was measured against this and lost — " +
      "a shortlist that drops the one policy a boundary turns on is a wrong verdict, not a " +
      "saved token.",
  },
  {
    name: "Nothing the model writes is an identifier",
    says:
      "Policies are presented without their identifiers and answered in a fixed order; " +
      "identity is attached back by position and re-checked after parsing. A misremembered " +
      "policy name cannot corrupt a citation, because names are never read back.",
  },
  {
    name: "Reasoning before conclusion",
    says:
      "Response schemas declare the rationale field before the verdict field. A conclusion " +
      "declared before its reasoning is a conclusion reached before its reasoning.",
  },
  {
    name: "Assumptions are on the record",
    says:
      "When a verdict turns on a circumstance your case did not state, that hinge is " +
      "recorded with the verdict — which is exactly what the question moment exists to " +
      "resolve.",
  },
  {
    name: "Prompts fail loudly, never silently",
    says:
      "Every prompt is measured against the model’s budget before it is sent. Too large " +
      "fails by name, with both sizes — nothing is ever quietly truncated into a different " +
      "question.",
  },
  {
    name: "Retries repair transport, not answers",
    says:
      "A dropped connection is retried with backoff. A malformed answer is not retried " +
      "until it passes: structured output gets one repair round, and then the failure is " +
      "reported as what it is.",
  },
];

/**
 * The method, stated. The front door shows what a verdict looks like; this page says how one
 * is made, and — because trust in an advisor is trust in its constraints — exactly where a
 * model is allowed to speak. Like the front door it reads nothing from the workspace, so it
 * makes the same argument on every machine.
 */
export function AboutPage() {
  return (
    <div className={column}>
      <section className="pt-[clamp(44px,7vh,76px)] pb-[clamp(36px,5vh,56px)]">
        <p className="eyebrow mb-[18px]">The method</p>
        <h1 className="m-0 mb-5 max-w-[24ch] text-[clamp(30px,4vw,44px)] leading-[1.08] font-bold tracking-[-.025em]">
          How a verdict is made
        </h1>
        <p className="m-0 mb-3.5 max-w-[62ch] text-read leading-reading text-ink-2">
          Everything in a review is one of two kinds of work. What can be computed is
          computed: the same repository produces the same atlas and the same candidate
          boundaries, every time. What takes judgement — whether a boundary earns its place,
          given what you are building — goes to a model, and only there, inside constraints
          this page writes down.
        </p>
        <p className="m-0 flex flex-wrap items-center gap-2 text-meta text-ink-3">
          Every stage below is marked as one or the other:
          <Lane kind="computed" />
          <Lane kind="judged" />
        </p>
      </section>

      <section className={cn(band, "py-[clamp(36px,6vh,60px)]")}>
        <h2 className={sectionHead}>The anatomy of a verdict</h2>
        <p className={sectionSub}>
          Every part of a verdict is traceable to the stage that wrote it. Reading one part
          at a time is the fastest way to see how the whole run works.
        </p>
        <p className={specimen}>Specimen verdict, annotated</p>
        <AnatomyFigure />
      </section>

      <section className={cn(band, "py-[clamp(36px,6vh,60px)]")}>
        <h2 className={sectionHead}>The run, stage by stage</h2>
        <p className={sectionSub}>
          Five stages, in the order they happen. The order is the design: judgement runs on
          evidence that deterministic stages prepared, and the record pins exactly what it
          ran against.
        </p>
        <StageWalk />
      </section>

      <section className={cn(band, "py-[clamp(36px,6vh,60px)]")}>
        <h2 className={sectionHead}>What keeps the model honest</h2>
        <p className={sectionSub}>
          An advisor is only as trustworthy as its constraints. These are the ones every
          judged stage runs inside.
        </p>
        <dl className="m-0 grid grid-cols-2 gap-3.5 max-[880px]:grid-cols-1">
          {HONESTY.map(({ name, says }) => (
            <div
              key={name}
              className="grid content-start gap-1.5 rounded-panel border border-rule-soft bg-surface px-[var(--card-pad-x)] py-5 shadow-card"
            >
              <dt className="m-0 text-ui font-[650]">{name}</dt>
              <dd className="m-0 text-ui leading-[1.6] text-ink-2">{says}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className={cn(band, "py-[clamp(36px,6vh,60px)]")}>
        <h2 className={sectionHead}>What is measured, and what is not</h2>
        <div className="grid max-w-[72ch] gap-3">
          <p className="m-0 text-body leading-[1.65] text-ink-2">
            A deterministic test suite drives the whole workflow with a scripted provider. It
            proves that evidence is handled with integrity — that reviews pin their inputs,
            that answers land on the case, that nothing the model writes becomes an
            identifier — and it proves nothing about architectural judgement, because it
            exercises none.
          </p>
          <p className="m-0 text-body leading-[1.65] text-ink-2">
            Judgement is graded separately, against benchmark cases with worked answers: one
            asks whether a boundary absorbs any variation at all — built so that a model
            that always adds abstraction and one that always deletes it both score badly —
            and one asks whether a boundary sits in the right place. No universal
            maintainability score comes out of any of it, because none exists.
          </p>
        </div>
      </section>

      <div className={cn(band, "flex flex-wrap items-center gap-3 pt-[26px] pb-10")}>
        <p className="m-0 mr-auto max-w-[52ch] text-body text-ink-2">
          The fastest way to see all of this at once is to run it — a bundled example
          produces a real review in one click.
        </p>
        <Button asChild variant="primary" className="h-[38px] px-[18px] text-ui">
          <Link to="/start">
            <Play size={14} aria-hidden fill="currentColor" />
            Start a review
          </Link>
        </Button>
        <Button asChild className="h-[38px] px-[18px] text-ui">
          <Link to="/policies">
            <BookOpen size={14} aria-hidden />
            Read the policies
          </Link>
        </Button>
      </div>
    </div>
  );
}
