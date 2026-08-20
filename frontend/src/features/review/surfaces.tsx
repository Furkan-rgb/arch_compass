import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, plural, shortId, splitQualified } from "../../lib/format";
import { Tag, VerdictBadge } from "../../ui/badge";
import { Button, ExternalButtonLink, ToggleButton } from "../../ui/button";
import { EvidenceBlock } from "../../ui/code";
import { Input } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { MetaList, MetaRow, Mono, Statistic } from "../../ui/meta";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";
import { orderedFindings } from "./attention-queue";

type DeltaState = "new" | "changed" | "addressed" | "unchanged";

const DELTA_STATES: ReadonlyArray<{
  id: DeltaState;
  label: string;
  glyph: string;
  tone: string;
  says: string;
}> = [
  { id: "new", label: "New", glyph: "+", tone: "text-accent", says: "Not in the previous review" },
  { id: "changed", label: "Changed", glyph: "~", tone: "text-held", says: "The same candidate, moved" },
  {
    id: "addressed",
    label: "Addressed",
    glyph: "✓",
    tone: "text-cleared",
    says: "Raised last time, gone now",
  },
  { id: "unchanged", label: "Unchanged", glyph: "=", tone: "text-ink-3", says: "As it was" },
];

type DeltaEntry = {
  state: DeltaState;
  candidateId: string;
  /** The name to scan for. Falls back to the summary, then to the bare id. */
  identity: string;
  summary: string | null;
  finding: Review["findings"][number] | null;
  causes: readonly string[];
  lastVerdict: string | null;
};

/**
 * One row of the delta.
 *
 * Led by the identifier rather than by the sentence: a returning reviewer is scanning for
 * *which* things moved, and a column of full sentences has to be read rather than scanned.
 * The name is the key — the same mono treatment the queue uses, so the two surfaces are
 * visibly about the same objects — and the sentence sits under it, at one line, for when
 * the name alone is not enough.
 */
function DeltaRow({ entry, onOpen }: { entry: DeltaEntry; onOpen?: () => void }) {
  const state = DELTA_STATES.find((item) => item.id === entry.state)!;
  const { namespace, leaf } = splitQualified(entry.identity);
  const body = (
    <div className="grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-3">
      <span
        aria-hidden="true"
        title={state.label}
        className={cn("mt-0.5 text-center font-mono text-sm font-bold leading-6", state.tone)}
      >
        {state.glyph}
      </span>
      <span className="min-w-0">
        <span className="sr-only">{state.label}: </span>
        {namespace ? (
          <span className="block truncate font-mono text-[10.5px] text-ink-3">{namespace}</span>
        ) : null}
        <span className="block truncate font-mono text-[13px] font-medium text-ink">{leaf}</span>
        {entry.summary ? (
          <span className="mt-0.5 block truncate text-xs leading-5 text-ink-2">
            {entry.summary}
          </span>
        ) : null}
        {entry.causes.length ? (
          <span className="mt-1.5 flex flex-wrap gap-1.5">
            {entry.causes.map((cause) => (
              <Tag key={cause}>{humanise(cause)}</Tag>
            ))}
          </span>
        ) : null}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {entry.finding ? (
          <VerdictBadge verdict={entry.finding.verdict} />
        ) : entry.lastVerdict ? (
          <Tag>last: {humanise(entry.lastVerdict)}</Tag>
        ) : null}
      </span>
    </div>
  );

  // An addressed candidate is not in this review, so there is nothing to open — it is shown
  // as a record, not as a destination.
  if (!onOpen) {
    return <li className="px-4 py-3 sm:px-5">{body}</li>;
  }
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        title={entry.identity}
        className="w-full px-4 py-3 text-left transition hover:bg-sunken sm:px-5"
      >
        {body}
      </button>
    </li>
  );
}

/**
 * What moved since the previous review.
 *
 * The review history is the point of keeping reviews immutable, and this is the surface a
 * reviewer opens on their second visit: everything they already dealt with is noise, and
 * what they want is the short list of what is different. So this is one list under one
 * filter rather than four stacked panels — the change state belongs to the row, not to the
 * container it happens to be in — ordered by how much it demands of a person.
 */
export function DeltaSurface({
  review,
  onOpen,
}: {
  review: Review;
  onOpen?: (candidateId: string) => void;
}) {
  const [state, setState] = useState<DeltaState | "all">("all");
  const findingOf = (candidateId: string) =>
    review.findings.find((item) => item.candidate.id === candidateId) ?? null;
  const nameOf = (candidateId: string) => {
    const finding = findingOf(candidateId);
    return (
      finding?.candidate.participants[0]?.qualified_name ??
      finding?.candidate.summary ??
      shortId(candidateId, 16)
    );
  };

  const entries: DeltaEntry[] = [
    ...review.delta.new.map((candidateId) => ({
      state: "new" as const,
      candidateId,
      identity: nameOf(candidateId),
      summary: findingOf(candidateId)?.candidate.summary ?? null,
      finding: findingOf(candidateId),
      causes: [],
      lastVerdict: null,
    })),
    ...review.delta.changed.map((change) => ({
      state: "changed" as const,
      candidateId: change.candidate_id,
      identity: nameOf(change.candidate_id),
      summary: findingOf(change.candidate_id)?.candidate.summary ?? null,
      finding: findingOf(change.candidate_id),
      causes: change.causes,
      lastVerdict: null,
    })),
    ...review.delta.addressed.map((item) => ({
      state: "addressed" as const,
      candidateId: item.candidate_id,
      identity: item.title,
      summary: null,
      finding: null,
      causes: [],
      lastVerdict: item.last_verdict,
    })),
    ...review.delta.unchanged.map((candidateId) => ({
      state: "unchanged" as const,
      candidateId,
      identity: nameOf(candidateId),
      summary: findingOf(candidateId)?.candidate.summary ?? null,
      finding: findingOf(candidateId),
      causes: [],
      lastVerdict: null,
    })),
  ];

  const counts = Object.fromEntries(
    DELTA_STATES.map((item) => [
      item.id,
      entries.filter((entry) => entry.state === item.id).length,
    ]),
  ) as Record<DeltaState, number>;
  const visible = state === "all" ? entries : entries.filter((entry) => entry.state === state);

  return (
    <div className="grid gap-4">
      <Panel>
        <PanelHeader
          title="Change since the previous review"
          description={
            review.previous_review_id
              ? `Compared against review ${shortId(review.previous_review_id, 8)} by candidate identity — not by what the model said either time.`
              : "This is the first review in this lineage, so everything is new."
          }
        />
        {/* The counts are the filter. Four numbers you can only read, next to a list you
            then have to scan by hand, is two controls' worth of screen doing one job. */}
        <PanelBody className="flex flex-wrap gap-1.5">
          <ToggleButton pressed={state === "all"} onClick={() => setState("all")}>
            All
            <span className="tabular-nums opacity-70">{entries.length}</span>
          </ToggleButton>
          {DELTA_STATES.map((item) => (
            <ToggleButton
              key={item.id}
              pressed={state === item.id}
              disabled={!counts[item.id]}
              onClick={() => setState(item.id)}
              title={item.says}
            >
              <span className={cn("font-mono font-bold", item.tone)} aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
              <span className="tabular-nums opacity-70">{counts[item.id]}</span>
            </ToggleButton>
          ))}
        </PanelBody>
      </Panel>

      {!visible.length ? (
        <EmptyState title="Nothing in this state">
          {review.previous_review_id
            ? "Choose another state to see the rest of the comparison."
            : "The first review in a lineage has nothing to be different from."}
        </EmptyState>
      ) : (
        <Panel>
          <ul aria-label="Candidates by change" className="divide-y divide-rule">
            {visible.map((entry) => (
              <DeltaRow
                key={`${entry.state}-${entry.candidateId}`}
                entry={entry}
                onOpen={entry.finding && onOpen ? () => onOpen(entry.candidateId) : undefined}
              />
            ))}
          </ul>
        </Panel>
      )}
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
  const explore = useMutation({ mutationFn: (terms: string[]) => api.searchAtlas(root, terms) });
  const summary = useQuery({
    queryKey: ["repository-summary", root],
    queryFn: () => api.repositorySummary(root),
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
/**
 * Every pinned excerpt, under the candidate it was pinned for.
 *
 * An excerpt only means something next to the claim it supports — a flat list of file
 * fragments makes the reader match line numbers against the queue by hand. The review
 * already carries the evidence on each finding, so this groups what is there rather than
 * re-fetching `/source`, which flattens the grouping away.
 *
 * Two kinds sit under each candidate and are labelled apart, because they were pinned by
 * different steps and carry different weight: what the analyser found to raise the
 * candidate at all, and what the judgement leant on to reach its verdict.
 */
export function EvidenceSurface({ review }: { review: Review }) {
  const findings = orderedFindings(review);
  const groups = findings.map((finding) => ({
    finding,
    judgement: finding.evidence,
    detection: finding.candidate.evidence,
  }));
  const withEvidence = groups.filter(
    (group) => group.judgement.length > 0 || group.detection.length > 0,
  );
  const excerpts = withEvidence.reduce(
    (total, group) => total + group.judgement.length + group.detection.length,
    0,
  );

  if (!withEvidence.length) {
    return <EmptyState title="No pinned evidence">This review pinned no source excerpts.</EmptyState>;
  }

  const silent = groups.length - withEvidence.length;

  return (
    <div className="grid gap-4">
      <Panel>
        <PanelHeader
          title="Evidence by candidate"
          description={`${plural(excerpts, "excerpt")} across ${plural(
            withEvidence.length,
            "candidate",
          )}.${silent ? ` ${plural(silent, "other candidate")} pinned none.` : ""}`}
        />
      </Panel>

      {withEvidence.map(({ finding, judgement, detection }) => {
        const identity = finding.candidate.participants[0]?.qualified_name;
        return (
          <Panel key={finding.candidate.id}>
            <PanelHeader
              title={finding.candidate.summary}
              description={
                identity ? (
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Mono className="text-[11px]">{identity}</Mono>
                    <Tag>{humanise(finding.candidate.pattern)}</Tag>
                  </span>
                ) : (
                  <Tag>{humanise(finding.candidate.pattern)}</Tag>
                )
              }
              actions={<VerdictBadge verdict={finding.verdict} />}
            />
            <PanelBody className="grid gap-4">
              {judgement.length ? (
                <div className="grid gap-2">
                  <Label>Pinned by the judgement</Label>
                  {judgement.map((item, index) => (
                    <EvidenceBlock
                      key={`judgement-${item.location?.path}-${index}`}
                      description={item.description}
                      path={item.location?.path}
                      startLine={item.location?.start_line}
                      endLine={item.location?.end_line}
                      excerpt={item.excerpt}
                    />
                  ))}
                </div>
              ) : null}
              {detection.length ? (
                <div className="grid gap-2">
                  <Label>Pinned by detection</Label>
                  {detection.map((item, index) => (
                    <EvidenceBlock
                      key={`detection-${item.location?.path}-${index}`}
                      description={item.description}
                      path={item.location?.path}
                      startLine={item.location?.start_line}
                      endLine={item.location?.end_line}
                      excerpt={item.excerpt}
                    />
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </Panel>
        );
      })}
    </div>
  );
}

export function ReportSurface({ review }: { review: Review }) {
  const report = useQuery({
    queryKey: ["review-report", review.id],
    queryFn: () => api.reviewReport(review.id),
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
    queryFn: () => api.conversations(review.id),
  });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    if (!conversationId && conversations.data?.[0]) setConversationId(conversations.data[0].id);
  }, [conversationId, conversations.data]);

  const ask = useMutation({
    mutationFn: async () => {
      const id = conversationId || (await api.createConversation(review.id)).id;
      setConversationId(id);
      return api.ask(id, question.trim());
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
