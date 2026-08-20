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

/**
 * One section of the assessment, with what supports it in the margin beside it.
 *
 * The context used to be a third column, which meant reading a paragraph here and finding
 * the case that produced it over there — a correlation the reader had to make by eye, and
 * which cost the argument itself two hundred pixels of width. A citation belongs next to
 * what it supports, so it sits in the margin of the row it belongs to and stacks underneath
 * when the pane is too narrow to have a margin at all.
 */
function Row({
  label,
  note,
  children,
  className,
  full = false,
}: {
  label: string;
  note?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  full?: boolean;
}) {
  return (
    <section
      className={cn(
        "grid gap-x-7 gap-y-4 border-t border-rule px-4 py-4 sm:px-6",
        // Prose is measured; code is not. A row that carries an excerpt spans the margin
        // too, because an excerpt read at 62 characters is an excerpt with its own
        // scrollbar.
        full ? "grid-cols-1" : "lg:grid-cols-[minmax(0,1fr)_15rem]",
        className,
      )}
    >
      <div className="min-w-0">
        <Label>{label}</Label>
        <div className="mt-2.5">{children}</div>
      </div>
      {note && !full ? (
        <aside className="min-w-0 lg:border-l lg:border-rule lg:pl-5">{note}</aside>
      ) : null}
    </section>
  );
}

/** A single fact in the margin: a small dim key and something short under it. */
function Note({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="text-[10px] font-bold uppercase tracking-[0.11em] text-ink-3">{label}</div>
      <div className="mt-1 text-[12.5px] leading-[1.5] text-ink-2 [overflow-wrap:anywhere]">
        {children}
      </div>
    </div>
  );
}

function NoteList({ items }: { items: readonly string[] }) {
  if (!items.length) return <span className="text-ink-3">None recorded.</span>;
  return (
    <ul className="grid gap-1.5">
      {items.map((item, index) => (
        <li key={index} className="relative pl-3 before:absolute before:left-0 before:top-[0.6em] before:h-px before:w-1.5 before:bg-ink-3">
          {item}
        </li>
      ))}
    </ul>
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
  const measurements = finding.candidate.measurements;
  const retrieval = review.retrieval_manifest.find(
    (entry) => entry.candidate_id === finding.candidate.id,
  );
  const answered = review.case.answers.filter((answer) => answer.status === "answered");

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

      <Row
        label="Why this matters"
        className="border-t-0"
        note={
          <>
            <Note label="Judged against">
              {review.case.goal || (
                <span className="text-ink-3">No architecture goal has been stated.</span>
              )}
            </Note>
            <Note label={`Constraints · ${review.case.constraints.length}`}>
              <NoteList items={review.case.constraints.map((item) => item.text)} />
            </Note>
            <Note label="Case revision">{review.case.revision}</Note>
          </>
        }
      >
        <p className="max-w-[62ch] whitespace-pre-line text-[15px] leading-7 text-ink-2">
          {finding.reasoning}
        </p>
      </Row>

      {finding.hinge ? (
        <Row
          label="What the judgement hinges on"
          note={
            <>
              <Note label={`Answered so far · ${answered.length}`}>
                <NoteList items={answered.map((answer) => answer.value ?? "")} />
              </Note>
              <Note label="What happens next">
                Answering this produces the next case revision, and the candidates it touches
                are judged again.
              </Note>
            </>
          }
        >
          <div className="rounded-md border border-held/30 bg-held-soft/60 px-3.5 py-3 text-sm leading-6 text-ink-2">
            <span aria-hidden="true" className="mr-2 text-held">
              ◆
            </span>
            {finding.hinge}
          </div>
        </Row>
      ) : null}

      {finding.recommended_response ? (
        <Row
          label="Recommended response"
          note={
            <>
              <Note label={`Decisions on the case · ${review.case.decisions.length}`}>
                <NoteList items={review.case.decisions.map((item) => item.text)} />
              </Note>
            </>
          }
        >
          <div className="max-w-[62ch] rounded-md border-l-2 border-accent bg-accent-soft/60 px-3.5 py-3 text-sm leading-6 text-ink-2">
            {finding.recommended_response}
          </div>
        </Row>
      ) : null}

      <Row
        label={`Involved code · ${finding.candidate.participants.length}`}
        note={
          measurements.length ? (
            <Note label="Measured">
              <NoteList
                items={measurements.map((item) =>
                  // A structural proxy is a hint the parse could not confirm, and a reader
                  // deciding on the number has to be told which kind of number it is.
                  `${humanise(item.name)}: ${item.value}${item.unit ? ` ${item.unit}` : ""}${
                    item.nature === "structural_proxy" ? " (proxy)" : ""
                  }`,
                )}
              />
            </Note>
          ) : (
            <Note label="Measured">Nothing was counted for this candidate.</Note>
          )
        }
      >
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
      </Row>

      {finding.evidence.length ? (
        <Row full label={`Evidence from the repository · ${finding.evidence.length}`}>
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
          <p className="mt-2.5 text-[11.5px] text-ink-3">
            Quoted from the indexed snapshot, not re-read from disk.
          </p>
        </Row>
      ) : null}

      {finding.policies.length ? (
        <Row
          label={`Policies that bear on this · ${finding.policies.length}`}
          note={
            <>
              <Note label="Retrieved for this candidate">
                {retrieval ? retrieval.selected_policy_ids.length : 0}
              </Note>
              <Note label="Bore on the judgement">{finding.policies.length}</Note>
              {retrieval ? (
                <Note label="Strategy">
                  <Mono className="text-[11px]">
                    {retrieval.retriever}:{retrieval.version}
                  </Mono>
                </Note>
              ) : null}
            </>
          }
        >
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
        </Row>
      ) : null}

      <Row full label="Standing decision">
        <DecisionBar review={review} finding={finding} />
      </Row>

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
