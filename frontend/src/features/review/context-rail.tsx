import { useState } from "react";

import type { Finding, Review } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, humanise, shortId } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { MetaList, MetaRow, Mono } from "../../ui/meta";
import { Label } from "../../ui/panel";
import { Tabs, TabPanel } from "../../ui/tabs";
import { EmptyState } from "../../ui/states";

/**
 * Why ArchCompass reached the conclusion beside it.
 *
 * Three answers, in the order a sceptical reader asks for them: the human context the
 * judgement was made against, the policies retrieval put in front of the model, and the
 * machinery that produced both.
 */
export function ContextRail({
  review,
  finding,
  className,
}: {
  review: Review;
  finding: Finding | null;
  className?: string;
}) {
  const [tab, setTab] = useState("case");
  const provenance = finding
    ? review.retrieval_manifest.find((item) => item.candidate_id === finding.candidate.id)
    : undefined;

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="border-b border-rule px-3 pt-3">
        <h2 className="font-display text-sm font-semibold tracking-tight text-ink">
          Judgement context
        </h2>
        <p className="mb-2 mt-0.5 text-xs text-ink-3">
          {finding ? "For the selected candidate" : "For this review"}
        </p>
        <Tabs
          label="Judgement context"
          active={tab}
          onChange={setTab}
          items={[
            { id: "case", label: "Case" },
            { id: "policies", label: "Policies", count: finding?.policies.length },
            { id: "provenance", label: "Provenance" },
          ]}
        />
      </div>

      <div className="scrollbar-slim min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <TabPanel id="case" active={tab}>
          <CaseContext review={review} />
        </TabPanel>

        <TabPanel id="policies" active={tab}>
          {!finding ? (
            <EmptyState title="Select a candidate" className="border-0 bg-transparent py-8">
              Retrieved policies are shown per candidate.
            </EmptyState>
          ) : !finding.policies.length ? (
            <EmptyState title="No policy bearing" className="border-0 bg-transparent py-8">
              Retrieval returned no policy that bears on this candidate.
            </EmptyState>
          ) : (
            <ul className="grid gap-2">
              {finding.policies.map((bearing) => (
                <li
                  key={bearing.policy_id}
                  className="rounded-md border border-rule bg-surface-2 p-3"
                >
                  <div className="text-sm font-semibold leading-5 text-ink">
                    {bearing.policy_title}
                  </div>
                  <Mono className="mt-1 block text-[11px] text-ink-3">{bearing.policy_id}</Mono>
                  <p className="mt-1.5 text-xs leading-5 text-ink-2">{bearing.reasoning}</p>
                </li>
              ))}
            </ul>
          )}
        </TabPanel>

        <TabPanel id="provenance" active={tab}>
          <MetaList>
            <MetaRow label="Judge">
              <Mono>{finding?.model_identity ?? review.model_identity}</Mono>
            </MetaRow>
            <MetaRow label="Prompt">
              <Mono>{finding?.prompt_identity ?? review.prompt_identity}</Mono>
            </MetaRow>
            {provenance ? (
              <>
                <MetaRow label="Retriever">
                  <Mono>
                    {provenance.retriever} · v{provenance.version}
                  </Mono>
                </MetaRow>
                <MetaRow label="Embedding">
                  <Mono>{provenance.model_identity || "non-embedding strategy"}</Mono>
                </MetaRow>
                <MetaRow label="Corpus">
                  <Mono className="break-all">{shortId(provenance.corpus_fingerprint, 24)}</Mono>
                </MetaRow>
                {provenance.query_fingerprint ? (
                  <MetaRow label="Query">
                    <Mono className="break-all">{shortId(provenance.query_fingerprint, 24)}</Mono>
                  </MetaRow>
                ) : null}
                <MetaRow label="Selected">
                  <span className="flex flex-wrap gap-1">
                    {provenance.selected_policy_ids.length ? (
                      provenance.selected_policy_ids.map((id) => (
                        <Tag key={id}>
                          <Mono className="text-[11px]">{id}</Mono>
                        </Tag>
                      ))
                    ) : (
                      <span className="text-ink-3">None</span>
                    )}
                  </span>
                </MetaRow>
                {Object.entries(provenance.metadata).map(([key, value]) => (
                  <MetaRow key={key} label={humanise(key)}>
                    <Mono className="break-all">{value}</Mono>
                  </MetaRow>
                ))}
              </>
            ) : (
              <MetaRow label="Retrieval">
                <span className="text-ink-3">
                  Select a candidate to see the retrieval that fed its judgement.
                </span>
              </MetaRow>
            )}
            <MetaRow label="Atlas">
              <span>
                {review.atlas.node_count.toLocaleString()} nodes ·{" "}
                {review.atlas.edge_count.toLocaleString()} edges
              </span>
            </MetaRow>
            <MetaRow label="Parser">
              <Mono>
                {Object.entries(review.atlas.parser_configuration)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(" ") || "—"}
              </Mono>
            </MetaRow>
          </MetaList>
        </TabPanel>
      </div>
    </div>
  );
}

function CaseContext({ review }: { review: Review }) {
  const { case: architectureCase } = review;
  return (
    <div className="grid gap-3">
      <div>
        <Label>Goal</Label>
        <p className="mt-1.5 text-sm leading-6 text-ink">
          {architectureCase.goal || "No architecture goal has been stated yet."}
        </p>
      </div>

      <div>
        <Label>Constraints · {architectureCase.constraints.length}</Label>
        {architectureCase.constraints.length ? (
          <ul className="mt-1.5 grid gap-1.5">
            {architectureCase.constraints.map((constraint, index) => (
              <li
                key={index}
                className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
              >
                <span className="mr-1.5 font-semibold text-accent">
                  {humanise(constraint.facet)}
                </span>
                {constraint.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-xs text-ink-3">None recorded.</p>
        )}
      </div>

      <div>
        <Label>Decisions · {architectureCase.decisions.length}</Label>
        {architectureCase.decisions.length ? (
          <ul className="mt-1.5 grid gap-1.5">
            {architectureCase.decisions.map((decision, index) => (
              <li
                key={index}
                className="rounded-md border border-rule bg-surface-2 px-2.5 py-2 text-xs leading-5 text-ink-2"
              >
                {decision.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-xs text-ink-3">None recorded.</p>
        )}
      </div>

      <div>
        <Label>Clarification answers · {architectureCase.answers.length}</Label>
        {architectureCase.answers.length ? (
          <ul className="mt-1.5 grid gap-1.5">
            {architectureCase.answers.map((answer) => (
              <li
                key={answer.question.id}
                className="rounded-md border border-rule bg-surface-2 px-2.5 py-2"
              >
                <div className="text-xs font-semibold leading-5 text-ink">
                  {answer.question.text}
                </div>
                <div className="mt-1 text-xs leading-5 text-ink-2">
                  {answer.status === "skipped" ? (
                    <span className="text-ink-3">Explicitly skipped</span>
                  ) : (
                    answer.value
                  )}
                </div>
                <div className="mt-1 text-[11px] text-ink-3">
                  {answer.actor} · {absoluteTime(answer.answered_at)}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-xs text-ink-3">No clarification has been answered yet.</p>
        )}
      </div>

      <MetaList className="mt-1 border-t border-rule pt-1">
        <MetaRow label="Revision">{architectureCase.revision}</MetaRow>
        <MetaRow label="Updated">{absoluteTime(architectureCase.updated_at)}</MetaRow>
        <MetaRow label="Case">
          <Mono className="break-all">{architectureCase.id}</Mono>
        </MetaRow>
      </MetaList>
    </div>
  );
}
