import { useState } from "react";

import type { Finding, Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, shortId, verdictOf } from "../../lib/format";
import { Badge, Tag, VerdictBadge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { ChevronDown } from "../../ui/icons";
import { MetaList, MetaRow, Mono, PathRef } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { deltaStateOf } from "./attention-queue";
import { DecisionBar } from "./decision-bar";

function Section({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-rule px-4 py-4 sm:px-5", className)}>
      <Label>{label}</Label>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

/**
 * One architecture assessment, read top to bottom: what was found, why it matters, what the
 * repository shows, which policies bear on it, and what the team decides.
 *
 * Provenance is real but secondary — it lives behind a disclosure so the assessment reads as
 * an argument rather than as a debug dump.
 */
export function FindingDetail({
  review,
  finding,
  onOpenContext,
}: {
  review: Review;
  finding: Finding;
  onOpenContext?: () => void;
}) {
  const [technical, setTechnical] = useState(false);
  const descriptor = verdictOf(finding.verdict);
  const delta = deltaStateOf(review, finding.candidate.id);
  const measurements = Object.entries(finding.candidate.measurements);

  return (
    <article
      aria-labelledby={`finding-${finding.candidate.id}`}
      className="animate-fade overflow-hidden rounded-lg border border-rule bg-surface shadow-panel"
    >
      <header
        className={cn(
          "border-b border-rule px-4 py-4 sm:px-5",
          descriptor.tone === "material" && "bg-material-soft/40",
          descriptor.tone === "held" && "bg-held-soft/40",
          descriptor.tone === "cleared" && "bg-cleared-soft/30",
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <VerdictBadge verdict={finding.verdict} />
          <Tag>
            <span className="font-mono">{finding.candidate.pattern}</span>
          </Tag>
          {delta ? <Tag>{humanise(delta)} candidate</Tag> : null}
          {finding.reused_from_review_id ? (
            <Tag>Reused from review {shortId(finding.reused_from_review_id, 8)}</Tag>
          ) : null}
          {onOpenContext ? (
            <Button variant="ghost" size="sm" className="ml-auto" onClick={onOpenContext}>
              Judgement context
            </Button>
          ) : null}
        </div>
        <h2
          id={`finding-${finding.candidate.id}`}
          className="mt-2.5 font-display text-xl font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-[26px]"
        >
          {finding.candidate.summary}
        </h2>
        <p className="mt-1.5 text-xs text-ink-3">{descriptor.description}</p>
      </header>

      <Section label="Why this matters" className="border-t-0">
        <p className="max-w-3xl whitespace-pre-line text-[15px] leading-7 text-ink-2">
          {finding.reasoning}
        </p>
      </Section>

      {finding.hinge ? (
        <Section label="What the judgement hinges on">
          <div className="rounded-md border border-held/30 bg-held-soft/60 px-3.5 py-3 text-sm leading-6 text-ink-2">
            <span aria-hidden="true" className="mr-2 text-held">
              ◆
            </span>
            {finding.hinge}
          </div>
        </Section>
      ) : null}

      {finding.recommended_response ? (
        <Section label="Recommended response">
          <div className="rounded-md border-l-2 border-accent bg-accent-soft/60 px-3.5 py-3 text-sm leading-6 text-ink-2">
            {finding.recommended_response}
          </div>
        </Section>
      ) : null}

      <Section label={`Involved code · ${finding.candidate.participants.length}`}>
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
      </Section>

      {finding.evidence.length ? (
        <Section label={`Evidence from the repository · ${finding.evidence.length}`}>
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
        </Section>
      ) : null}

      {finding.policies.length ? (
        <Section label={`Policies that bear on this · ${finding.policies.length}`}>
          <ul className="grid gap-2">
            {finding.policies.map((bearing) => (
              <li
                key={bearing.policy_id}
                className="rounded-md border border-rule bg-surface-2 px-3 py-2.5"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-semibold text-ink">{bearing.policy_title}</span>
                  <Mono className="text-[11px] text-ink-3">{bearing.policy_id}</Mono>
                </div>
                <p className="mt-1 text-sm leading-6 text-ink-2">{bearing.reasoning}</p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section label="Standing decision">
        <DecisionBar review={review} finding={finding} />
      </Section>

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
                    {measurements.map(([key, value]) => (
                      <Tag key={key}>
                        {humanise(key)} <Mono className="text-[11px]">{value}</Mono>
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
