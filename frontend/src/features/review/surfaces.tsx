import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { coreApi, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, shortId } from "../../lib/format";
import { Tag, VerdictBadge } from "../../ui/badge";
import { Button, ExternalButtonLink } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { Input } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { MetaList, MetaRow, Mono, Statistic } from "../../ui/meta";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";

/** Every candidate compared against the preceding immutable review. */
export function DeltaSurface({ review }: { review: Review }) {
  return (
    <div className="grid gap-4">
      <Panel>
        <PanelHeader
          title="Change since the previous review"
          description={
            review.previous_review_id
              ? `Compared against review ${shortId(review.previous_review_id, 8)} by candidate identity.`
              : "This is the first review in this lineage, so everything is new."
          }
        />
        <PanelBody className="grid grid-cols-2 gap-5 sm:grid-cols-4">
          <Statistic label="New" value={review.delta.new.length} tone="accent" />
          <Statistic label="Changed" value={review.delta.changed.length} tone="held" />
          <Statistic label="Unchanged" value={review.delta.unchanged.length} />
          <Statistic label="Addressed" value={review.delta.addressed.length} tone="cleared" />
        </PanelBody>
      </Panel>

      {/* On the first review every candidate is new and the queue already lists them, so the
          list is only worth showing once there is a predecessor to be new against. */}
      {review.previous_review_id && review.delta.new.length ? (
        <Panel>
          <PanelHeader
            title="New candidates"
            description="Detected in this snapshot and absent from the previous one."
          />
          <PanelBody className="grid gap-2">
            {review.delta.new.map((candidateId) => {
              const finding = review.findings.find((item) => item.candidate.id === candidateId);
              return (
                <div
                  key={candidateId}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-rule bg-surface-2 px-3 py-2.5"
                >
                  <span className="min-w-0 text-sm text-ink">
                    {finding?.candidate.summary ?? shortId(candidateId, 16)}
                  </span>
                  {finding ? <VerdictBadge verdict={finding.verdict} /> : null}
                </div>
              );
            })}
          </PanelBody>
        </Panel>
      ) : null}

      {review.delta.changed.length ? (
        <Panel>
          <PanelHeader
            title="Changed candidates"
            description="What about the candidate moved, not what the model said about it."
          />
          <PanelBody className="grid gap-2">
            {review.delta.changed.map((change) => {
              const finding = review.findings.find(
                (item) => item.candidate.id === change.candidate_id,
              );
              return (
                <div
                  key={change.candidate_id}
                  className="rounded-md border border-rule bg-surface-2 px-3 py-2.5"
                >
                  <div className="text-sm font-semibold text-ink">
                    {finding?.candidate.summary ?? shortId(change.candidate_id, 16)}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {change.causes.map((cause) => (
                      <Tag key={cause}>{humanise(cause)}</Tag>
                    ))}
                  </div>
                  {change.predecessor_id ? (
                    <Mono className="mt-1.5 block text-[11px] text-ink-3">
                      was {shortId(change.predecessor_id, 16)}
                    </Mono>
                  ) : null}
                </div>
              );
            })}
          </PanelBody>
        </Panel>
      ) : null}

      {review.delta.addressed.length ? (
        <Panel>
          <PanelHeader
            title="Addressed since last time"
            description="Candidates the previous review raised that this one no longer detects."
          />
          <PanelBody className="grid gap-2">
            {review.delta.addressed.map((item) => (
              <div
                key={item.candidate_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-cleared/25 bg-cleared-soft/50 px-3 py-2.5"
              >
                <span className="text-sm text-ink">{item.title}</span>
                <Tag>last verdict: {humanise(item.last_verdict)}</Tag>
              </div>
            ))}
          </PanelBody>
        </Panel>
      ) : null}
    </div>
  );
}

/** The repository atlas, explored as structure rather than drawn as a graph. */
export function AtlasSurface({ review }: { review: Review }) {
  const root = review.repository.path;
  const seedTerms = review.findings
    .flatMap((finding) => finding.candidate.participants.map((item) => item.qualified_name))
    .slice(0, 5);
  const [query, setQuery] = useState(seedTerms.join(" "));
  const explore = useMutation({ mutationFn: (terms: string[]) => coreApi.searchAtlas(root, terms) });
  const summary = useQuery({
    queryKey: ["repository-summary", root],
    queryFn: () => coreApi.repositorySummary(root),
  });

  const { mutate } = explore;
  useEffect(() => {
    const terms = seedTerms.filter(Boolean);
    if (terms.length) mutate(terms);
    // Seeded once from the review's own participants; every search after that is the reader's.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, mutate]);

  function search() {
    const terms = query.split(/\s+/).map((item) => item.trim()).filter(Boolean).slice(0, 10);
    if (terms.length) mutate(terms);
  }

  return (
    <div className="grid gap-4">
      <Panel>
        <PanelHeader
          title="Repository atlas"
          description="The deterministic structure this review was judged against."
        />
        <PanelBody>
          {summary.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-ink-3">
              <Spinner /> Reading the atlas…
            </div>
          ) : summary.error ? (
            <ErrorNotice error={summary.error} />
          ) : (
            <>
              <p className="max-w-3xl text-sm leading-7 text-ink-2">{summary.data?.summary}</p>
              <div className="mt-5 grid grid-cols-2 gap-5 border-t border-rule pt-4 sm:grid-cols-4">
                <Statistic label="Nodes" value={review.atlas.node_count.toLocaleString()} />
                <Statistic label="Edges" value={review.atlas.edge_count.toLocaleString()} />
                <Statistic label="Metrics" value={review.atlas.metric_count.toLocaleString()} />
                <Statistic label="Signals" value={review.atlas.signal_count.toLocaleString()} />
              </div>
            </>
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Search the atlas"
          description="Modules, classes and functions the analysis recorded, with their relationships."
          actions={
            <div className="flex w-full gap-2 sm:w-auto">
              <Input
                aria-label="Search the atlas"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") search();
                }}
                className="sm:w-72"
                placeholder="module, class, function"
              />
              <Button onClick={search} disabled={!query.trim() || explore.isPending}>
                Search
              </Button>
            </div>
          }
        />
        <PanelBody>
          {explore.error ? <ErrorNotice error={explore.error} /> : null}
          {explore.isPending ? (
            <div className="flex items-center gap-2 text-sm text-ink-3">
              <Spinner /> Querying the atlas…
            </div>
          ) : !explore.data ? (
            <EmptyState title="Nothing searched yet">
              Search for a module or symbol to see where it sits in the structure.
            </EmptyState>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-5 border-b border-rule pb-4">
                <Statistic label="Matched" value={explore.data.node_summaries?.length ?? 0} />
                <Statistic label="Relations" value={explore.data.relationships?.length ?? 0} />
                <Statistic label="Signals" value={explore.data.signals?.length ?? 0} />
              </div>
              <ul className="mt-4 grid gap-1.5 md:grid-cols-2">
                {explore.data.node_summaries?.map((node) => (
                  <li
                    key={node.node_id}
                    className="rounded-md border border-rule bg-surface-2 px-3 py-2.5"
                  >
                    <Mono className="block truncate text-[13px] text-ink">
                      {node.qualified_name}
                    </Mono>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <Tag>{humanise(node.node_type)}</Tag>
                      <span className="truncate font-mono text-[11px] text-ink-3">{node.path}</span>
                    </div>
                  </li>
                ))}
              </ul>
              {explore.data.signals?.length ? (
                <div className="mt-4 border-t border-rule pt-4">
                  <Label>Architectural signals</Label>
                  <ul className="mt-2 grid gap-1.5">
                    {explore.data.signals.slice(0, 20).map((signal, index) => (
                      <li
                        key={`${signal.code}-${index}`}
                        className="rounded-md border border-rule bg-surface-2 px-3 py-2 text-xs leading-5 text-ink-2"
                      >
                        <Mono className="mr-2 text-[11px] text-ink-3">{signal.code}</Mono>
                        {signal.message}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}

/** Every excerpt pinned by this review, in one place, for reading the code itself. */
export function EvidenceSurface({ review }: { review: Review }) {
  const evidence = useQuery({
    queryKey: ["review-source", review.id],
    queryFn: () => coreApi.reviewSource(review.id),
  });
  if (evidence.isLoading) return <LoadingPanel label="Loading pinned evidence…" />;
  if (evidence.error) return <ErrorNotice error={evidence.error} />;
  if (!evidence.data?.length)
    return <EmptyState title="No pinned evidence">This review pinned no source excerpts.</EmptyState>;
  return (
    <div className="grid gap-2">
      {evidence.data.map((item, index) => (
        <EvidenceBlock
          key={`${item.location?.path}-${index}`}
          description={item.description}
          path={item.location?.path}
          startLine={item.location?.start_line}
          endLine={item.location?.end_line}
          excerpt={item.excerpt}
        />
      ))}
    </div>
  );
}

export function ReportSurface({ review }: { review: Review }) {
  const report = useQuery({
    queryKey: ["review-report", review.id],
    queryFn: () => coreApi.reviewReport(review.id),
    enabled: review.status === "completed",
  });
  if (review.status !== "completed") {
    return (
      <EmptyState title="The report is written when the review completes">
        A review that is waiting on clarification has no final text yet.
      </EmptyState>
    );
  }
  if (report.isLoading) return <LoadingPanel label="Rendering the report…" />;
  if (report.error) return <ErrorNotice error={report.error} />;
  return (
    <Panel>
      <PanelHeader
        title="Review report"
        description="The same Markdown the API serves, rendered."
        actions={
          <ExternalButtonLink
            size="sm"
            href={`/api/reviews/${encodeURIComponent(review.id)}/report`}
            download={`archcompass-${review.id}.md`}
          >
            Download Markdown
          </ExternalButtonLink>
        }
      />
      <PanelBody>
        <Markdown>{report.data ?? ""}</Markdown>
      </PanelBody>
    </Panel>
  );
}

/**
 * A grounded follow-up.
 *
 * Deliberately not the front door: it is one surface among several, and every answer is
 * anchored to the immutable review rather than to a conversation with a model.
 */
export function AskSurface({ review }: { review: Review }) {
  const client = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations", review.id],
    queryFn: () => coreApi.conversations(review.id),
  });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    if (!conversationId && conversations.data?.[0]) setConversationId(conversations.data[0].id);
  }, [conversationId, conversations.data]);

  const ask = useMutation({
    mutationFn: async () => {
      const id = conversationId || (await coreApi.createConversation(review.id)).id;
      setConversationId(id);
      return coreApi.ask(id, question.trim());
    },
    onSuccess: async () => {
      setQuestion("");
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  const current =
    ask.data || conversations.data?.find((item) => item.id === conversationId) || conversations.data?.[0];

  return (
    <Panel>
      <PanelHeader
        title="Ask about this review"
        description="Answers are grounded in this review's findings, case, policies and pinned evidence — nothing else."
      />
      <PanelBody>
        {current?.messages.length ? (
          <ol className="grid gap-4">
            {current.messages.map((message, index) => (
              <li key={`${message.asked_at}-${index}`} className="grid gap-2">
                <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
                  <Label>Question</Label>
                  <p className="mt-1 text-sm leading-6 text-ink">{message.question}</p>
                </div>
                <div className="rounded-md border border-accent/20 bg-accent-soft/40 px-3 py-2.5">
                  <Label className="text-accent">Grounded answer</Label>
                  <p className="mt-1 whitespace-pre-line text-sm leading-6 text-ink-2">
                    {message.answer.text}
                  </p>
                  {message.answer.supporting_candidate_ids.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-rule pt-2">
                      {message.answer.supporting_candidate_ids.map((id) => {
                        const finding = review.findings.find((item) => item.candidate.id === id);
                        return <Tag key={id}>{finding?.candidate.summary ?? shortId(id, 12)}</Tag>;
                      })}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState title="No questions asked yet">
            Ask something the review already contains the answer to — scope, provenance, or why a
            candidate was cleared.
          </EmptyState>
        )}

        <div className={cn("mt-4 flex gap-2 border-t border-rule pt-4")}>
          <Input
            aria-label="Question about this review"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && question.trim() && !ask.isPending) ask.mutate();
            }}
            className="min-w-0 flex-1"
            placeholder="Why was the gateway candidate cleared?"
          />
          <Button disabled={!question.trim() || ask.isPending} onClick={() => ask.mutate()}>
            {ask.isPending ? <Spinner /> : "Ask"}
          </Button>
        </div>
        {ask.error ? (
          <div className="mt-3">
            <ErrorNotice error={ask.error} />
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

/** Provenance for every candidate at once — the audit view, not the reading view. */
export function ProvenanceSurface({ review }: { review: Review }) {
  if (!review.retrieval_manifest.length) {
    return (
      <EmptyState title="No retrieval recorded">
        This review judged no candidate, so no policy retrieval was performed.
      </EmptyState>
    );
  }
  return (
    <div className="grid gap-3">
      {review.retrieval_manifest.map((item) => {
        const finding = review.findings.find((entry) => entry.candidate.id === item.candidate_id);
        return (
          <Panel key={item.candidate_id}>
            <PanelHeader
              title={finding?.candidate.summary ?? shortId(item.candidate_id, 16)}
              description={
                <>
                  <Mono>{item.retriever}</Mono> · v{item.version}
                </>
              }
              actions={<Tag>{item.selected_policy_ids.length} selected</Tag>}
            />
            <PanelBody>
              <MetaList>
                <MetaRow label="Embedding">
                  <Mono>{item.model_identity || "non-embedding strategy"}</Mono>
                </MetaRow>
                <MetaRow label="Corpus">
                  <Mono className="break-all">{item.corpus_fingerprint}</Mono>
                </MetaRow>
                {item.query_fingerprint ? (
                  <MetaRow label="Query">
                    <Mono className="break-all">{item.query_fingerprint}</Mono>
                  </MetaRow>
                ) : null}
                <MetaRow label="Policies">
                  <span className="flex flex-wrap gap-1">
                    {item.selected_policy_ids.map((id) => (
                      <Tag key={id}>
                        <Mono className="text-[11px]">{id}</Mono>
                      </Tag>
                    ))}
                  </span>
                </MetaRow>
                {Object.entries(item.metadata).map(([key, value]) => (
                  <MetaRow key={key} label={humanise(key)}>
                    <Mono>{value}</Mono>
                  </MetaRow>
                ))}
              </MetaList>
            </PanelBody>
          </Panel>
        );
      })}
    </div>
  );
}
