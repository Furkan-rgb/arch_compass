import { Suspense, lazy, useEffect, useState } from "react";
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
import { ANCHOR, ATLAS_VIEWBOX, AtlasMap } from "./atlas";
import { Field } from "./field";
import { SpecimenCallout, SpecimenPicker, useSpecimen } from "./specimen";

/** The one heavy thing on this page, and it is four screens down. See `FindingSection`. */
const CaseFileDocket = lazy(() =>
  import("./exhibit").then((module) => ({ default: module.CaseFileDocket })),
);

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
    "The answer is written to the case revision this review opened, every candidate is judged again — an answer is about intent, and intent bears on all of them — and the review is recorded with a delta against the previous one.",
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
    <>
      <header
        className={cn(
          "sticky top-0 z-40 border-b transition",
          scrolled
            ? "border-rule bg-chrome backdrop-blur-chrome"
            : "border-transparent bg-transparent",
        )}
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Wordmark to="/" />
          <nav aria-label="Sections" className="hidden items-center gap-1 lg:flex">
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
              className="-my-1.5 min-h-11 min-w-11 px-2 lg:hidden"
              aria-label="Open menu"
              onClick={() => setOpen(true)}
            >
              <MenuIcon className="size-5" />
            </Button>
          </div>
        </div>
      </header>

      {/* A sibling of the header rather than a child of it, and that is load-bearing rather
          than tidiness.

          The header earns `backdrop-blur-chrome` — a real `backdrop-filter` — the moment the
          page scrolls past 8px, and a `backdrop-filter` other than `none` makes an element
          the containing block for every `position: fixed` descendant, the same rule
          `transform`, `filter` and `perspective` follow. Nested, the drawer's `fixed inset-0`
          therefore stopped meaning the viewport and started meaning the 56px header: the
          scrim dimmed only the header band, the panel became a sliver showing its own title
          row, and the section links were clipped to nothing by a scroller with no height. The
          body was already locked, so the page stopped scrolling while nothing had visibly
          opened.

          Which is why it read as a menu that sometimes does nothing: unscrolled, the header
          carries no filter at all and the drawer worked. `AppShell` never had this — its
          drawer has always sat outside the rail. */}
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
          <ButtonLink to="/start" className="mt-2">
            Review a repository
          </ButtonLink>
        </nav>
      </Drawer>
    </>
  );
}

function Hero() {
  const { index, select, bearing, holdProps, showcasing, toggleShowcase } = useSpecimen();

  return (
    // The figure is taken out of the flow above `xl` so it can bleed off the right edge, so
    // above `lg` the section has nothing tall left in it to be measured by. The minimum is
    // what the figure needs; below `lg` the copy and the figure stack and it never applies.
    //
    // The split used to start at `xl`, which meant no tablet ever saw it: at 1024 the copy
    // ran the full width with the right half empty, the atlas stacked underneath, and the
    // judgement — the one thing the hero exists to show — sat a screen and a half down. The
    // section went from 880px on a desk to 1712px on an iPad.
    //
    // `lg` rather than `md`, and that is measured rather than chosen. At 768 the same
    // arrangement puts the map through the paragraph and the buttons, and runs the callout
    // off the right edge with its sentences cut. Below `lg` the stack is the honest answer;
    // at `lg` the copy narrows to 27rem and the headline with it, because 5.6vw is 57px at
    // 1024 and that is three words to a line in a column that width.
    <section className="relative overflow-hidden pb-10 pt-14 sm:pt-[76px] lg:min-h-[54rem] lg:pb-16 xl:min-h-[55rem]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 grid-lines opacity-50 [mask-image:radial-gradient(74%_62%_at_34%_0%,black,transparent)]"
      />
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal className="lg:max-w-[27rem] xl:max-w-[35rem]">
          <Mono className="text-[11px] uppercase tracking-[0.13em] text-ink-3">
            Weighed, not enforced
          </Mono>
          <h1 className="mt-3.5 max-w-[15ch] font-display text-[clamp(37px,5.6vw,62px)] font-semibold leading-[1.04] tracking-[-0.036em] text-ink lg:text-[40px] xl:text-[clamp(37px,5.6vw,62px)]">
            Write your guidance once. Every review weighs it.
          </h1>
          <p className="mt-5 max-w-[52ch] text-[17px] leading-[1.62] text-ink-2">
            ArchCompass maps your repository deterministically, then asks a model one question at a
            time: given what this team has written down, is this boundary earning its place? Every
            answer names the guidance it rests on.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-x-7 gap-y-3">
            <ButtonLink to="/start" size="lg">
              Review a repository
              <ArrowRight className="size-4" />
            </ButtonLink>
            {/* Not a second button. One page has one primary action, and the thing this
                offers is a shorter walk than starting a review — the section below, not the
                review list, which on a first visit is empty. */}
            <a
              href="#finding"
              className="inline-flex min-h-11 items-center border-b border-rule-strong text-[15px] font-semibold text-ink transition hover:border-ink"
            >
              See how a finding is made
            </a>
          </div>
          <Mono className="mt-4 block text-[12px] text-ink-3">
            Runs locally · your models · Apache-2.0
          </Mono>
          {/* The legend for the three lit nodes on the map, and the way to move between them.
              It stands where an invented count of a review nobody has run used to stand. */}
          <SpecimenPicker
            index={index}
            onSelect={select}
            showcasing={showcasing}
            onToggleShowcase={toggleShowcase}
            hold={holdProps}
            className="mt-8 border-t border-rule-strong pt-2.5"
          />
        </Reveal>

        <Reveal
          delay={120}
          className="mt-12 lg:absolute lg:left-[47%] lg:right-[-4%] lg:top-4 lg:mt-0 lg:max-w-[56rem] xl:left-[50%] xl:right-[-6%]"
        >
          <Mono className="block text-[11px] uppercase tracking-[0.13em] text-ink-3">
            The atlas — parsed, never imported and never run
          </Mono>
          {/* The box the map is drawn in carries the map's own proportions, so a percentage
              of this box and a fraction of the viewBox are the same place. That is what lets
              the callout — which is HTML, and outside the SVG — land exactly where the
              leader inside it ends. */}
          <div className="relative mt-3 max-w-[46rem] lg:aspect-[900/700] lg:max-w-none">
            <AtlasMap
              active={bearing.node}
              className="pointer-events-none aspect-[900/700] w-full lg:absolute lg:inset-0 lg:aspect-auto"
            />
            <SpecimenCallout
              index={index}
              hold={holdProps}
              style={{
                left: `${(ANCHOR.x / ATLAS_VIEWBOX.width) * 100}%`,
                top: `${(ANCHOR.y / ATLAS_VIEWBOX.height) * 100}%`,
              }}
              className="mt-6 w-full max-w-[24rem] lg:absolute lg:mt-0 lg:w-[19rem] lg:max-w-none xl:w-[22rem]"
            />
          </div>
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
    // The band carries its own ground in both themes, and in dark that ground is the same
    // void the page is already on — so in dark there is nothing here to mark a section with
    // except the field, and the field is what does it.
    //
    // Which is why neither the ground nor the field is drawn the way a section normally
    // draws them. There are no hairlines: a rule across a boundary where the two grounds are
    // the same colour is a line asserting a change that did not happen. And the field is not
    // clipped to the band — it is one sheet reaching up into the hero and down past the
    // band, masked at both ends, so a ribbon fades out rather than being cut off by an edge.
    <section id="intent" className="relative py-20 text-band-ink sm:py-[132px]">
      {/* The ground, as its own layer rather than as the section's background. A background
          belongs to the section's own box and paints over every negative-z child of it, and
          the field has to sit on top of this ground in light — where the band really is a
          different colour from the page — while still reaching past the section's edges. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-20 bg-band" />
      {/* Up into the hero by a third of its height and down past the band, fading to nothing
          at both ends. The mask is what makes the sheet continuous: the canvas still has
          edges, but no ribbon ever reaches one at full strength. */}
      <Field
        bleed={{ top: 0.45, bottom: 0.14 }}
        className="pointer-events-none absolute inset-x-0 -z-10 max-md:opacity-[0.34]"
      />
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
          {/* Not a fill. A solid button here was the loudest thing on the page and it pointed
              at an anchor a screen below — the page has one primary action, "Review a
              repository", and this is a walk down to the next section. Same shape as the
              hero's second call to action, so the two read as the same kind of offer. */}
          <a
            href="#how"
            className="mt-8 inline-flex min-h-12 items-center border-b border-band-rule text-[15px] font-semibold text-band-ink transition hover:border-band-ink"
          >
            See how it's read
            <ArrowRight className="ml-2 size-4" />
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

        <Reveal className="mt-11">
          <ol className="grid grid-cols-2 gap-y-9 sm:grid-cols-3 lg:grid-cols-6 lg:gap-y-0">
            {STEPS.map(([title, body, who], index) => (
              // The wire is drawn per step rather than once across the section.
              //
              // It used to be one absolutely-positioned hairline on the wrapper —
              // `inset-x-0 top-[11px]` — which is exact at the one width where all six steps
              // share a row. Below `lg` the grid wraps, and `top` on the wrapper is measured
              // from the wrapper, so the rule could only ever cross the first row: at 390px
              // steps 03 to 06 were left with a bead and a tick and nothing joining them,
              // and at 640–1023px steps 04 to 06 were. It read as broken rules rather than
              // as a sequence, which is what it is.
              //
              // Each step now carries its own segment at the same 11px — the y of the bead's
              // centre, not the tick's half-height. The grid has no column gap (the gutter
              // is each item's own `pr-5`), so the segments abut inside a row and compose
              // exactly the line the wrapper drew: identical at `lg`, and now true of every
              // row the grid makes. Adding `gap-x-*` here would break it into six dashes.
              //
              // The bead comes later in the tree than the pseudo-element, so it still paints
              // over the segment and reads as a bead on a wire rather than a dot beside one.
              <li
                key={title}
                className="relative pr-5 before:absolute before:inset-x-0 before:top-[11px] before:h-px before:bg-rule"
              >
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
 * The docket, running.
 *
 * This section used to be a drawing of the finding surface — a hand-built copy of a device
 * called the attribution gutter, kept correct by nothing but memory, and still on the page
 * months after the gutter itself was deleted and the queue and the workbench became one
 * docket. So it is not a drawing any more. `CaseFileDocket` renders the workbench's own
 * `FindingBody` against a written-out review, which means this section cannot describe a
 * component the product does not have.
 *
 * It is loaded on its own, after the page. The chunk it pulls in is the finding surface and
 * the syntax highlighter behind it, and the first screen of a landing page should not wait
 * on either — this is four screens down.
 */
function FindingSection() {
  return (
    <section id="finding" className="border-y border-rule bg-surface-2 py-16 sm:py-[88px]">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="One docket, worked down"
            title="The machine assembles. The model judges. You decide."
            body="Three different jobs, kept visibly apart — each block on the surface led by a line naming who produced it. Every candidate is a row stating its own claim, so the list is the overview; the row opens in place, so checking a claim never moves you. This is the real thing, on a review written out for the page."
          />
        </Reveal>

        <Reveal className="mt-11">
          <Suspense
            fallback={
              // Held at roughly the height the docket opens to, so the page under it does
              // not jump when the chunk lands.
              <div
                className="min-h-[42rem] rounded-lg border border-rule bg-surface"
                aria-busy="true"
              />
            }
          >
            <CaseFileDocket />
          </Suspense>
        </Reveal>

        <Mono className="mt-4 block text-[11px] text-ink-3">
          A written-out review · no repository is read by this page
        </Mono>
      </div>
    </section>
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
        {/* One stacking context over the two sections the field crosses. Without it the
            field — which is behind the page's content, at a negative z — would be painted
            over by `bg-canvas` on the wrapper above, because a background belonging to an
            in-flow ancestor is painted after every negative-z descendant of it. */}
        <div className="relative isolate">
          <Hero />
          <IntentBand />
        </div>
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
