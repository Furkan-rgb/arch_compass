import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { Wordmark } from "../../ui/brand";
import { Button, ButtonLink } from "../../ui/button";
import { Drawer } from "../../ui/drawer";
import {
  ArrowRight,
  ChevronDown,
  GithubIcon,
  MenuIcon,
  MonitorIcon,
  MoonIcon,
  SunIcon,
} from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Reveal } from "../../ui/reveal";
import { CorpusCard } from "./corpus-card";
import { Field } from "./field";

/**
 * The landing page.
 *
 * Its thesis is guidance. The hero is not a picture of the workbench and not an instrument
 * — it is the corpus doing its job: a policy somebody wrote, and the finding it produced.
 * That is the one thing this product can show that nothing else can, and it needs no score
 * to show it, which matters because the domain has no score to give.
 *
 * The chrome here is deliberately not the app's chrome. `AppShell` is a sidebar and a
 * topbar because the workbench is a tool somebody works inside; a marketing page is read
 * top to bottom and wants a horizontal nav and a footer. What the two share is what should
 * be shared: the wordmark, the tokens, the type and the buttons.
 */

const SECTIONS = [
  { id: "intent", label: "Unwritten intent" },
  { id: "how", label: "How it works" },
  { id: "finding", label: "A finding" },
  { id: "refusals", label: "What it isn't" },
];

/** Six steps on one rule, and which of the three jobs owns each. */
const STEPS = [
  ["Repository", "Parsed, never imported and never run.", "Machine"],
  ["Atlas", "A deterministic map: nodes, edges, metrics, obscurity signals.", "Machine"],
  ["Candidate", "A structural shape that deserves judgement — not a violation.", "Machine"],
  ["Guidance", "Retrieved per candidate, with the retriever and corpus recorded.", "Machine"],
  ["Finding", "The model says what the evidence means, inside the guidance it was given.", "Model"],
  [
    "Decision",
    "Accept, park or waive — recorded against the branch, and it survives the rerun.",
    "Person",
  ],
] as const;

/** The charter's four refusals, in its own words. Each is a plausible direction that would break it. */
const REFUSALS = [
  [
    "Not a linter",
    "A candidate is a structural shape that deserves judgement, not a violation. If it could be decided by a rule, it should be a rule, in someone's linter.",
  ],
  [
    "Not a code generator",
    "ArchCompass does not write the fix. It can recommend a response; acting on it is yours.",
  ],
  [
    "Not an autonomous agent",
    "It does not roam the repository, choose its own goals, or act without being asked. The model never picks which elements to inspect.",
  ],
  [
    "Not a dashboard",
    "Counts are orientation, read once, on the way to the work. A number that nobody acts on is decoration.",
  ],
] as const;

const FAQ = [
  [
    "Does it send my whole repository to an LLM?",
    "No. The repository is parsed locally into an atlas. What reaches the model is a candidate, its pinned evidence excerpts, the architecture case, and the policies retrieved for that candidate.",
  ],
  [
    "How are policies selected?",
    "By retrieval, per candidate, and it is recorded: the retriever and its version, the corpus fingerprint, the embedding model identity, the query fingerprint, and the exact policy ids selected.",
  ],
  [
    "Can I use Ollama?",
    "Yes, for both roles. Reasoning and embedding are separate selections, so a local embedding model can serve retrieval while a hosted model does the judging, or the whole thing can run locally.",
  ],
  [
    "What happens after I answer a clarification question?",
    "The answer is written to the architecture case as a new revision, the affected candidates are judged again, and a new review revision is recorded with a delta against the previous one.",
  ],
  [
    "Can I add my own architecture policies?",
    "Yes. Author them in the workspace as Markdown with a title, description, scope and strength, or register a folder of existing policy documents as a source.",
  ],
] as const;

function LandingNav() {
  const { preference, cycle } = useTheme();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const Glyph = preference === "light" ? SunIcon : preference === "dark" ? MoonIcon : MonitorIcon;

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 border-b transition",
        scrolled ? "border-rule bg-canvas/85 backdrop-blur" : "border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Wordmark to="/" />
        <nav aria-label="Sections" className="hidden items-center gap-1 md:flex">
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="rounded-sm px-2.5 py-1.5 text-sm font-medium text-ink-2 transition hover:bg-sunken hover:text-ink"
            >
              {section.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="-my-1.5 min-h-11 min-w-11 px-2"
            onClick={cycle}
            aria-label={`Theme: ${preference}. Change it.`}
          >
            <Glyph className="size-4" />
          </Button>
          {/* Not on a phone, where it wrapped onto two lines and squeezed the wordmark
              against the menu button. It is the third copy of the same call to action at
              that width — the hero states it a screen-length below, and the drawer this
              menu opens ends with it — so the one that costs the header its shape is the
              one to drop. */}
          <ButtonLink to="/start" size="sm" className="hidden sm:inline-flex">
            Review a repository
          </ButtonLink>
          <Button
            variant="ghost"
            size="sm"
            className="-my-1.5 min-h-11 min-w-11 px-2 md:hidden"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <MenuIcon className="size-5" />
          </Button>
        </div>
      </div>

      <Drawer open={open} onClose={() => setOpen(false)} side="right" title="ArchCompass">
        <nav aria-label="Sections" className="grid gap-1 p-3">
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              onClick={() => setOpen(false)}
              className="rounded-sm px-3 py-2.5 text-sm font-medium text-ink-2 hover:bg-sunken hover:text-ink"
            >
              {section.label}
            </a>
          ))}
          <Link
            to="/start"
            className="mt-2 rounded-sm bg-ink px-3 py-2.5 text-center text-sm font-semibold text-canvas"
          >
            Review a repository
          </Link>
        </nav>
      </Drawer>
    </header>
  );
}

/**
 * Orientation, read once, on the way to the work — set like readings on an instrument
 * rather than in cards that ask to be looked at. "Decided" is counted beside the model's
 * three, because how far through a review you are is answered by the team's half.
 */
function Ribbon() {
  const readings: [string, string, string?][] = [
    ["Examined", "12"],
    ["Material", "4", "text-material"],
    ["Held", "3", "text-held"],
    ["Cleared", "5", "text-cleared"],
    ["Decided", "0"],
  ];
  return (
    <dl className="mt-10 flex max-w-[600px] flex-wrap border-t border-rule-strong pt-3.5">
      {readings.map(([label, value, tone], index) => (
        <div
          key={label}
          className={cn(
            "border-r border-rule px-5 last:border-r-0",
            index === 0 && "pl-0",
          )}
        >
          <dt
            className={cn(
              "whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.13em]",
              tone ?? "text-ink-3",
            )}
          >
            {label}
          </dt>
          <dd
            className={cn(
              "mt-1.5 font-mono text-[22px] font-semibold leading-none tracking-[-0.02em] tabular-nums",
              tone ?? "text-ink",
            )}
          >
            {value}
            {label === "Decided" ? <span className="text-[13px] font-normal text-ink-3">/12</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden pb-2 pt-14 sm:pt-[76px]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 grid-lines opacity-50 [mask-image:radial-gradient(74%_62%_at_34%_0%,black,transparent)]"
      />
      <div className="relative mx-auto grid max-w-6xl items-start gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-14">
        <Reveal>
          <Mono className="text-[11px] uppercase tracking-[0.13em] text-ink-3">
            Weighed, not enforced
          </Mono>
          <h1 className="mt-3.5 max-w-[15ch] font-display text-[clamp(37px,5.6vw,62px)] font-semibold leading-[1.04] tracking-[-0.036em] text-ink">
            Write your guidance once. Every review weighs it.
          </h1>
          <p className="mt-5 max-w-[52ch] text-[17px] leading-[1.62] text-ink-2">
            ArchCompass maps your repository deterministically, then asks a model one question at a
            time: given what this team has written down, is this boundary earning its place? Every
            answer names the guidance it rests on.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-2.5">
            <ButtonLink to="/start" size="lg">
              Review a repository
              <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink to="/reviews" size="lg" variant="secondary">
              Read a real finding
            </ButtonLink>
          </div>
          <Mono className="mt-4 block text-[12px] text-ink-3">
            Runs locally · your models · Apache-2.0
          </Mono>
          <Ribbon />
        </Reveal>

        <Reveal delay={120}>
          <CorpusCard />
          <p className="mt-3.5 max-w-[420px] text-xs leading-[1.55] text-ink-3">
            Three verdicts, no score. “Leave it exactly as it is” is a first-class answer — an
            advisor that only ever recommends change is an advocate, not a judge.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * The one atmospheric moment on the page, and the only section that is dark in both themes.
 * It earns that because it is the only place stating the problem rather than the product.
 */
function IntentBand() {
  return (
    <section id="intent" className="relative overflow-hidden bg-band py-20 text-band-ink sm:py-[132px]">
      <Field className="pointer-events-none absolute inset-0 h-full w-full max-md:opacity-[0.34]" />
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal className="max-w-[58ch]">
          <Mono className="text-[11px] uppercase tracking-[0.13em] text-band-ink-2">
            Unwritten intent
          </Mono>
          <h2 className="mt-3.5 font-display text-[clamp(29px,3.8vw,46px)] font-semibold leading-[1.08] tracking-[-0.032em]">
            A codebase records what was built. Not what you were trying to build.
          </h2>
          <p className="mt-5 text-[16.5px] leading-[1.68] text-band-ink-2">
            A parser reads the code as written — the imports, the calls, the inheritance. What it
            cannot read is the part that decides whether any of it is right: who owns what, which
            shortcut was deliberate, what the team already agreed to live with.
          </p>
          <p className="mt-4 text-[16.5px] leading-[1.68] text-band-ink-2">
            <span className="font-medium text-band-ink">That intent is real.</span> It shapes every
            file in the repository. It just isn't written anywhere a parser can reach, which is why
            a linter flags the shortcut you took on purpose and misses the abstraction that stopped
            paying rent two years ago.
          </p>
          <p className="mt-4 text-[16.5px] leading-[1.68] text-band-ink-2">
            ArchCompass's whole job is to make it readable. You write it down once, as guidance and
            as answers to the questions a review asks. Every review after that can see it.
          </p>
          <a
            href="#how"
            className="mt-8 inline-flex min-h-12 select-none items-center justify-center rounded-sm border border-band-ink bg-band-ink px-5 text-[15px] font-semibold text-band transition hover:opacity-90"
          >
            See how it's read
          </a>
        </Reveal>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="py-16 sm:py-[88px]">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="How it works"
            title="Six steps, and you can audit every one"
            body="The application decides what to inspect. The model decides what the evidence means. Neither one invents the identity of your repository or of a policy — which is why the same commit gives the same map, every time."
          />
        </Reveal>

        <Reveal className="relative mt-11">
          <div aria-hidden="true" className="absolute inset-x-0 top-[11px] h-px bg-rule" />
          <ol className="grid grid-cols-2 gap-y-9 sm:grid-cols-3 lg:grid-cols-6 lg:gap-y-0">
            {STEPS.map(([title, body, who], index) => (
              <li key={title} className="relative pr-5">
                <div className="relative h-[23px] w-px bg-rule-strong">
                  <span className="absolute -left-[3.5px] top-[7px] size-2 rounded-full border-[1.5px] border-ink bg-canvas" />
                </div>
                <Mono className="mt-3 block text-[10px] tracking-[0.14em] text-ink-3">
                  {String(index + 1).padStart(2, "0")}
                </Mono>
                <h3 className="mt-1 font-display text-[15px] font-semibold tracking-tight text-ink">
                  {title}
                </h3>
                <p className="mt-1.5 max-w-[24ch] text-[13px] leading-[1.55] text-ink-2">{body}</p>
                <Mono className="mt-3 inline-block border-t border-rule pt-1.5 text-[9px] uppercase tracking-[0.13em] text-ink-3">
                  {who}
                </Mono>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * One finding on the attribution gutter — the device that carries the charter's second
 * commitment, shown at full size because it is the most distinctive thing in the product.
 */
function FindingSection() {
  return (
    <section
      id="finding"
      className="border-y border-rule bg-surface-2 py-16 sm:py-[88px]"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="One finding, whole"
            title="The machine assembles. The model judges. You decide."
            body="Three different jobs, kept visibly apart — down a single hairline, with the gutter saying whose voice produced the block beside it. There is no provenance footer, because the attribution is never more than a gutter's width from the claim it belongs to."
          />
        </Reveal>

        <Reveal className="mt-11 overflow-hidden rounded-lg border border-rule bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule bg-surface-2 px-5 py-3.5">
            <Mono className="text-[15px] font-semibold tracking-tight text-ink">
              payments.gateway.PaymentGateway
            </Mono>
            <Mono className="text-[11px] text-ink-3">▲ material · changed since review 3</Mono>
          </div>

          <GutterBlock voice="Measured" who={["sole_implementation", "detector v1.4.0", "8f31c2a"]}>
            <Mono className="text-[11px] uppercase tracking-[0.13em] text-ink-3">
              What was counted
            </Mono>
            <dl className="mt-3 flex flex-wrap overflow-hidden rounded-md border border-rule">
              {[
                ["Implementations", "1"],
                ["External callers", "5"],
                ["Provider terms in domain", "3"],
              ].map(([label, value]) => (
                <div
                  key={label}
                  // `basis-full` rather than `w-full`: `flex-1` sets `flex-basis: 0` and would win
                  // over a width on the main axis, so the three readings stayed in one cramped
                  // row on a phone. Below `sm` each reading is its own row.
                  className="basis-full border-b border-rule px-3.5 py-2.5 last:border-b-0 sm:min-w-[104px] sm:flex-1 sm:basis-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
                >
                  <dt className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">
                    {label}
                  </dt>
                  <dd className="mt-1 font-mono text-[19px] font-semibold tracking-[-0.02em] tabular-nums text-ink">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="mt-3 overflow-x-auto rounded-md border border-rule bg-sunken px-3.5 py-2.5">
              <Mono className="block text-[10.5px] text-ink-3">payments/gateway.py:12–26</Mono>
              <pre className="mt-1.5 font-mono text-[12.5px] leading-[1.5] text-ink">
{`class PaymentGateway(Protocol):
    def charge(self, amount: Money, *, idempotency_key: str) -> Charge: ...
    def stripe_retry_after(self, err: StripeError) -> float: ...`}
              </pre>
            </div>
          </GutterBlock>

          <GutterBlock voice="Judged" who={["google:gemini-3.6", "judge:v1", "2026-08-21"]}>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-material/25 bg-material-soft px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-material">
              <span aria-hidden="true">▲</span> Material
            </span>
            <p className="mt-3 max-w-[58ch] text-[15.5px] leading-[1.68] text-ink-2">
              The port was introduced to keep payment providers replaceable, and it is not doing
              that. One adapter implements it, and the protocol itself names{" "}
              <span className="font-mono text-[14px]">stripe_retry_after</span> — so a second
              provider could not satisfy the interface without inheriting Stripe's error vocabulary.
              The indirection currently costs a hop and buys nothing your guidance asked for.
            </p>
            <p className="mt-3.5 rounded-md border border-held/30 bg-held-soft px-3.5 py-2.5 text-[13px] leading-[1.55] text-ink-2">
              <span className="font-semibold text-held">Hinges on:</span> whether a second provider
              is actually planned this year. You answered “no, and none is on the roadmap” in review
              3 — which is why this moved from held to material.
            </p>
          </GutterBlock>

          <GutterBlock voice="Decided" who={["nobody yet"]}>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-sm border border-ink bg-ink px-3.5 py-1.5 text-[12.5px] font-semibold text-canvas">
                Accept the work
              </span>
              {["Park", "Waive"].map((label) => (
                <span
                  key={label}
                  className="rounded-sm border border-rule-strong bg-surface-2 px-3.5 py-1.5 text-[12.5px] font-semibold text-ink-2"
                >
                  {label}
                </span>
              ))}
            </div>
            <p className="mt-3 max-w-[56ch] text-[13px] leading-6 text-ink-3">
              Whatever you choose stays with the branch, with your reasoning and your name on it,
              and the next review reads it before it judges again.
            </p>
          </GutterBlock>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * One block of the attribution gutter: who is speaking on the left, what they said on the
 * right, and a rule across both where the voice changes. Below `lg` the two columns become
 * a label strip above the block — the sequence survives, the registration does not.
 */
function GutterBlock({
  voice,
  who,
  children,
}: {
  voice: string;
  who: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 [&+&>*]:border-t [&+&>*]:border-rule-strong md:grid-cols-[172px_1px_minmax(0,1fr)]">
      <div className="px-5 pb-0 pt-5 text-left md:pb-6 md:pr-4 md:text-right">
        <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">{voice}</div>
        <div className="mt-1.5 font-mono text-[10px] leading-[1.6] text-ink-3">
          {who.map((line) => (
            <span key={line} className="block whitespace-nowrap">
              {line}
            </span>
          ))}
        </div>
      </div>
      <div aria-hidden="true" className="relative hidden bg-rule md:block">
        <span className="absolute -left-[3px] top-[22px] size-[7px] bg-ink" />
      </div>
      <div className="px-5 pb-6 pt-3 md:pt-5">{children}</div>
    </div>
  );
}

function RefusalsSection() {
  return (
    <section id="refusals" className="py-16 sm:py-[88px]">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="What ArchCompass is not"
            title="Four plausible directions, each of which would break it"
          />
        </Reveal>
        <Reveal className="mt-10 border-t border-rule">
          {REFUSALS.map(([title, body]) => (
            <div
              key={title}
              className="grid items-baseline gap-2 border-b border-rule py-5 md:grid-cols-[minmax(0,240px)_minmax(0,1fr)] md:gap-8"
            >
              <h3 className="font-display text-[17px] font-semibold tracking-[-0.015em] text-ink">
                {title}
              </h3>
              <p className="max-w-[64ch] text-[14.5px] leading-[1.62] text-ink-2">{body}</p>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

function FaqSection() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section className="border-t border-rule py-16 sm:py-[88px]">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro eyebrow="FAQ" title="Questions engineers actually ask" />
        </Reveal>
        <div className="mt-8 divide-y divide-rule border-y border-rule">
          {FAQ.map(([question, answer], index) => {
            const expanded = open === index;
            return (
              <div key={question}>
                <h3>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : index)}
                    className="flex min-h-11 w-full items-center justify-between gap-4 py-4 text-left"
                  >
                    <span className="font-display text-base font-semibold text-ink">{question}</span>
                    <ChevronDown
                      className={cn("size-4 shrink-0 text-ink-3 transition", expanded && "rotate-180")}
                    />
                  </button>
                </h3>
                {expanded ? (
                  <p className="animate-expand pb-4 text-sm leading-7 text-ink-2">{answer}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="border-t border-rule py-16 text-center sm:py-24">
      <div className="mx-auto max-w-4xl px-4 sm:px-6">
        <Reveal>
          <h2 className="mx-auto max-w-[19ch] font-display text-[clamp(28px,3.6vw,42px)] font-semibold leading-[1.1] tracking-[-0.03em] text-ink">
            Point it at a repository and see what your guidance says.
          </h2>
          <p className="mx-auto mt-4 max-w-[48ch] text-base leading-[1.62] text-ink-2">
            It will map the structure, weigh what it finds against what you have written down, and
            tell you plainly what it could not decide without asking you first.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-2.5">
            <ButtonLink to="/start" size="lg">
              Review a repository
              <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink to="/policies" size="lg" variant="secondary">
              Read the policy corpus
            </ButtonLink>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-rule bg-surface-2">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-sm">
          <Wordmark to="/" />
          <p className="mt-3 text-sm leading-6 text-ink-3">
            A context-aware, evidence-grounded architecture reviewer. Apache-2.0 licensed, and it
            runs in your own workspace.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-8 text-sm sm:grid-cols-3">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">
              Product
            </div>
            <ul className="mt-2.5 grid gap-1.5">
              {[
                ["/start", "Start a review"],
                ["/reviews", "Reviews"],
                ["/policies", "Policies"],
              ].map(([to, label]) => (
                <li key={to}>
                  <Link to={to} className="text-ink-2 hover:text-ink">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">
              Workspace
            </div>
            <ul className="mt-2.5 grid gap-1.5">
              {[
                ["/repositories", "Repositories"],
                ["/cases", "Architecture cases"],
                ["/settings", "Models"],
              ].map(([to, label]) => (
                <li key={to}>
                  <Link to={to} className="text-ink-2 hover:text-ink">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">
              Project
            </div>
            <ul className="mt-2.5 grid gap-1.5">
              <li>
                <a
                  href="https://github.com/Furkan-rgb/arch_compass"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 text-ink-2 hover:text-ink"
                >
                  {/* The mark says which site; the repository name says which project.
                      "GitHub" on its own said neither. */}
                  <GithubIcon className="size-3.5 shrink-0" />
                  {/* One unbreakable word in a third of a footer. At the width where the
                      footer becomes three columns it is the widest thing in its column and
                      there is no break to take, so it decides the page's width. */}
                  <span className="font-mono text-[13px] wrap-anywhere">
                    Furkan-rgb/arch_compass
                  </span>
                </a>
              </li>
              <li>
                <a href="#how" className="text-ink-2 hover:text-ink">
                  How it works
                </a>
              </li>
              <li>
                <span className="text-ink-3">Apache-2.0</span>
              </li>
            </ul>
          </div>
        </nav>
      </div>
      <div className="border-t border-rule px-4 py-4 text-center text-xs text-ink-3 sm:px-6">
        Analysis runs locally. Only the candidate, its evidence and the retrieved guidance reach the
        model you chose.
      </div>
    </footer>
  );
}

function SectionIntro({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body?: string;
}) {
  return (
    <div className="max-w-[62ch]">
      <Mono className="text-[11px] uppercase tracking-[0.13em] text-ink-3">{eyebrow}</Mono>
      <h2 className="mt-2.5 font-display text-[clamp(26px,3.2vw,34px)] font-semibold leading-[1.12] tracking-[-0.028em] text-ink">
        {title}
      </h2>
      {body ? (
        <p className="mt-3.5 max-w-[56ch] text-base leading-[1.62] text-ink-2">{body}</p>
      ) : null}
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <a
        href="#landing-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-ink focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-canvas"
      >
        Skip to content
      </a>
      <LandingNav />
      <main id="landing-main" tabIndex={-1} className="outline-none">
        <Hero />
        <IntentBand />
        <HowItWorks />
        <FindingSection />
        <RefusalsSection />
        <FaqSection />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
