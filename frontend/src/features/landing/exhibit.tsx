import { useState } from "react";

import { cn } from "../../lib/cn";
import { humanise, plural, splitQualified, verdictOf } from "../../lib/format";
import { buttonClass } from "../../ui/button";
import { ChevronDown } from "../../ui/icons";
import { Mark } from "../../ui/mark";
import { Mono, TONE_EDGE, TONE_TEXT } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { CHOICES } from "../review/decision-bar";
import { deltaStateOf, needsAttention, orderedFindings } from "../review/docket-rules";
import { FindingBody } from "../review/finding-detail";
import { CASE_FILE, LEAD_CANDIDATE_ID } from "./case-file";

/**
 * The docket, on the landing page, running on a written-out review.
 *
 * The section this belongs to is the one place the page shows the product rather than
 * describing it, so what it shows has to *be* the product: `FindingBody` here is the same
 * component the workbench opens a row into, reading the same `Review` and `Finding` off the
 * same types. Nothing about the assessment is redrawn — not the attribution lines, not the
 * measurement list, not the evidence column, not the folds. When the workbench's finding
 * surface changes, this changes with it, which is the whole reason it is built this way: the
 * hand-drawn version it replaced kept a device — an attribution gutter — that the product
 * had already deleted.
 *
 * Two things are pictures rather than the real components, and both are pictures because the
 * real one talks to the API:
 *
 * - `DecisionBar` reads and writes standing decisions, and binds `A`/`P`/`W` at the document.
 *   On a marketing page that is a request nobody asked for and a keystroke that would record
 *   a decision against a repository that does not exist. The labels still come from its own
 *   `CHOICES`, so the three words cannot drift. What does not follow from "not a control" is
 *   "not readable": the three words are the "you decide" of this section's headline, so they
 *   are a labelled list with a caption saying they are a still, rather than the `aria-hidden`
 *   button-shaped spans they were.
 * - `Docket` itself carries the filters, the keyboard walk and the clarification round, all
 *   of which mutate. What is kept is the shape a reader has to recognise: a column of rows,
 *   each stating its own claim, opening in place.
 */

/** The identity a row is led by, which is the first participant's name. */
function identityOf(summary: string, qualified?: string) {
  return qualified ?? summary;
}

function Row({
  candidateId,
  open,
  onToggle,
}: {
  candidateId: string;
  open: boolean;
  onToggle: () => void;
}) {
  const finding = CASE_FILE.findings.find((item) => item.candidate.id === candidateId)!;
  const descriptor = verdictOf(finding.verdict);
  const identity = identityOf(
    finding.candidate.summary,
    finding.candidate.participants[0]?.qualified_name,
  );
  const { namespace, leaf } = splitQualified(identity);
  const delta = deltaStateOf(CASE_FILE, candidateId);
  // No decision has been taken against any of these, so `needsAttention` is deciding on the
  // verdict alone — which is what makes the cleared row settle and the other two not.
  const settled = !needsAttention(finding);
  const panelId = `exhibit-panel-${candidateId}`;
  const headingId = `exhibit-${candidateId}`;

  return (
    // The workbench's row is an `<article aria-labelledby>` over an `sr-only` heading naming
    // the candidate and its claim, which is what makes a long list navigable by heading. This
    // one had neither, so the section claiming to be the real component had already drifted in
    // the one place a screen reader depends on: three anonymous regions holding three buttons
    // whose names were a run-together string of identifier, verdict, claim and pattern.
    <article
      aria-labelledby={headingId}
      className={cn(
        "border-b border-l-[3px] border-rule last:border-b-0",
        settled ? "border-l-transparent" : TONE_EDGE[descriptor.tone],
        open && "bg-surface",
      )}
    >
      <h2 id={headingId} className="sr-only">
        {identity} — {finding.candidate.summary}
      </h2>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        // The whole qualified name, because the namespace beside it truncates and the leaf is
        // the only half that wraps. The workbench's row carries the same attribute for the
        // same reason; the three names here are short today, and the guard was still missing.
        title={identity}
        onClick={onToggle}
        // `--sunken` for the hover, never `--surface-2`. This row sits in a panel on
        // `--surface`, inside a section whose ground is `--surface-2` and under a header strip
        // that is also `--surface-2` — so one token was being asked to be a page ground, a
        // header and a pointer state within 200px, and against the panel it is a 1.04:1 change
        // in light, which is no feedback at all. `--sunken` is the token the design system
        // names for a hover, and it is a 1.13:1 step here.
        className={cn(
          "flex min-h-14 w-full items-start gap-3 px-4 py-3 text-left transition sm:px-5",
          open ? "bg-surface" : "hover:bg-sunken",
        )}
      >
        <Mark
          shape={descriptor.glyph}
          className={cn(
            "mt-px size-[15px] shrink-0",
            settled ? "text-ink-3" : TONE_TEXT[descriptor.tone],
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            {namespace ? (
              <span className="min-w-0 truncate font-mono text-[11px] text-ink-3">
                {namespace}.
              </span>
            ) : null}
            <span
              className={cn(
                "font-mono text-[14px] font-medium leading-[1.35] [overflow-wrap:anywhere]",
                settled ? "text-ink-2" : "text-ink",
              )}
            >
              {leaf}
            </span>
            {!settled ? (
              // The block-label recipe, and deliberately not `Label`: this one is inline in
              // a row of baselines rather than a block above one, and it takes the verdict's
              // tone instead of the meta grey. What it had no excuse for was the tracking —
              // `0.11em` was a paste, and `0.08em` is the value the type scale names.
              <span
                className={cn(
                  "text-[11px] font-bold uppercase tracking-[0.08em]",
                  TONE_TEXT[descriptor.tone],
                )}
              >
                {descriptor.label}
              </span>
            ) : null}
          </span>
          <span
            className={cn("mt-1 text-[13px] leading-[1.5] text-ink-2", open ? "block" : "line-clamp-2")}
          >
            {finding.candidate.summary}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-3">
            <span>{humanise(finding.candidate.pattern)}</span>
            {delta && delta !== "unchanged" ? <span>· {humanise(delta)} this review</span> : null}
            {settled ? <span>· nothing outstanding</span> : null}
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn("mt-0.5 size-4 shrink-0 text-ink-3 transition", open && "rotate-180")}
        />
      </button>

      {open ? (
        <div id={panelId} className="animate-expand border-t border-rule">
          <FindingBody review={CASE_FILE} finding={finding} />
          {/* A picture of `DecisionBar`, for the reason given at the top of this file. */}
          <div className="border-t border-rule-strong px-4 py-4 sm:px-5">
            <Label>Standing decision</Label>
            <p className="mt-1.5 max-w-[58ch] text-sm leading-6 text-ink-2">
              Nobody has decided this.
            </p>
            {/* A list, not a control group, and announced rather than hidden.
                These three words are the "you decide" in the section's own headline, and they
                were `aria-hidden` button-shaped spans: a screen reader was told nothing at
                all, and a sighted reader got a primary-looking action that swallowed the
                click. Keeping `buttonClass` is what stops the picture drifting from the real
                control, so the honesty has to come from the markup and the caption instead —
                `role="list"` because `list-style: none` costs a `<ul>` its semantics in
                Safari, `cursor-default` because nothing here is pressable. */}
            <ul role="list" aria-label="The three decisions a person can record" className="mt-3 flex flex-wrap gap-2">
              {CHOICES.map((choice, position) => (
                <li
                  key={choice.id}
                  className={cn(
                    buttonClass(position === 0 ? "primary" : "secondary", "md"),
                    "cursor-default select-none",
                  )}
                >
                  {choice.label}
                </li>
              ))}
            </ul>
            <Mono className="mt-2.5 block text-ink-3">
              Shown, not live · the real controls record against a branch
            </Mono>
            <p className="mt-3 max-w-[56ch] text-[12px] leading-5 text-ink-2">
              Whatever the team chooses stays with the branch, with the reasoning and the name on
              it, and the next review reads it before it judges again.
            </p>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function CaseFileDocket() {
  const [open, setOpen] = useState<string | null>(LEAD_CANDIDATE_ID);
  const findings = orderedFindings(CASE_FILE);
  const outstanding = findings.filter((finding) => needsAttention(finding)).length;

  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-surface">
      {/* What the workbench puts above the docket: which repository, at which commit, and how
          much of the review is left. Counts are orientation, read once, on the way to work. */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-rule bg-surface-2 px-4 py-3 sm:px-5">
        <Mono className="text-[13px] font-semibold tracking-tight text-ink">
          payments-platform · main @ {CASE_FILE.repository.commit?.slice(0, 7)}
        </Mono>
        <Mono className="text-[11px] text-ink-3">
          Review {CASE_FILE.sequence} · {plural(findings.length, "candidate")} ·{" "}
          <span className="font-semibold text-ink">{outstanding}</span> not decided
        </Mono>
      </div>
      {findings.map((finding) => (
        <Row
          key={finding.candidate.id}
          candidateId={finding.candidate.id}
          open={open === finding.candidate.id}
          onToggle={() =>
            setOpen((current) =>
              current === finding.candidate.id ? null : finding.candidate.id,
            )
          }
        />
      ))}
    </div>
  );
}
