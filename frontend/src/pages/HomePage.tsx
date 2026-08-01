import { ArrowRight, BookOpen, Download, PenLine, Play, Waypoints } from "lucide-react";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  Citation,
  PosterStripe,
  VERDICT_INK,
  posterCard,
  type Verdict,
} from "@/components/ledger";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { HomeAtlas } from "../home-atlas";
import { JudgingLedger, VerdictBand } from "../review-ledger";
import type { RunState } from "../run-progress";

/* Not `page`: that is 1400px of workbench under a context row, and the front door has no
   context to state. */
const column = "mx-auto w-[min(1120px,100%)] px-[var(--gutter)]";

const band = "border-t border-rule";
const sectionHead = "m-0 mb-1.5 text-[clamp(21px,2.4vw,26px)]";
const sectionSub = "m-0 mb-[26px] max-w-[62ch] text-body leading-[1.6] text-ink-2";

/* Every fabricated section on this page carries one of these, and the specimens must never be
   drawn without it: a made-up verdict passed off as a real one falsifies the exact claim the
   page is here to make. */
const specimen = cn(
  "m-0 mb-2.5 flex items-center gap-2 text-balance font-mono text-micro tracking-[.1em]",
  "text-ink-3 uppercase after:h-px after:flex-1 after:bg-rule after:content-['']",
);

/* A heading inside a panel: small caps with a rule running out to the column's edge. */
const subhead = cn(
  "mt-4 mb-2 flex items-center gap-2 text-micro font-[650] tracking-[.09em] text-ink-3",
  "uppercase after:h-px after:flex-1 after:bg-rule-soft after:content-['']",
);

/* `--lamp-glow` is `none` by day, so this never has to ask which theme is on. */
const verdictSay =
  "m-0 font-display text-head leading-[1.15] font-bold tracking-[-.015em] [text-shadow:var(--lamp-glow)]";

/* Where a boundary sits, and what shape it was found to be. */
const monoWhere = "font-mono text-meta text-ink-3 [overflow-wrap:anywhere]";
const kindChip = cn(
  "rounded-pill border border-rule bg-sunken px-2 py-[3px] font-mono text-micro",
  "tracking-[.07em] whitespace-nowrap text-ink-2 uppercase",
);

/* The one place in this app taller than 34px — read from across the page. */
const heroControl = "h-[38px] px-[18px] text-ui";

const dot = cn(
  "grid size-[22px] cursor-pointer place-items-center rounded-pill border-0 bg-transparent p-0",
  "before:size-[7px] before:rounded-pill before:bg-ink-3 before:opacity-40 before:content-['']",
  "before:transition-[opacity,transform] before:duration-200",
);
const dotOn = "before:scale-125 before:bg-primary before:opacity-100";

type VerdictCard = {
  key: string;
  where: string;
  kind: string;
  say: string;
  why: string;
  cites: string[];
  material: boolean;
};

const verdictOf = (material: boolean): Verdict => (material ? "material" : "cleared");

/**
 * Written for the page, not read from any workspace. They must stay labelled as specimens
 * wherever they are drawn: a fabricated verdict passed off as a real one falsifies the exact
 * claim this page makes.
 */
const SPECIMENS: VerdictCard[] = [
  {
    key: "specimen-port",
    where: "orders/adapters/repository_port.py",
    kind: "indirection hiding nothing",
    say: "Remove the boundary.",
    why:
      "One implementation, one caller, and a signature that repeats the ORM’s own. Every " +
      "change passes through this port unchanged — it costs a hop on every read and buys " +
      "no freedom to vary.",
    cites: ["avoid-pass-through-parameters"],
    material: true,
  },
  {
    key: "specimen-rounding",
    where: "pricing/ · checkout/ · invoicing/",
    kind: "knowledge with no owner",
    say: "Give this knowledge one owner.",
    why:
      "The rounding rule for line totals is restated in three modules. They agree today; " +
      "nothing makes them agree tomorrow. The next price change is a three-file change, " +
      "and someone will make it in two.",
    cites: ["avoid-duplicated-knowledge", "assign-clear-ownership"],
    material: true,
  },
  {
    key: "specimen-gateway",
    where: "billing/ports/payment_gateway.py",
    kind: "boundary examined",
    say: "Leave it exactly as it is.",
    why:
      "Two implementations, a test double, and a provider your case says you have already " +
      "replaced once. This seam is absorbing real change — removing it would spread one " +
      "vendor’s vocabulary through four modules.",
    cites: ["boundary earns its place"],
    material: false,
  },
];

/**
 * One verdict, drawn the way the ledger draws one — as a poster rather than as a row.
 *
 * The stripe, the hue and the citation chips are the ledger's own atoms, composed here at
 * poster size. Nothing about which colour a verdict is, or what it is called, is decided in
 * this file: a specimen on the front door and a finding on a review page must not come out
 * looking like two different kinds of claim, and they cannot, because they are drawn from the
 * same records.
 */
function VerdictPoster({
  card,
  className,
  say = verdictSay,
  children,
}: {
  card: VerdictCard;
  className?: string;
  /** The verdict's own line, one step down where the card is not the page's centrepiece. */
  say?: string;
  /** What this particular poster states between the shape and the verdict, if anything. */
  children?: ReactNode;
}) {
  const verdict = verdictOf(card.material);
  return (
    <article className={cn(posterCard, "rounded-panel", className)}>
      <PosterStripe verdict={verdict} />
      <div className="grid gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className={monoWhere}>{card.where}</span>
          <span className={kindChip}>{card.kind}</span>
        </div>
        {children}
        <p className={cn(say, VERDICT_INK[verdict])}>{card.say}</p>
        <p className="m-0 line-clamp-4 text-ui leading-[1.6] text-ink-2">{card.why}</p>
        {card.cites.length ? (
          <div className="mt-0.5 flex flex-wrap gap-1.5">
            {card.cites.map((cite) => (
              <Citation key={cite}>{cite}</Citation>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/** Three verdicts in one card's worth of space, one at a time. */
function VerdictStack({ cards }: { cards: VerdictCard[] }) {
  const [showing, setShowing] = useState(0);
  const [held, setHold] = useState(false);

  useEffect(() => {
    if (held || cards.length < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(
      () => setShowing((index) => (index + 1) % cards.length),
      7000,
    );
    return () => window.clearInterval(timer);
  }, [cards.length, held]);

  return (
    <div
      data-slot="verdict-stack"
      onMouseEnter={() => setHold(true)}
      onMouseLeave={() => setHold(false)}
      // React's focus events bubble, so this is `:focus-within` without a wrapper class.
      onFocus={() => setHold(true)}
      onBlur={() => setHold(false)}
    >
      <p className={specimen}>Specimen verdicts — run a bundled example to write your own</p>
      {/* Stacked in one cell, so the block is as tall as the tallest of the three and never
          changes height as it turns. */}
      <div className="grid">
        {cards.map((card, index) => (
          <VerdictPoster
            key={card.key}
            card={card}
            className={cn(
              "[grid-area:1/1] pt-[22px] pr-6 pb-5 pl-[18px] shadow-panel",
              "transition-[opacity,visibility] duration-[550ms] ease-out motion-reduce:transition-none",
              index === showing ? "visible opacity-100" : "invisible opacity-0",
            )}
          />
        ))}
      </div>
      {cards.length > 1 ? (
        <div
          role="group"
          aria-label="Choose a verdict"
          className="mt-3.5 flex justify-center gap-2"
        >
          {cards.map((card, index) => (
            <button
              key={card.key}
              type="button"
              className={cn(dot, index === showing && dotOn)}
              aria-label={`Verdict ${index + 1}`}
              aria-current={index === showing || undefined}
              onClick={() => setShowing(index)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** One of the three things a judgement is made of. */
function Material({
  icon: Icon,
  name,
  tag,
  children,
}: {
  icon: typeof Waypoints;
  name: string;
  tag: string;
  children: ReactNode;
}) {
  return (
    <div className="grid content-start gap-2 rounded-panel border border-rule-soft bg-surface px-[22px] py-5 shadow-card">
      <h3 className="m-0 flex items-center gap-[9px] text-read">
        <Icon size={15} aria-hidden className="flex-none text-primary" />
        {name}
      </h3>
      <p className="m-0 text-ui leading-[1.6] text-ink-2">{children}</p>
      <span className="font-mono text-micro text-ink-3">{tag}</span>
    </div>
  );
}

function Answer({
  verdict,
  say,
  children,
}: {
  verdict: Verdict;
  say: string;
  children: ReactNode;
}) {
  return (
    <div className={cn(posterCard, "rounded-panel pt-4 pr-5 pb-4 pl-3.5 shadow-card")}>
      <PosterStripe verdict={verdict} />
      <div className="grid gap-[3px]">
        <h3 className={cn("m-0 text-read", VERDICT_INK[verdict])}>{say}</h3>
        <p className="m-0 text-ui leading-[1.55] text-ink-2">{children}</p>
      </div>
    </div>
  );
}

/* ── The run, replayed ────────────────────────────────────────────────────────
   Five boundaries judged one at a time, into the two instruments a real run fills: the band
   that states the counts and the ledger that lists every boundary the sweep found. Both are
   the app's own components, driven by a `RunState` written out below rather than streamed —
   which is what the specimen line over them says out loud. The verdicts never change; the
   only thing that moves is how far the run has got.
   ──────────────────────────────────────────────────────────────────────────── */

type Judged = VerdictCard & { name: string; bearings: string };

const REPLAY: Judged[] = [
  {
    key: "BR-001",
    name: "orders.adapters.RepositoryPort",
    where: "orders/adapters/repository_port.py",
    kind: "indirection hiding nothing",
    say: "Remove the boundary.",
    why:
      "One implementation, one caller, and a signature that repeats the ORM’s own. Every " +
      "change passes through this port unchanged.",
    cites: ["avoid-pass-through-parameters"],
    bearings: "3/53",
    material: true,
  },
  {
    key: "BR-002",
    name: "pricing.rounding.line_total",
    where: "pricing/ · checkout/ · invoicing/",
    kind: "knowledge with no owner",
    say: "Give this knowledge one owner.",
    why:
      "The rounding rule for line totals is restated in three modules. They agree today; " +
      "nothing makes them agree tomorrow.",
    cites: ["avoid-duplicated-knowledge", "assign-clear-ownership"],
    bearings: "2/53",
    material: true,
  },
  {
    key: "BR-003",
    name: "billing.ports.PaymentGateway",
    where: "billing/ports/payment_gateway.py",
    kind: "boundary examined",
    say: "Leave it exactly as it is.",
    why:
      "Two implementations, a test double, and a provider your case says you have already " +
      "replaced once. This seam is absorbing real change.",
    cites: ["keep-vendor-vocabulary-contained"],
    bearings: "4/53",
    material: false,
  },
  {
    key: "BR-004",
    name: "notifications.EmailSenderFactory",
    where: "notifications/factory.py",
    kind: "generality with no second case",
    say: "Collapse the factory into its one product.",
    why:
      "A factory with one product, selected by a constant. The second sender it was built " +
      "for is named in no case, no test and no branch.",
    cites: ["avoid-speculative-generality"],
    bearings: "2/53",
    material: true,
  },
  {
    key: "BR-005",
    name: "catalog.search.QueryBuilder",
    where: "catalog/search/query_builder.py",
    kind: "boundary examined",
    say: "Leave it exactly as it is.",
    why:
      "Every filter the catalogue offers is added here and nowhere else. Removing it would " +
      "put SQL fragments in four request handlers.",
    cites: ["contain-change-amplification"],
    bearings: "3/53",
    material: false,
  },
];

/**
 * A step every 2.7 seconds, with two extra steps at the end: once every verdict has landed
 * there is nothing under the model, so the finished ledger and its map are held for a beat
 * before the run starts over.
 */
export const REPLAY_STEPS = [1, 2, 3, 4, 5, 5, 5];
export const REPLAY_INTERVAL_MS = 2700;
/**
 * Where a reader who has asked for less motion finds the run: two verdicts landed and a third
 * under the model. It is the one position that draws all four kinds of row at once, so the
 * still picture says everything the moving one does.
 */
export const REPLAY_STILL = 2;

function useReplay() {
  // Read once, at the first paint, because it decides the position the run is *drawn* in and
  // not only whether it moves: a page that started at step one and then stopped would be a
  // different picture from the one this chooses.
  const [still] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [step, setStep] = useState(0);
  const [held, setHold] = useState(false);

  useEffect(() => {
    if (still || held) return;
    const timer = window.setInterval(
      () => setStep((at) => (at + 1) % REPLAY_STEPS.length),
      REPLAY_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
  }, [still, held]);

  return { judged: still ? REPLAY_STILL : REPLAY_STEPS[step], held, setHold };
}

function Replay() {
  const { judged, held, setHold } = useReplay();
  const material = REPLAY.slice(0, judged).filter((item) => item.material).length;
  const landed = REPLAY[judged - 1];

  const progress: RunState = {
    total: REPLAY.length,
    boundaries: REPLAY.map((item) => item.name),
    verdicts: REPLAY.map((item, index) => (index < judged ? item.material : null)),
    judged,
    eliciting: false,
    summarising: false,
    concluded: false,
  };

  return (
    <>
      {/* A fabricated run drawn without this line would falsify the page's own claim. */}
      <p className={specimen}>Specimen run — run a bundled example to write your own</p>

      <VerdictBand
        material={material}
        cleared={judged - material}
        judged={judged}
        total={REPLAY.length}
        mode="live"
        facts={[
          { label: "repository", value: "your-repository" },
          { label: "case", value: "revision 2" },
          { label: "policies", value: "53" },
        ]}
      />

      {/* No live region anywhere in here, deliberately. This is a loop with nothing at stake,
          and a reader told every 2.7 seconds that another specimen verdict has landed is being
          interrupted by a picture. The ledger is this section's accessible text and it is read
          when the reader reaches it, like every other passage on the page.

          Held while the pointer is over it or something inside it has focus. `data-held` is
          what stops the map: the comet, the breathing node and its ring are CSS animations,
          and no JavaScript interval reaches them. */}
      <div
        data-slot="run-replay"
        className="home-replay grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] items-start gap-[22px] max-[880px]:grid-cols-1"
        data-held={held || undefined}
        onMouseEnter={() => setHold(true)}
        onMouseLeave={() => setHold(false)}
        onFocus={() => setHold(true)}
        onBlur={() => setHold(false)}
      >
        <HomeAtlas
          judged={judged}
          material={REPLAY.map((item) => item.material)}
          bearings={REPLAY.map((item) => item.bearings)}
        />

        <div className="grid">
          <JudgingLedger
            progress={progress}
            bearings={REPLAY.map((item) => item.bearings)}
            foot={
              <>
                Cleared boundaries keep their rows: a ledger that listed only problems would
                read identically whether five boundaries were examined and cleared or none
                ever was. <code>BR-001</code> and the rest are references ArchCompass assigns
                in detection order.
              </>
            }
          />

          <div>
            <p className={subhead}>The verdict that just landed</p>
            <VerdictPoster
              card={landed}
              className="pt-[18px] pr-5 pb-[18px] pl-4 shadow-card"
              say={cn(verdictSay, "text-sub")}
            />
          </div>
        </div>
      </div>
    </>
  );
}

/* ── The course's own furniture ───────────────────────────────────────────────
   Spans and paths with nothing in them but geometry, all of it drawn in `styles.css` and none
   of it below 1260px. Every piece is `aria-hidden` and takes no tab stop: the course restates
   as a line what the sections already say in words.
   ──────────────────────────────────────────────────────────────────────────── */

/** What staggers one section's comet against the next one's. */
const courseDelay = (delay: string) =>
  ({ "--course-pulse-delay": delay }) as CSSProperties;

/**
 * Where the course crosses a section's rule, and the segment running down from it.
 *
 * The comet is a sibling of the rail rather than a child: the rail is scaled on its own Y axis
 * as it draws itself, and a head inside it would be squashed by that same transform.
 */
function Waypoint({ pulse }: { pulse: string }) {
  return (
    <>
      <span aria-hidden className="course-tick" />
      <span aria-hidden className="course-rail" />
      <span aria-hidden className="course-pulse" style={courseDelay(pulse)} />
    </>
  );
}

/** The fork: off the rail, into the accent border of the block the reader's answer changed. */
function ForkIn() {
  return (
    <svg
      aria-hidden
      className="course-elbow course-elbow--in"
      viewBox="0 0 34 24"
      preserveAspectRatio="none"
    >
      <path pathLength={1} d="M 1 0 C 1 13, 12 21, 34 21" />
    </svg>
  );
}

/** And back out under it. */
function ForkOut() {
  return (
    <svg
      aria-hidden
      className="course-elbow course-elbow--out"
      viewBox="0 0 34 24"
      preserveAspectRatio="none"
    >
      <path pathLength={1} d="M 34 3 C 12 3, 1 11, 1 24" />
    </svg>
  );
}

/**
 * The front door: what this tool is, and what one of its verdicts looks like. Not the start
 * step, which is at `/start`. Deliberately reads nothing from the workspace, so it draws the
 * same argument on the first paint whatever this machine has judged.
 *
 * Three things run down the left of it on a wide screen, and all three are decorative: the
 * ground the sections stand on, the course plotted through them, and the comet travelling each
 * of the course's segments. They are drawn in `styles.css`, where the constraints they turn on
 * are written down — the full-bleed's clip pairing, the fan that replaces the stem, and the
 * elbow whose offsets resolve against a padding box.
 */
export function HomePage() {
  return (
    <div className={column}>
      <section className="home-hero grid grid-cols-[minmax(0,5fr)_minmax(0,4fr)] items-center gap-[clamp(28px,4vw,56px)] pt-[clamp(48px,8vh,88px)] pb-[clamp(40px,6vh,64px)] max-[880px]:grid-cols-1">
        <div>
          <p className="eyebrow mb-[18px]">Software architecture advisor</p>
          <h1 className="m-0 mb-5 text-[clamp(34px,4.6vw,52px)] leading-[1.06] font-bold tracking-[-.025em]">
            Verdicts with reasoning, <span className="text-ink-3">not lint.</span>
          </h1>
          <p className="m-0 mb-7 max-w-[46ch] text-read leading-reading text-ink-2">
            ArchCompass reads the boundaries in an existing repository — the abstractions,
            ports and indirections — and decides, one at a time, whether each is earning its
            place given what you are actually building.
          </p>
          <div className="flex flex-wrap items-center gap-2.5">
            <Button asChild variant="primary" className={heroControl}>
              <Link to="/start">
                <Play size={14} aria-hidden fill="currentColor" />
                Start a review
              </Link>
            </Button>
            <Button asChild className={heroControl}>
              <Link to="/policies">Read the policies</Link>
            </Button>
            <p className="m-0 mt-1.5 basis-full text-meta text-ink-3">
              A bundled example fills everything in one click — a fresh workspace produces a
              real review immediately.
            </p>
          </div>
        </div>

        <VerdictStack cards={SPECIMENS} />
      </section>

      <section className={cn(band, "course-host py-[clamp(30px,5vh,52px)]")}>
        <Waypoint pulse="0s" />
        <p className="m-0 max-w-[62ch] font-display text-[clamp(19px,2.3vw,25px)] leading-[1.45] font-[460] tracking-[-.012em] text-ink">
          AI-assisted coding made working code cheap. What it left untouched is the hard
          problem — <strong className="font-bold">containing complexity</strong>: every
          abstraction added “to be safe,” every port with one implementation, every rule
          restated where it was needed.{" "}
          <span className="text-ink-3">
            ArchCompass exists to judge that structure, boundary by boundary, and to say so
            with evidence.
          </span>
        </p>
      </section>

      <section className={cn(band, "course-host pt-[clamp(36px,6vh,60px)]")}>
        <Waypoint pulse=".9s" />
        <h2 className={sectionHead}>One judgement, three materials</h2>
        <p className={sectionSub}>
          Three structural detectors surface every candidate boundary; a model then judges
          each one against everything below. Nothing is scored, nothing is averaged — each
          boundary gets its own verdict, in writing.
        </p>
        <div className="grid grid-cols-3 gap-3.5 max-[880px]:grid-cols-1">
          <Material icon={Waypoints} name="The atlas" tag="objective structure">
            A deterministic map of your repository — modules, boundaries, dependencies —
            parsed without importing or running your code. Same repository, same atlas, every
            time.
          </Material>
          <Material icon={PenLine} name="The case" tag="your intent">
            Prose about what this software actually has to do — scale, team, what changes
            often, what must not break. The same port is dead weight in one case and
            load-bearing in another.
          </Material>
          <Material icon={BookOpen} name="The policies" tag="normative guidance">
            Fifty-three standing policies on ownership, indirection and change amplification.
            Every verdict cites the ones it leaned on, so the reasoning can be checked, not
            just believed.
          </Material>
        </div>

        <div className="grid justify-items-center">
          {/* Three materials, one judgement: the section's thesis, drawn as a line. In flow,
              so it survives every column width without measuring anything. */}
          {/* The viewBox is 1000 wide, not 100: the fan only exists at ≥1260px where the
              column is capped, so a near-width user space keeps the stretch close to 1:1 —
              which is what lets the comets' dash arithmetic (normalized to pathLength) and
              their round caps survive `preserveAspectRatio="none"`. */}
          <svg
            aria-hidden
            className="course-converge"
            viewBox="0 0 1000 56"
            preserveAspectRatio="none"
          >
            <path pathLength={1} d="M 167 0 C 167 22, 500 16, 500 40" />
            <path pathLength={1} d="M 500 0 C 500 16, 500 24, 500 40" />
            <path pathLength={1} d="M 833 0 C 833 22, 500 16, 500 40" />
            <path pathLength={1} className="course-converge__stub" d="M 500 40 L 500 56" />
            {/* The same four paths again as wires for the comets: overlays, so the pulse
                can be a dash without the lines beneath ever being dashed themselves. */}
            <path pathLength={100} className="course-converge__pulse" d="M 167 0 C 167 22, 500 16, 500 40" />
            <path pathLength={100} className="course-converge__pulse" d="M 500 0 C 500 16, 500 24, 500 40" />
            <path pathLength={100} className="course-converge__pulse" d="M 833 0 C 833 22, 500 16, 500 40" />
            <path pathLength={100} className="course-converge__pulse course-converge__pulse--stub" d="M 500 40 L 500 56" />
          </svg>
          <span aria-hidden className="course-stem h-[34px] w-px bg-rule" />
          <div className="flex w-full flex-wrap items-center gap-x-[18px] gap-y-3 rounded-panel border border-rule-soft bg-surface px-[22px] py-4 shadow-card">
            <p className="m-0 flex-[1_1_32ch] text-ui text-ink-2 [&_strong]:font-[650] [&_strong]:text-ink">
              Judging every boundary in <strong>your-repository</strong> against{" "}
              <strong>your case</strong>. This opens the review and follows it there.
            </p>
            {/* A picture of the control, not the control — but drawn by the real button, so
                it cannot drift from the one the start step shows. */}
            <Button
              asChild
              variant="primary"
              className={cn(heroControl, "pointer-events-none")}
            >
              <span aria-hidden>
                <Play size={14} fill="currentColor" />
                Run review
              </span>
            </Button>
          </div>
        </div>

        <div className="home-run-field mt-[clamp(36px,6vh,56px)] pt-[clamp(30px,5vh,48px)] pb-[clamp(34px,5vh,52px)]">
          <h2 className={sectionHead}>The Run</h2>
          <p className={sectionSub}>
            A review is watched rather than waited on. Every boundary the sweep found is
            listed before any of them is judged, and each verdict lands in two places at once
            — the ledger it is written into, and the map of the repository it is about.
          </p>
          <Replay />
        </div>
      </section>

      <section className={cn(band, "course-host py-[clamp(36px,6vh,60px)]")}>
        <Waypoint pulse="1.8s" />
        <h2 className={sectionHead}>The question moment</h2>
        <p className={sectionSub}>
          A review pauses when the code cannot answer for itself. Your answers become part of
          the case, verdicts they move are re-judged on the next pass, and the ledger
          attributes every change to the answer that caused it.
        </p>

        <p className={specimen}>Specimen question — run a bundled example to write your own</p>

        <div className="max-w-[82ch] rounded-panel border border-accent-rule bg-accent-soft p-[var(--card-pad)]">
          <p className="m-0 mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-read leading-[1.5] font-semibold">
            <code className="rounded-pill border border-accent-rule bg-surface px-2 py-px font-mono text-meta font-normal tracking-[.04em] text-accent-ink">
              Q-2
            </code>
            Is the duplication between <code>pricing/</code> and <code>invoicing/</code>{" "}
            deliberate?
          </p>
          <p className="m-0 mb-2 max-w-[78ch] text-body leading-[1.65] text-ink-2">
            The rounding rule for line totals is written out three times — in{" "}
            <code>pricing/rounding.py</code>, <code>checkout/totals.py</code> and{" "}
            <code>invoicing/line_item.py</code>. The three agree today, and nothing in the
            repository makes them agree tomorrow.
          </p>
          <p className="m-0 mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-ui leading-[1.6] text-ink-2">
            <span>
              If the copies are held apart on purpose, this is a boundary earning its place
              rather than knowledge with no owner — and the verdict comes out the other way.
            </span>
            <span className="flex flex-wrap gap-1.5">
              <Citation>BR-002</Citation>
              <Citation>BR-005</Citation>
            </span>
          </p>

          <span className="mt-3 mb-1 block text-meta text-ink-3">
            Your answer — something you know to be settled (<code>confirmed_facts</code>)
          </span>
          {/* The reader's own words, in the shape this product gives them. */}
          <p className="m-0 max-w-[62ch] justify-self-start rounded-panel rounded-bl-control bg-sunken px-3 py-2 text-ui leading-[1.55] text-ink">
            Deliberate. <code>invoicing/</code> is frozen by the tax contract and may not
            follow a pricing change; <code>checkout/</code> mirrors whatever pricing does
            within a release. Only <code>pricing/rounding.py</code> changes when the pricing
            model does.
          </p>
        </div>

        {/* What the reader's own answer did, in the ledger's own language. Ruled down its
            accent side, because this is a result about the page rather than one more panel on
            it — and on a wide screen that rule is the course's own segment through it. */}
        <div className="home-changed mt-[var(--gap-lg)] rounded-panel border-l-[3px] border-l-primary bg-surface p-[var(--card-pad)] shadow-card [border-block:var(--sheet-border)] [border-right:var(--sheet-border)]">
          <ForkIn />
          <ForkOut />
          <p className="m-0 mb-3.5 flex items-start gap-2 text-body leading-reading">
            <ArrowRight size={15} aria-hidden className="mt-1 flex-none text-accent-ink" />
            <span>
              <strong>1 of 5 verdicts changed</strong> because of what you answered. Same
              repository, same atlas, same model — the only difference between the two passes
              is what the case now says.
            </span>
          </p>

          <VerdictPoster
            card={{
              key: "BR-002-again",
              where: "pricing/ · checkout/ · invoicing/",
              kind: "re-judged on the answered case",
              say: "Leave it exactly as it is.",
              why:
                "The three copies are held apart by release, not by oversight. One owner " +
                "would couple a tax contract to a pricing change, which is the " +
                "amplification this duplication was put there to prevent.",
              cites: ["avoid-duplicated-knowledge", "respect-release-boundaries"],
              material: false,
            }}
            className="pt-[18px] pr-[22px] pb-[18px] pl-4 shadow-card"
          >
            <p className="m-0 flex flex-wrap items-center gap-1.5 font-mono text-meta text-ink-3">
              <span>was</span>{" "}
              <b className="font-[550] text-material">Give this knowledge one owner.</b>
            </p>
          </VerdictPoster>

          <ul className="m-0 mt-3.5 grid list-none gap-1 border-l-2 border-accent-rule pl-3">
            <li>
              <span className="block text-ui leading-[1.55] text-ink-3">
                Asked: Is the duplication between <code>pricing/</code> and{" "}
                <code>invoicing/</code> deliberate?
              </span>
              <span className="block text-ui leading-[1.55] text-ink-2">
                Deliberate. <code>invoicing/</code> is frozen by the tax contract and may not
                follow a pricing change; <code>checkout/</code> mirrors whatever pricing does
                within a release.
              </span>
            </li>
          </ul>

          <p className="m-0 mt-3.5 max-w-[78ch] text-meta leading-[1.55] text-ink-3">
            Both passes remain readable, each pinned to the case revision it ran against, so
            the verdict that moved can be read against the one it replaced.
          </p>
        </div>
      </section>

      <section className={cn(band, "course-host py-[clamp(36px,6vh,60px)]")}>
        <Waypoint pulse="2.7s" />
        <h2 className={sectionHead}>Three answers, all first-class</h2>
        <p className={sectionSub}>
          An advisor that only ever recommends change is an advocate, not a judge. “Nothing to
          change here” is a verdict ArchCompass writes down, signs with reasoning, and stands
          behind.
        </p>
        <div className="grid gap-2.5">
          <Answer verdict="material" say="Remove the boundary">
            An indirection that hides nothing costs a hop on every read and a file on every
            change.
          </Answer>
          <Answer verdict="material" say="Give this knowledge one owner">
            A rule restated in three places will, one day, be updated in two.
          </Answer>
          <Answer verdict="cleared" say="Leave it exactly as it is">
            A seam that has already absorbed a provider swap is earning its keep — and the
            review says so, on the record.
          </Answer>
        </div>
        <p className="mt-[18px] mb-0 text-ui text-ink-3 italic">
          Boundaries examined and cleared are part of the record, not silence.
        </p>
      </section>

      <section className={cn(band, "home-record-field course-host py-[clamp(30px,5vh,48px)]")}>
        {/* The last segment, and the destination fix it was always headed for. */}
        <span aria-hidden className="course-rail course-rail--end" />
        <span
          aria-hidden
          className="course-pulse course-pulse--end"
          style={courseDelay("3.3s")}
        />
        <span aria-hidden className="course-end" />
        <h2 className={sectionHead}>The record</h2>
        <p className={sectionSub}>
          A finished review is a file. It is written once, when the run concludes, and never
          rewritten — pinned to the case revision it ran against, so re-running is a second
          record rather than a correction of the first.
        </p>

        <p className={specimen}>Specimen report — run a bundled example to write your own</p>

        <div className="overflow-hidden rounded-panel border border-rule bg-surface shadow-card">
          <div className="flex flex-wrap items-center gap-2.5 border-b border-rule bg-sunken px-[var(--row-pad-x)] py-2.5">
            <span className="min-w-0 overflow-hidden font-mono text-meta text-ellipsis whitespace-nowrap text-ink-2">
              archcompass-review-2026-07-31-a41c9e.md
            </span>
            {/* A picture of the export control, drawn by the real button for the same reason
                the run control above is. */}
            <Button asChild className="pointer-events-none ml-auto">
              <span aria-hidden>
                <Download size={14} />
                Export Markdown
              </span>
            </Button>
          </div>
          {/* The report's own prose, in the styles the app renders a report in — with the
              specimen's own measure and the fade that says it goes on. */}
          <div className="home-doc markdown">
            <h1>Review — your-repository</h1>
            <p className="font-mono text-meta text-ink-3 [overflow-wrap:anywhere]">
              3f9c1ab · case revision 2 · 53 policies · run 2 of 2 · concluded 31 Jul 2026,
              14:08
            </p>
            <p>
              Five boundaries were examined. Three should change, two earn their place. Both
              passes are kept: this one is pinned to case revision 2, the first to revision 1.
            </p>
            <h2>BR-002 — pricing.rounding.line_total</h2>
            <p>
              <strong>Earns its place.</strong> The rounding rule for line totals is restated
              in <code>pricing/rounding.py</code>, <code>checkout/totals.py</code> and{" "}
              <code>invoicing/line_item.py</code>. The case says the three are held apart by
              release: only <code>pricing/</code> changes when the pricing model does.
            </p>
            <p>
              Bearings — 2 of 53 policies bear on this boundary:{" "}
              <code>avoid-duplicated-knowledge</code>,{" "}
              <code>respect-release-boundaries</code>.
            </p>
            <p>
              Changed from <em>should change</em> on run 1, by the answer recorded against
              Q-2.
            </p>
            <h2>BR-003 — billing.ports.PaymentGateway</h2>
            <p>
              <strong>Earns its place.</strong> Two implementations, a test double, and a
              provider the case says has already been replaced once.
            </p>
          </div>
        </div>
        <p className="mt-3.5 mb-0 max-w-[78ch] text-meta leading-[1.55] text-ink-3">
          Nothing is recalculated when the file is opened, and nothing about it changes when
          the repository does. Reading a review only reads.
        </p>
      </section>

      <div className={cn(band, "mt-2 pt-[26px] pb-10")}>
        <ul className="m-0 mb-[18px] flex list-none flex-wrap gap-x-[26px] gap-y-2 p-0 font-mono text-micro text-ink-3">
          {[
            "bring your own model — Gemini or Ollama",
            "reviews are immutable records",
            "every verdict carries its reasoning",
            "Python repositories · V1",
          ].map((fact) => (
            <li
              key={fact}
              className="flex items-center gap-[7px] before:size-[5px] before:rounded-pill before:bg-primary before:opacity-60 before:content-['']"
            >
              {fact}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center justify-between gap-3 text-meta text-ink-3">
          <span>
            Open the workspace: <code className="font-mono">archcompass web</code>
          </span>
          <span>ArchCompass — a workspace for architectural judgement.</span>
        </div>
      </div>
    </div>
  );
}
