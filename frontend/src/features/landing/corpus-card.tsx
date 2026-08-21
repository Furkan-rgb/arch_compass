import { useEffect, useState } from "react";

import { cn } from "../../lib/cn";
import { type Tone, strengthOf, verdictOf } from "../../lib/format";
import { Mark } from "../../ui/mark";
import { Mono } from "../../ui/meta";

/**
 * The landing hero: a policy, and the finding it produced.
 *
 * This is a specimen — Home reads nothing from the workspace, by design — but every field
 * below is shaped like the record it stands for, because a hero that invents a field is a
 * promise the product cannot keep:
 *
 * - `title`, `id`, `strength`, `description` are a `Policy`, and the three quoted here are
 *   the real bundled ones, verbatim from `src/archcompass/policies/general/*.md`.
 * - `retrieved` and `bore` are the two counts the workbench already prints:
 *   `RetrievalProvenance.selected_policy_ids.length` against `Finding.policies.length`.
 *   Retrieval pulls several policies; only some of them bear on the verdict, and saying so
 *   is the most honest number on the card.
 * - `reasoning` is a `PolicyBearing.reasoning` — the model's account of how *this* policy
 *   bore on *this* candidate. It is not the policy's text. `PolicyBearingResponse` carries
 *   `policy_id`, `policy_title` and `reasoning` and nothing else, so a finding surface
 *   could not quote a policy body even if it wanted to.
 * - `verdict` is a three-value `Verdict`. There is no score anywhere on this card because
 *   there is no score anywhere in the domain: the model returns `FindingOutput.material`,
 *   a bool.
 *
 * Only the finding's own sentences are written for the page.
 */

type Bearing = {
  policy: { id: string; title: string; strength: string; description: string };
  /** Bundled corpus or this workspace's own directory — `PolicyOrigin`. */
  origin: string;
  retrieved: number;
  candidate: string;
  verdict: string;
  finding: string;
  reasoning: string;
  hinge?: string;
  /** The other policy that bore, if one did. */
  also?: string;
  source: string;
};

const BEARINGS: Bearing[] = [
  {
    policy: {
      id: "delay-premature-abstraction",
      title: "Delay abstractions until variation is credible",
      strength: "guidance",
      description:
        "An abstraction introduced before its variation exists is a guess about a boundary, paid for in interfaces, indirection, and configuration. Wait until a second real implementation or a committed change shows where the seam actually is.",
    },
    origin: "bundled corpus",
    retrieved: 6,
    candidate: "payments.gateway.PaymentGateway",
    verdict: "material",
    finding: "The payment provider abstraction carries a single implementation",
    reasoning:
      "The protocol has had one implementation since it was introduced, and it names stripe_retry_after — so the variation this abstraction was guessing at never arrived, and the interface now encodes the provider it was meant to keep replaceable.",
    also: "design-for-replaceability",
    source: "payments/gateway.py:12–26 · google:gemini-3.6",
  },
  {
    policy: {
      id: "give-state-one-writer",
      title: "Give every piece of shared state one writing owner",
      strength: "guidance",
      description:
        "State written by several components has no invariant anyone can enforce. Each datum gets one component that writes it, and everyone else reads through that component's interface or through a copy it publishes.",
    },
    origin: "bundled corpus",
    retrieved: 5,
    candidate: "orders.Repository",
    verdict: "held",
    finding: "The orders domain imports the persistence adapter directly",
    reasoning:
      "Five modules outside the domain reach this adapter and two of them write through it, so the state has more than one writer. Whether that breaks the policy depends on which component is meant to own it.",
    hinge:
      "whether the platform team owns the adapter or the domain does. The repository cannot say, so the review is holding until you answer.",
    source: "domain/orders.py:4 · awaiting an answer since review 4",
  },
  {
    policy: {
      id: "explicit-source-of-truth",
      title: "Make the source of truth explicit",
      strength: "guidance",
      description:
        "For every piece of authoritative state or configuration, one place defines it and everything else is visibly derived from that place. When several sources can supply the same value and precedence is implicit, the system's real behaviour is discovered by experiment rather than by reading.",
    },
    origin: "bundled corpus",
    retrieved: 7,
    candidate: "billing.invoice.InvoiceBoundary",
    verdict: "cleared",
    finding: "The invoice boundary is earning its place",
    reasoning:
      "Every posting path resolves through this boundary and no other module writes the ledger directly, so the authoritative place is both singular and visible. The seam does exactly what the policy asks of it.",
    also: "prefer-deep-modules",
    source: "billing/invoice.py:8 · unchanged since review 2",
  },
];

/** How many policies the bundled `general` corpus actually ships. */
const CORPUS_SIZE = 54;

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink",
  marked: "text-ink",
  material: "text-material",
  held: "text-held",
  cleared: "text-cleared",
};

const CYCLE_MS = 6200;

/**
 * One specimen: the policy, what retrieval did with it, and the finding it produced.
 *
 * All three are rendered at once and stacked in a single grid cell, with the inactive two
 * held at `visibility: hidden`. A hidden element still occupies its space, so the grid
 * track is exactly as tall as the tallest specimen and the card never changes height as
 * they cycle.
 *
 * This replaced a `min-h-[684px]` measured off one browser at one text size, which had
 * three pixels of headroom: at a 20px root size the held specimen wrapped one extra line,
 * grew to 701px, and pushed the whole page down every six seconds. A layout that has to be
 * re-measured whenever the copy or the font changes is a layout that will be wrong again.
 */
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
      {/* The policy, as the Policies surface shows it. Strength is glyph and weight, never
          a hue: a required policy is the one to read first, not an alarm. */}
      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center gap-2">
          <Mono
            className={cn(
              "text-[9.5px] font-semibold uppercase tracking-[0.14em]",
              strength.tone === "marked" ? "text-ink" : "text-ink-3",
            )}
          >
            <Mark shape={strength.glyph} className="mr-0.5 align-[-0.09em]" />
            {strength.label}
          </Mono>
          <Mono className="text-[9.5px] uppercase tracking-[0.14em] text-ink-3">
            · {bearing.origin}
          </Mono>
        </div>
        <h3 className="mt-2 font-display text-[15px] font-semibold leading-[1.36] tracking-tight text-ink">
          {bearing.policy.title}
        </h3>
        <Mono className="mt-1.5 block text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
          {bearing.policy.id}
        </Mono>
        <p className="mt-3 border-l-2 border-rule-strong pl-3.5 text-[13px] leading-[1.62] text-ink-2">
          {bearing.policy.description}
        </p>
      </div>

      {/* Retrieval pulled these; only some of them bore. Both numbers are recorded, and
          the difference between them is the point. */}
      <div className="flex items-center gap-2 border-y border-rule bg-surface-2 px-5 py-2">
        <Mono className="text-[9.5px] uppercase tracking-[0.11em] text-ink-3">
          <span className="font-semibold text-ink">{bearing.retrieved}</span> retrieved ·{" "}
          <span className="font-semibold text-ink">{bore}</span> bore on the judgement
        </Mono>
      </div>

      <div className="flex-1 px-5 pb-4 pt-3.5">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <Mark
            shape={verdict.glyph}
            className={cn("size-[11px] self-center", TONE_TEXT[verdict.tone])}
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

        <Mono className="mt-3 block text-[9.5px] font-semibold uppercase tracking-[0.13em] text-ink-3">
          How it bore
        </Mono>
        <p className="mt-1.5 text-[13px] leading-[1.62] text-ink-2">{bearing.reasoning}</p>

        {bearing.hinge ? (
          <p className="mt-3 rounded-md border border-held/30 bg-held-soft px-3 py-2.5 text-[12.5px] leading-[1.55] text-ink-2">
            <span className="font-semibold text-held">Hinges on:</span> {bearing.hinge}
          </p>
        ) : null}

        {bearing.also ? (
          <Mono className="mt-3 block text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
            also bore: {bearing.also}
          </Mono>
        ) : null}
        <Mono className="mt-2 block text-[10.5px] text-ink-3 [overflow-wrap:anywhere]">
          {bearing.source}
        </Mono>
      </div>
    </div>
  );
}

export function CorpusCard() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    const timer = setInterval(() => setIndex((current) => (current + 1) % BEARINGS.length), CYCLE_MS);
    return () => clearInterval(timer);
  }, [paused]);

  return (
    <div
      // Named as a group because it is one: the policy above and the finding below are a
      // single specimen that changes together, and a reader arriving by keyboard should be
      // told that before the pieces arrive one at a time.
      role="group"
      aria-label="A policy and the finding it produced"
      // The one shadow on the page. A hero card is the other thing besides a drawer that
      // genuinely leaves the surface.
      className="overflow-hidden rounded-lg border border-rule bg-surface shadow-hero"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="flex items-center justify-between gap-3 border-b border-rule bg-surface-2 px-3.5 py-2">
        <Mono className="text-[10px] tracking-[0.06em] text-ink-3">Your policy corpus</Mono>
        <Mono className="text-[10px] tracking-[0.06em] text-ink-3">{CORPUS_SIZE} policies</Mono>
      </div>

      {/* One cell, three specimens in it. The browser sizes the track to the tallest, so
          nothing below the card moves when the specimen changes. */}
      <div className="grid">
        {BEARINGS.map((bearing, position) => (
          <Specimen key={bearing.policy.id} bearing={bearing} hidden={position !== index} />
        ))}
      </div>

      <div role="group" aria-label="Example bearings" className="flex border-t border-rule">
        {BEARINGS.map((item, position) => {
          const label = verdictOf(item.verdict).label;
          const selected = position === index;
          return (
            <button
              key={item.policy.id}
              type="button"
              aria-pressed={selected}
              onClick={() => setIndex(position)}
              className={cn(
                "relative flex-1 border-r border-rule px-1 py-3 font-mono text-[10px] uppercase tracking-[0.1em] transition last:border-r-0",
                selected ? "bg-sunken text-ink" : "text-ink-3 hover:text-ink",
              )}
            >
              {selected ? (
                <span
                  aria-hidden="true"
                  className="absolute inset-x-0 -top-px h-0.5 bg-ink"
                />
              ) : null}
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
