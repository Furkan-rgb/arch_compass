import { BookOpen, PenLine, Play, Waypoints } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* Not `page`: that is 1400px of workbench under a context row, and the front door has no
   context to state. */
const column = "mx-auto w-[min(1120px,100%)] px-[var(--gutter)]";

const band = "border-t border-rule";
const sectionHead = "m-0 mb-1.5 text-[clamp(21px,2.4vw,26px)]";
const sectionSub = "m-0 mb-[26px] max-w-[62ch] text-body leading-[1.6] text-ink-2";

const stripe = "self-stretch rounded-[99px]";
const cardShell =
  "grid grid-cols-[4px_minmax(0,1fr)] gap-x-4 border border-rule-soft bg-surface";

/* `--lamp-glow` is `none` by day, so this never has to ask which theme is on. */
const verdictSay =
  "m-0 font-display text-head leading-[1.15] font-bold tracking-[-.015em] [text-shadow:var(--lamp-glow)]";

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

/** One verdict, drawn the way the ledger draws one. */
function Verdict({ card, showing }: { card: VerdictCard; showing: boolean }) {
  return (
    <article
      aria-hidden={!showing}
      className={cn(
        cardShell,
        "[grid-area:1/1] rounded-panel pt-[22px] pr-6 pb-5 pl-[18px] shadow-panel",
        "transition-[opacity,visibility] duration-[550ms] ease-out motion-reduce:transition-none",
        showing ? "visible opacity-100" : "invisible opacity-0",
      )}
    >
      <span
        aria-hidden
        className={cn(stripe, card.material ? "bg-material" : "bg-cleared")}
      />
      <div className="grid gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-meta text-ink-3 [overflow-wrap:anywhere]">
            {card.where}
          </span>
          <span className="rounded-pill border border-rule bg-sunken px-2 py-[3px] font-mono text-micro tracking-[.07em] whitespace-nowrap text-ink-2 uppercase">
            {card.kind}
          </span>
        </div>
        <p className={cn(verdictSay, card.material ? "text-material" : "text-cleared")}>
          {card.say}
        </p>
        <p className="m-0 line-clamp-4 text-ui leading-[1.6] text-ink-2">{card.why}</p>
        {card.cites.length ? (
          <div className="mt-0.5 flex flex-wrap gap-1.5">
            {card.cites.map((cite) => (
              <span
                key={cite}
                className="rounded-pill border border-accent-rule bg-accent-soft px-[9px] py-[3px] font-mono text-micro text-accent-ink"
              >
                {cite}
              </span>
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
      onMouseEnter={() => setHold(true)}
      onMouseLeave={() => setHold(false)}
      // React's focus events bubble, so this is `:focus-within` without a wrapper class.
      onFocus={() => setHold(true)}
      onBlur={() => setHold(false)}
    >
      {/* The specimens must never be drawn without this line. */}
      <p className="m-0 mb-2.5 flex items-center gap-2 text-balance font-mono text-micro tracking-[.1em] text-ink-3 uppercase after:h-px after:flex-1 after:bg-rule after:content-['']">
        Specimen verdicts — run a bundled example to write your own
      </p>
      <div className="grid">
        {cards.map((card, index) => (
          <Verdict key={card.key} card={card} showing={index === showing} />
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
  verdict: "material" | "cleared";
  say: string;
  children: ReactNode;
}) {
  const material = verdict === "material";
  return (
    <div
      className={cn(cardShell, "rounded-panel pt-4 pr-5 pb-4 pl-3.5 shadow-card")}
    >
      <span aria-hidden className={cn(stripe, material ? "bg-material" : "bg-cleared")} />
      <div className="grid gap-[3px]">
        <h3 className={cn("m-0 text-read", material ? "text-material" : "text-cleared")}>
          {say}
        </h3>
        <p className="m-0 text-ui leading-[1.55] text-ink-2">{children}</p>
      </div>
    </div>
  );
}

/**
 * The front door: what this tool is, and what one of its verdicts looks like. Not the start
 * step, which is at `/start`. Deliberately reads nothing from the workspace, so it draws the
 * same argument on the first paint whatever this machine has judged.
 */
export function HomePage() {
  return (
    <div className={column}>
      <section className="grid grid-cols-[minmax(0,5fr)_minmax(0,4fr)] items-center gap-[clamp(28px,4vw,56px)] pt-[clamp(48px,8vh,88px)] pb-[clamp(40px,6vh,64px)] max-[880px]:grid-cols-1">
        <div>
          <p className="eyebrow mb-[18px]">Local-first architecture advisor</p>
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

      <section className={cn(band, "py-[clamp(30px,5vh,52px)]")}>
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

      <section className={cn(band, "pt-[clamp(36px,6vh,60px)]")}>
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
          <span aria-hidden className="h-[34px] w-px bg-rule" />
          <div className="flex w-full flex-wrap items-center gap-x-[18px] gap-y-3 rounded-panel border border-rule-soft bg-surface px-[22px] py-4 shadow-card">
            <p className="m-0 flex-[1_1_32ch] text-ui text-ink-2 [&_strong]:font-[650] [&_strong]:text-ink">
              Judging every boundary in <strong>your-repository</strong> against{" "}
              <strong>your case</strong>. This opens the review and follows it there.
            </p>
            {/* A picture of the control, not the control — but drawn by the real button, so
                it cannot drift from the one the start step shows. */}
            <Button asChild variant="primary" className={cn(heroControl, "pointer-events-none")}>
              <span aria-hidden>
                <Play size={14} fill="currentColor" />
                Run review
              </span>
            </Button>
          </div>
        </div>

        <div
          className={cn(
            band,
            "mt-[clamp(36px,6vh,56px)] grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-start gap-x-12 gap-y-6 py-[clamp(28px,4vh,40px)] max-[880px]:grid-cols-1",
          )}
        >
          <h2 className={cn(sectionHead, "mb-0")}>It asks before it judges</h2>
          <p className="m-0 max-w-[58ch] text-body leading-reading text-ink-2">
            A review pauses when the code cannot answer for itself —{" "}
            <strong className="font-[650] text-ink">
              is this duplication deliberate? does anything else write this table?
            </strong>{" "}
            Your answers become part of the case, verdicts they move are re-judged on the next
            pass, and the ledger attributes every change to the answer that caused it.
          </p>
        </div>
      </section>

      <section className={cn(band, "py-[clamp(36px,6vh,60px)]")}>
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

      <div className={cn(band, "mt-2 pt-[26px] pb-10")}>
        <ul className="m-0 mb-[18px] flex list-none flex-wrap gap-x-[26px] gap-y-2 p-0 font-mono text-micro text-ink-3">
          {[
            "runs on 127.0.0.1 — nothing leaves your machine",
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
          <span>ArchCompass — a local workspace, not a service.</span>
        </div>
      </div>
    </div>
  );
}
