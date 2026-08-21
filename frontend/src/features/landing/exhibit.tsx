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
 *   `CHOICES`, so the three words cannot drift.
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

  return (
    <article
      className={cn(
        "border-b border-l-[3px] border-rule last:border-b-0",
        settled ? "border-l-transparent" : TONE_EDGE[descriptor.tone],
        open && "bg-surface",
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className={cn(
          "flex min-h-14 w-full items-start gap-3 px-4 py-3 text-left transition sm:px-5",
          open ? "bg-surface" : "hover:bg-surface-2",
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
              <span
                className={cn(
                  "text-[10px] font-bold uppercase tracking-[0.11em]",
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
            <div aria-hidden="true" className="mt-3 flex flex-wrap gap-2">
              {CHOICES.map((choice, position) => (
                <span
                  key={choice.id}
                  className={buttonClass(position === 0 ? "primary" : "secondary", "md")}
                >
                  {choice.label}
                </span>
              ))}
            </div>
            <p className="mt-3 max-w-[56ch] text-[12px] leading-5 text-ink-3">
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
          <span className="font-semibold text-ink">{outstanding}</span> still want a person
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
