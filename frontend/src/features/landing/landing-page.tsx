import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { Badge, Tag } from "../../ui/badge";
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
import { WorkbenchPreview } from "./preview";

const SECTIONS = [
  { id: "product", label: "Product" },
  { id: "how-it-works", label: "How it works" },
  { id: "architecture", label: "Architecture" },
  { id: "policies", label: "Policies" },
  { id: "faq", label: "FAQ" },
];

const PIPELINE = [
  ["Repository", "Parsed into an atlas: nodes, edges, metrics, obscurity signals."],
  ["Atlas", "A deterministic map. The same commit gives the same map, every time."],
  ["Candidate", "Structural patterns detected by rule — the application decides what to inspect."],
  ["Policies", "Retrieved per candidate, with the retriever, corpus and selection recorded."],
  ["Finding", "The model decides what the evidence means, inside the policy it was given."],
  ["Review", "Recorded as an immutable revision, with a delta against the one before it."],
] as const;

const PRINCIPLES = [
  [
    "Deterministic analysis",
    "The repository is read by a parser, not by a model. Nodes, edges and metrics are reproducible from the commit.",
  ],
  [
    "Auditable retrieval",
    "Every judgement records which policies were retrieved, by which retriever, against which corpus fingerprint.",
  ],
  [
    "Structured judgement",
    "The model returns a verdict, its reasoning, the evidence it used, and what the conclusion hinges on.",
  ],
  [
    "Revisioned reviews",
    "Reviews are never edited. A new answer produces a new case revision and a new review with its own delta.",
  ],
  [
    "Human clarification",
    "When the code cannot answer a question, ArchCompass asks instead of assuming.",
  ],
  [
    "Standing decisions",
    "Accept, park or waive stays with the team, on the branch, separate from what the model found.",
  ],
] as const;

const FEATURES = [
  {
    title: "Deterministic repository analysis",
    body: "Python source is parsed into a typed atlas — packages, modules, classes, functions, imports, calls, inheritance and tests — with optional type-aware edge resolution. Nothing about the map depends on a model being available.",
    points: ["Reproducible from the commit", "Parser version folded into the analysis hash", "Metrics carry their own limitations"],
  },
  {
    title: "Policy-grounded judgement",
    body: "Candidates are judged against the policies retrieved for them, plus the architecture case a human authored. The prompt identity, model identity and retrieval identity are stored on the finding.",
    points: ["Verdicts: material, held, cleared", "Evidence pinned to file and line", "The hinge is stated when one exists"],
  },
  {
    title: "Clarification loops",
    body: "When judgement genuinely turns on something the repository cannot show — ownership, intent, what is planned — the review pauses and asks. Answers become case context and the affected candidates are judged again.",
    points: ["Questions carry their reason", "Skipping is explicit and recorded", "Each round is a case revision"],
  },
  {
    title: "Review delta and lineage",
    body: "Each review is compared to its predecessor by candidate identity: what is new, what changed and why, what is unchanged, and what has been addressed since.",
    points: ["Immutable review records", "Cause-level change reporting", "Addressed candidates tracked"],
  },
  {
    title: "Standing decisions",
    body: "Accept, park or waive is recorded against the branch with its reasoning and author, and survives the next review. ArchCompass never decides on the team's behalf.",
    points: ["Separate from the model's verdict", "Waiving requires a reason", "Full decision history per candidate"],
  },
  {
    title: "Local or hosted models",
    body: "Reasoning and embedding are chosen independently. Run both against a local Ollama, both against a hosted provider, or mix them — retrieval provenance records whichever was used.",
    points: [
      "Ollama, Google, Groq and Cerebras",
      "Embedding choice is independent",
      "Environment pinning respected",
    ],
  },
] as const;

const FAQ = [
  [
    "Is ArchCompass an autonomous coding agent?",
    "No. It does not edit code, open branches, or run anything in your repository. It analyses, judges, asks, and records. Every action that changes your codebase remains yours.",
  ],
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
    "Are findings persisted?",
    "Yes. Reviews, findings, evidence, retrieval provenance, case revisions and standing decisions are all stored in the workspace and remain readable exactly as recorded.",
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
              className="rounded-md px-2.5 py-1.5 text-sm font-medium text-ink-2 transition hover:bg-sunken hover:text-ink"
            >
              {section.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={cycle}
            aria-label={`Theme: ${preference}. Change it.`}
          >
            <Glyph className="size-4" />
          </Button>
          <ButtonLink to="/start" size="sm">
            Review a repository
          </ButtonLink>
          <Button
            variant="ghost"
            size="sm"
            className="px-2 md:hidden"
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
              className="rounded-md px-3 py-2.5 text-sm font-medium text-ink-2 hover:bg-sunken hover:text-ink"
            >
              {section.label}
            </a>
          ))}
          <Link
            to="/start"
            className="mt-2 rounded-md bg-ink px-3 py-2.5 text-center text-sm font-semibold text-canvas"
          >
            Review a repository
          </Link>
        </nav>
      </Drawer>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 grid-lines opacity-[0.35] [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]"
      />
      <div className="relative mx-auto max-w-6xl px-4 pb-12 pt-12 sm:px-6 sm:pb-16 sm:pt-20">
        <Reveal className="max-w-3xl">
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-ink-3">
            Architecture review, not autocomplete
          </div>
          <h1 className="mt-3 font-display text-[34px] font-semibold leading-[1.08] tracking-[-0.03em] text-ink sm:text-[52px]">
            Architecture review grounded in your code, policies, and decisions.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-ink-2 sm:text-lg">
            ArchCompass deterministically maps your repository, detects architecture candidates,
            retrieves the policies that matter, and uses structured model judgement to produce
            auditable architecture findings.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <ButtonLink to="/start" size="lg">
              Review a repository
              <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink to="/reviews" size="lg" variant="secondary">
              Explore an example review
            </ButtonLink>
          </div>
          <p className="mt-4 text-xs text-ink-3">
            Runs locally against your workspace. Reasoning and embedding models are yours to choose.
          </p>
        </Reveal>

        <Reveal delay={120} className="mt-10 sm:mt-14">
          <WorkbenchPreview />
        </Reveal>
      </div>
    </section>
  );
}

function PipelineSection() {
  return (
    <section id="how-it-works" className="border-t border-rule bg-surface/60 py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="How it works"
            title="Six steps, and you can audit every one"
            body="The application decides what to inspect. The model decides what the evidence means. Neither invents the identity of your repository or of a policy."
          />
        </Reveal>

        <ol className="mt-9 grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
          {PIPELINE.map(([title, body], index) => (
            <Reveal as="li" key={title} delay={index * 60}>
              <div className="h-full rounded-lg border border-rule bg-surface p-4 transition hover:border-rule-strong hover:">
                <div className="flex items-center gap-2">
                  <Mono className="text-[11px] font-bold text-ink">
                    {String(index + 1).padStart(2, "0")}
                  </Mono>
                  <span className="font-display text-base font-semibold tracking-tight text-ink">
                    {title}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-ink-2">{body}</p>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}

function PrinciplesSection() {
  return (
    <section id="product" className="py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="Design principles"
            title="Built to be trusted by the people it reviews"
            body="Every claim ArchCompass makes can be traced back to something you can inspect: a parsed structure, a retrieved policy, an authored constraint, or a decision your team recorded."
          />
        </Reveal>
        <div className="mt-9 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {PRINCIPLES.map(([title, body], index) => (
            <Reveal key={title} delay={index * 50}>
              <div className="h-full rounded-lg border border-rule bg-surface p-4">
                <h3 className="font-display text-base font-semibold tracking-tight text-ink">
                  {title}
                </h3>
                <p className="mt-1.5 text-sm leading-6 text-ink-2">{body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function ShowcaseSection() {
  return (
    <section id="policies" className="border-t border-rule bg-surface/60 py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="Inside a review"
            title="Findings, evidence, retrieval, clarification"
            body="Four things a reviewer asks for, and where each of them lives."
          />
        </Reveal>

        <div className="mt-9 grid gap-2.5 lg:grid-cols-2">
          <Reveal>
            <ShowcaseCard title="A finding, structured">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="held" glyph="◆">
                  Held
                </Badge>
                <Tag>
                  <span className="font-mono text-[11px]">dependency_direction</span>
                </Tag>
              </div>
              <p className="mt-2 text-sm font-semibold leading-6 text-ink">
                The orders domain imports the persistence adapter directly
              </p>
              <p className="mt-1.5 text-sm leading-6 text-ink-2">
                Whether this is a problem depends on who owns persistence — which the repository
                cannot say.
              </p>
              <div className="mt-2.5 rounded-md border border-held/30 bg-held-soft/50 px-3 py-2 text-xs leading-5 text-ink-2">
                <span className="mr-1.5 text-held" aria-hidden="true">
                  ◆
                </span>
                Hinges on: whether the adapter is owned by the domain team.
              </div>
            </ShowcaseCard>
          </Reveal>

          <Reveal delay={60}>
            <ShowcaseCard title="Retrieval provenance">
              <dl className="grid gap-1.5 text-xs">
                {[
                  ["retriever", "dense-scoped · v1-k8"],
                  ["embedding", "ollama:nomic-embed-text:768"],
                  ["corpus", "sha256:4f0c…9ab2"],
                  ["selected", "dependency-direction, ports-and-adapters"],
                ].map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <dt className="w-20 shrink-0 text-ink-3">{key}</dt>
                    <dd className="min-w-0 truncate font-mono text-ink-2">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-sm leading-6 text-ink-2">
                Recorded per candidate, so a finding can be re-examined months later against the
                exact corpus that produced it.
              </p>
            </ShowcaseCard>
          </Reveal>

          <Reveal delay={100}>
            <ShowcaseCard title="Evidence, pinned to the source">
              <Mono className="block text-[11px] text-ink-3">domain/orders.py:4</Mono>
              <div className="mt-1.5 rounded-md border border-rule bg-sunken/70 px-3 py-2">
                <Mono className="block text-[12px] text-ink">from adapters.db import Store</Mono>
              </div>
              <p className="mt-2.5 text-sm leading-6 text-ink-2">
                Excerpts are pinned when the review is composed, so the argument stays readable even
                after the code moves on.
              </p>
            </ShowcaseCard>
          </Reveal>

          <Reveal delay={140}>
            <ShowcaseCard title="Clarification, not chat">
              <p className="text-sm font-semibold leading-6 text-ink">
                Who owns the persistence adapter?
              </p>
              <p className="mt-1 text-xs leading-5 text-ink-3">
                Facet: decision · affects 2 candidates
              </p>
              <div className="mt-2.5 rounded-md border border-rule bg-surface-2 px-3 py-2 text-sm leading-6 text-ink-2">
                The platform team owns it; the domain team consumes it through the port.
              </div>
              <p className="mt-2.5 text-sm leading-6 text-ink-2">
                The answer becomes case revision 2, and both candidates are judged again.
              </p>
            </ShowcaseCard>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section className="py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <Reveal>
          <SectionIntro
            eyebrow="Capabilities"
            title="What the product actually does"
            body="No claims that cannot be checked against a review you have run."
          />
        </Reveal>
        <div className="mt-9 grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.title} delay={index * 50}>
              <article className="flex h-full flex-col rounded-lg border border-rule bg-surface p-5">
                <h3 className="font-display text-base font-semibold tracking-tight text-ink">
                  {feature.title}
                </h3>
                <p className="mt-2 flex-1 text-sm leading-6 text-ink-2">{feature.body}</p>
                <ul className="mt-3 grid gap-1 border-t border-rule pt-3">
                  {feature.points.map((point) => (
                    <li key={point} className="flex gap-2 text-xs leading-5 text-ink-3">
                      <span aria-hidden="true" className="text-ink-3">
                        ·
                      </span>
                      {point}
                    </li>
                  ))}
                </ul>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function ArchitectureSection() {
  return (
    <section id="architecture" className="border-t border-rule bg-surface/60 py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-start">
          <Reveal>
            <SectionIntro
              eyebrow="Architecture"
              title="Three layers, each with one job"
              body="ArchCompass is a domain with two infrastructure dependencies, not a wrapper around a framework."
            />
          </Reveal>
          <div className="grid gap-2.5">
            {[
              [
                "LangGraph",
                "workflow",
                "Holds the review as a graph: analyse, detect, retrieve, judge, ask, compose, record — with the interrupt that waits for a human answer.",
              ],
              [
                "LangChain",
                "model and RAG infrastructure",
                "Provider adapters, structured output, embeddings and the vector index behind policy retrieval.",
              ],
              [
                "ArchCompass domain",
                "product concepts",
                "Atlas, candidate, policy, finding, question, case, review, delta, decision. None of it knows which model is selected.",
              ],
            ].map(([name, role, body], index) => (
              <Reveal key={name} delay={index * 60}>
                <div className="rounded-lg border border-rule bg-surface p-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <Mono className="text-[13px] font-semibold text-ink">{name}</Mono>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">
                      {role}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm leading-6 text-ink-2">{body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function FaqSection() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section id="faq" className="py-14 sm:py-20">
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
                    className="flex w-full items-center justify-between gap-4 py-4 text-left"
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
    <section className="border-t border-rule py-14 sm:py-20">
      <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
        <Reveal>
          <h2 className="font-display text-3xl font-semibold tracking-[-0.02em] text-ink sm:text-4xl">
            Review your repository with context, not guesswork.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-base leading-7 text-ink-2">
            Point ArchCompass at a repository. It will map it, judge what it finds against your
            policies, and tell you what it could not decide on its own.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
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
    <footer className="border-t border-rule bg-surface/60">
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
              <li>
                <Link to="/start" className="text-ink-2 hover:text-ink">
                  Start a review
                </Link>
              </li>
              <li>
                <Link to="/reviews" className="text-ink-2 hover:text-ink">
                  Reviews
                </Link>
              </li>
              <li>
                <Link to="/policies" className="text-ink-2 hover:text-ink">
                  Policies
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">
              Workspace
            </div>
            <ul className="mt-2.5 grid gap-1.5">
              <li>
                <Link to="/repositories" className="text-ink-2 hover:text-ink">
                  Repositories
                </Link>
              </li>
              <li>
                <Link to="/cases" className="text-ink-2 hover:text-ink">
                  Architecture cases
                </Link>
              </li>
              <li>
                <Link to="/settings" className="text-ink-2 hover:text-ink">
                  Models
                </Link>
              </li>
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
                  <span className="font-mono text-[13px]">Furkan-rgb/arch_compass</span>
                </a>
              </li>
              <li>
                <a href="#architecture" className="text-ink-2 hover:text-ink">
                  Architecture
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
        Analysis runs locally. Only candidate evidence, the architecture case and retrieved policies
        are sent to the model you selected.
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
    <div className="max-w-2xl">
      <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-ink-3">{eyebrow}</div>
      <h2 className="mt-2 font-display text-2xl font-semibold tracking-[-0.02em] text-ink sm:text-3xl">
        {title}
      </h2>
      {body ? <p className="mt-3 text-base leading-7 text-ink-2">{body}</p> : null}
    </div>
  );
}

function ShowcaseCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="h-full rounded-lg border border-rule bg-surface p-5">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3">{title}</div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <a
        href="#landing-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-canvas"
      >
        Skip to content
      </a>
      <LandingNav />
      <main id="landing-main" tabIndex={-1} className="outline-none">
        <Hero />
        <PipelineSection />
        <PrinciplesSection />
        <ShowcaseSection />
        <FeaturesSection />
        <ArchitectureSection />
        <FaqSection />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
