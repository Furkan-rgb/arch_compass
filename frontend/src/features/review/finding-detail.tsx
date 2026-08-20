import { useState } from "react";

import type { Finding, Review } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, humanise, shortId, verdictOf } from "../../lib/format";
import { Badge, Tag, VerdictBadge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { Gutter, GutterBlock } from "../../ui/gutter";
import { ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono, PathRef } from "../../ui/meta";
import { deltaStateOf, useStandingDecisions } from "./attention-queue";
import { DecisionBar } from "./decision-bar";

/**
 * A fact that supports the block above it, said in one line.
 *
 * The supporting context used to be a third column down the right of every row, which cost
 * the argument itself two hundred pixels and asked the reader to correlate by eye. The
 * gutter now owns the left margin, so a citation sits under what it supports rather than
 * beside it, and the whole of it stays a click away in the judgement context.
 */
function Footnote({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 max-w-[62ch] font-mono text-[10.5px] leading-relaxed text-ink-3 [overflow-wrap:anywhere]">
      {children}
    </p>
  );
}

/**
 * One architecture assessment, registered against the attribution gutter — so at every
 * point on the way down it is legible whose voice is speaking.
 *
 * The order is the order the three jobs happen in. What the machine measured comes first,
 * because a verdict is worth nothing without the evidence that produced it. What the model
 * concluded comes second, and is the only thing on the page set in a serif: it is an
 * argument the reader is meant to weigh, not a result they are meant to accept. What the
 * team decides comes last and is the only part of the page that is a control.
 *
 * Provenance is not a section any more. The gutter carries it beside the voice it belongs
 * to, which is the one place it means something; `Technical detail` keeps the debug dump.
 */
export function FindingDetail({
  review,
  finding,
  next,
  onNext,
  onAnswer,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  /** The next candidate still wanting a person, so the control can name where it goes. */
  next?: Finding | null;
  onNext?: () => void;
  onAnswer?: () => void;
  onOpenContext?: () => void;
}) {
  const [technical, setTechnical] = useState(false);
  const decisions = useStandingDecisions(review);
  const descriptor = verdictOf(finding.verdict);
  const delta = deltaStateOf(review, finding.candidate.id);
  const measurements = finding.candidate.measurements;
  const retrieval = review.retrieval_manifest.find(
    (entry) => entry.candidate_id === finding.candidate.id,
  );
  const answered = review.case.answers.filter((answer) => answer.status === "answered");
  const decision = decisions.get(finding.candidate.id);
  const identity = finding.candidate.participants[0]?.qualified_name;
  // A held verdict says it is waiting on a person. Which person, and on what — the open
  // question that would settle it, if the round is still open.
  const waitingOn =
    review.status === "awaiting_answers"
      ? review.questions.find((question) =>
          question.candidate_ids.includes(finding.candidate.id),
        )
      : undefined;

  return (
    <article
      aria-labelledby={`finding-${finding.candidate.id}`}
      className="animate-fade overflow-hidden border border-rule bg-surface"
    >
      <Gutter>
        {/* ── Measured ──────────────────────────────────────────────────────────── */}
        <GutterBlock
          voice="Measured"
          who={
            <>
              deterministic
              <br />
              analysis
            </>
          }
        >
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-3">
            <span>{humanise(finding.candidate.pattern)}</span>
            {delta ? <span>· {humanise(delta)}</span> : null}
            {finding.reused_from_review_id ? (
              <span>· reused from {shortId(finding.reused_from_review_id, 8)}</span>
            ) : null}
            {onOpenContext ? (
              <Button variant="ghost" size="sm" className="ml-auto" onClick={onOpenContext}>
                Judgement context
              </Button>
            ) : null}
          </div>
          {/* The identifier leads, because that is what is being looked for. The sentence
              keeps its place underneath, because that is what explains. */}
          <h2
            id={`finding-${finding.candidate.id}`}
            className="mt-2.5 font-mono text-[17px] font-medium leading-snug tracking-[-0.01em] text-ink [overflow-wrap:anywhere] sm:text-[19px]"
          >
            {identity ?? finding.candidate.summary}
          </h2>
          {identity ? (
            <p className="mt-2 max-w-[58ch] text-[14px] leading-relaxed text-ink-2">
              {finding.candidate.summary}
            </p>
          ) : null}
        </GutterBlock>

        <GutterBlock label={`Involved code · ${finding.candidate.participants.length}`}>
          <ul className="flex flex-wrap gap-1.5">
            {finding.candidate.participants.map((participant) => (
              <li key={`${participant.role}-${participant.qualified_name}`}>
                <span className="inline-flex items-center gap-1.5 rounded-xs border border-rule bg-surface-2 px-2 py-1 text-xs">
                  <span className="text-ink-3">{humanise(participant.role)}</span>
                  <Mono className="text-ink">{participant.qualified_name}</Mono>
                </span>
              </li>
            ))}
          </ul>
        </GutterBlock>

        {measurements.length ? (
          <GutterBlock label="What was counted">
            {/* A hairline grid, not a row of cards. These are readings; a reading that has
                been put in a box is asking to be looked at twice. */}
            <div className="grid gap-px border border-rule bg-rule [grid-template-columns:repeat(auto-fit,minmax(11rem,1fr))]">
              {measurements.map((item) => (
                <div key={item.name} className="bg-surface px-3 py-2.5">
                  <div className="font-mono text-[15px] font-medium tabular-nums text-ink">
                    {item.value}
                    {item.unit ? <span className="text-ink-3"> {item.unit}</span> : null}
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] tracking-[0.04em] text-ink-3">
                    {item.name}
                    {item.nature === "structural_proxy" ? " · proxy" : ""}
                  </div>
                  {item.limitations ? (
                    <p className="mt-1.5 text-[10.5px] leading-snug text-ink-3">
                      {item.limitations}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </GutterBlock>
        ) : null}

        {finding.evidence.length ? (
          <GutterBlock label={`Pinned evidence · ${finding.evidence.length}`}>
            <div className="grid gap-2">
              {finding.evidence.map((evidence, index) => (
                <EvidenceBlock
                  key={`${evidence.location?.path}-${index}`}
                  description={evidence.description}
                  path={evidence.location?.path}
                  startLine={evidence.location?.start_line}
                  endLine={evidence.location?.end_line}
                  excerpt={evidence.excerpt}
                />
              ))}
            </div>
            <Footnote>Quoted from the indexed snapshot, not re-read from disk.</Footnote>
          </GutterBlock>
        ) : null}

        {/* ── Judged ────────────────────────────────────────────────────────────── */}
        <GutterBlock
          voice="Judged"
          who={
            <>
              {finding.model_identity}
              <br />
              {retrieval ? `${retrieval.retriever}/${retrieval.version}` : "no retrieval"}
            </>
          }
        >
          <VerdictBadge verdict={finding.verdict} />
          {/* The only serif on the screen. A verdict is an argument the reader is meant to
              weigh and disagree with, and prose you argue with is not set in the same face
              as the buttons beside it. */}
          <p className="mt-3.5 max-w-[60ch] whitespace-pre-line font-read text-[17px] font-light leading-[1.68] text-ink">
            {finding.reasoning}
          </p>
          <Footnote>
            {descriptor.description} Judged against case revision {review.case.revision} and{" "}
            {review.case.constraints.length}{" "}
            {review.case.constraints.length === 1 ? "constraint" : "constraints"}.
          </Footnote>
        </GutterBlock>

        {finding.hinge ? (
          <GutterBlock label="Hinges on">
            <div className="max-w-[60ch] border-l-2 border-held bg-held-soft/60 px-3.5 py-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.11em] text-held">
                Waiting on a person
              </div>
              <p className="mt-1.5 font-read text-[15px] leading-relaxed text-ink">
                {finding.hinge}
              </p>
            </div>
            {waitingOn && onAnswer ? (
              // "Waiting on a person" followed by no way to be that person is a dead end.
              <button
                type="button"
                onClick={onAnswer}
                className="mt-3 rounded-sm border border-held/40 px-2.5 py-1.5 text-xs font-semibold text-held transition hover:bg-held-soft"
              >
                Answer it → {waitingOn.text}
              </button>
            ) : null}
            <Footnote>
              {waitingOn
                ? "Answering produces the next case revision and re-judges what it touches."
                : "No open question covers this. The round was concluded with the uncertainty preserved."}{" "}
              {answered.length} {answered.length === 1 ? "answer" : "answers"} recorded so far.
            </Footnote>
          </GutterBlock>
        ) : null}

        {finding.policies.length ? (
          <GutterBlock label={`Policies it bears on · ${finding.policies.length}`}>
            <ul className="grid max-w-[62ch] gap-2">
              {finding.policies.map((bearing) => (
                <li key={bearing.policy_id} className="border border-rule px-3.5 py-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-[13px] font-semibold text-ink">
                      {bearing.policy_title}
                    </span>
                    <Mono className="text-[10.5px] text-mark">{bearing.policy_id}</Mono>
                  </div>
                  <p className="mt-1.5 font-read text-[14px] leading-relaxed text-ink-2">
                    {bearing.reasoning}
                  </p>
                </li>
              ))}
            </ul>
            {retrieval ? (
              <Footnote>
                {retrieval.selected_policy_ids.length} retrieved for this candidate;{" "}
                {finding.policies.length} bore on the judgement.
              </Footnote>
            ) : null}
          </GutterBlock>
        ) : null}

        {finding.recommended_response ? (
          <GutterBlock label="Recommended response">
            <div className="max-w-[60ch] border-l-2 border-ink pl-3.5">
              <p className="font-read text-[15px] leading-relaxed text-ink">
                {finding.recommended_response}
              </p>
            </div>
            <Footnote>A recommendation, not a change. ArchCompass does not write the fix.</Footnote>
          </GutterBlock>
        ) : null}

        {/* ── Decided ───────────────────────────────────────────────────────────── */}
        <GutterBlock
          voice="Decided"
          who={
            decision ? (
              <>
                {decision.author}
                <br />
                {absoluteTime(decision.decided_at)}
              </>
            ) : (
              // An explicit unknown beats an implied one, and an empty attribution reads as
              // a rendering fault rather than as "nobody has done this yet".
              <>nobody yet</>
            )
          }
        >
          <DecisionBar review={review} finding={finding} />
        </GutterBlock>
      </Gutter>

      <div className="border-t border-rule">
        <button
          type="button"
          onClick={() => setTechnical((open) => !open)}
          aria-expanded={technical}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-xs font-semibold text-ink-3 transition hover:text-ink sm:px-5"
        >
          <span className="uppercase tracking-[0.12em]">Technical detail</span>
          <ChevronDown className={cn("size-4 transition", technical && "rotate-180")} />
        </button>
        {technical ? (
          <div className="animate-expand border-t border-rule bg-surface-2 px-4 py-3 sm:px-5">
            <MetaList>
              <MetaRow label="Candidate">
                <Mono>{finding.candidate.id}</Mono>
              </MetaRow>
              <MetaRow label="Detection">{finding.candidate.detection_rationale}</MetaRow>
              <MetaRow label="Limitations">{finding.candidate.limitations}</MetaRow>
              {measurements.length ? (
                <MetaRow label="Measurements">
                  <span className="flex flex-wrap gap-1.5">
                    {measurements.map((item) => (
                      <Tag key={item.name}>
                        {humanise(item.name)}{" "}
                        <Mono className="text-[11px]">
                          {item.value}
                          {item.unit ? ` ${item.unit}` : ""}
                        </Mono>
                        {item.nature === "structural_proxy" ? (
                          <span
                            className="ml-1 text-[10px] uppercase tracking-[0.08em] text-ink-3"
                            title={item.limitations || "A structural proxy, not a count."}
                          >
                            proxy
                          </span>
                        ) : null}
                      </Tag>
                    ))}
                  </span>
                </MetaRow>
              ) : null}
              <MetaRow label="Judge">
                <Mono>{finding.model_identity}</Mono>
              </MetaRow>
              <MetaRow label="Prompt">
                <Mono>{finding.prompt_identity}</Mono>
              </MetaRow>
              <MetaRow label="Retrieval">
                <Mono>{finding.retrieval_identity}</Mono>
              </MetaRow>
              {finding.evidence[0]?.location ? (
                <MetaRow label="First location">
                  <PathRef
                    path={finding.evidence[0].location.path}
                    line={finding.evidence[0].location.start_line}
                    endLine={finding.evidence[0].location.end_line}
                  />
                </MetaRow>
              ) : null}
            </MetaList>
          </div>
        ) : null}
      </div>

      {/* Where a reader arrives once they have decided. Named rather than jumped to: being
          moved somewhere else the moment a decision lands is the interface concluding you
          were finished with this one. */}
      {onNext && next ? (
        <button
          type="button"
          onClick={onNext}
          aria-label={`Next needing you: ${
            next.candidate.participants[0]?.qualified_name ?? next.candidate.summary
          }`}
          className="flex w-full items-baseline gap-2.5 border-t border-rule bg-surface-2 px-4 py-3 text-left transition hover:bg-sunken sm:px-5"
        >
          <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-3">
            Next needing you
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-ink">
            {next.candidate.participants[0]?.qualified_name ?? next.candidate.summary}
          </span>
          <span aria-hidden="true" className="shrink-0 text-ink-3">
            &rarr;
          </span>
        </button>
      ) : null}
    </article>
  );
}

/** The compact header shown above the detail on small screens, with a way back. */
export function FindingBackBar({ onBack, finding }: { onBack: () => void; finding: Finding }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Button variant="secondary" size="sm" onClick={onBack}>
        ← Queue
      </Button>
      <Badge tone={verdictOf(finding.verdict).tone} glyph={verdictOf(finding.verdict).glyph}>
        {verdictOf(finding.verdict).label}
      </Badge>
    </div>
  );
}
