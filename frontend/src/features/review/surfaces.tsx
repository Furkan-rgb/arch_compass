import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, shortId, splitQualified } from "../../lib/format";
import { Tag, VerdictBadge } from "../../ui/badge";
import { Button, ExternalButtonLink, ToggleButton } from "../../ui/button";
import { Input } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";


type DeltaState = "new" | "changed" | "addressed" | "unchanged";

const DELTA_STATES: ReadonlyArray<{
  id: DeltaState;
  label: string;
  glyph: string;
  tone: string;
  says: string;
}> = [
  { id: "new", label: "New", glyph: "+", tone: "text-ink", says: "Not in the previous review" },
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

/**
 * The review as one document.
 *
 * Not gated on the review being finished any more. The report is composed for a waiting
 * review too and opens on a line saying it is not final, which is the same thing the empty
 * state used to say and a great deal more use — a reviewer part-way through a clarification
 * round can still hand somebody what has been judged so far.
 *
 * The description used to read "The same Markdown the API serves, rendered", which tells a
 * reviewer about the API rather than about their review.
 */
export function ReportSurface({ review }: { review: Review }) {
  const report = useQuery({
    queryKey: ["review-report", review.id],
    queryFn: () => api.reviewReport(review.id),
  });
  if (report.isLoading) return <LoadingPanel label="Rendering the report…" />;
  if (report.error) return <ErrorNotice error={report.error} />;
  return (
    <Panel>
      <PanelHeader
        title="Review report"
        description="The whole review as one document — what was found, what moved since last time, and the context it was judged against. Written to be read away from here."
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

/** What a conversation is called: the question that opened it. */
function conversationTitle(conversation: ReviewConversation, index: number): string {
  const first = conversation.messages[0]?.question.trim();
  if (!first) return `New question ${index + 1}`;
  return first.length > 44 ? `${first.slice(0, 44)}…` : first;
}

/**
 * Ask about this review.
 *
 * Deliberately not the front door: it is one surface among several, and every fact in an
 * answer is anchored to the immutable review rather than to a conversation with a model.
 * What follows from those facts — how a finding would be fixed, which to take first — is
 * fair to ask here, because it is why anybody read the review in the first place.
 *
 * A reader has more than one line of questioning — "why was this cleared" and "what does
 * this policy cover" are different threads, and reading them interleaved is worse than
 * reading either. So conversations are separate and switched between, named by the question
 * that opened them because nobody titles their own notes.
 *
 * They are working notes over an immutable review, not part of the record: the review, its
 * findings and the standing decisions are untouched by throwing one away.
 */
export function AskSurface({
  review,
  onOpen,
}: {
  review: Review;
  onOpen?: (candidateId: string) => void;
}) {
  const client = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations", review.id],
    queryFn: () => api.conversations(review.id),
  });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);

  const threads = conversations.data ?? [];
  // A thread with nothing in it is the one being started; there is never a reason to have
  // two, so the button that starts one steps aside once an empty one exists.
  const empty = threads.find((item) => !item.messages.length);
  const current =
    threads.find((item) => item.id === conversationId) ?? threads[threads.length - 1] ?? null;

  useEffect(() => {
    if (conversationId && !threads.some((item) => item.id === conversationId)) {
      setConversationId(null);
    }
  }, [conversationId, threads]);

  const ask = useMutation({
    mutationFn: async () => {
      const id = current?.id || (await api.createConversation(review.id)).id;
      setConversationId(id);
      return api.ask(id, question.trim());
    },
    onSuccess: async () => {
      setQuestion("");
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  const open = useMutation({
    mutationFn: () => api.createConversation(review.id),
    onSuccess: async (created) => {
      setConversationId(created.id);
      setQuestion("");
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  const discard = useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: async () => {
      setConfirming(null);
      setConversationId(null);
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  return (
    <Panel>
      <PanelHeader
        title="Ask about this review"
        description="Every fact in an answer comes from this review — its findings, case, policies and evidence. What to do about one is reasoned from those, and says so."
        actions={
          <Button
            variant="secondary"
            size="sm"
            disabled={open.isPending || Boolean(empty)}
            title={empty ? "There is already an empty conversation to ask in." : undefined}
            onClick={() => (empty ? setConversationId(empty.id) : open.mutate())}
          >
            {open.isPending ? <Spinner /> : "New conversation"}
          </Button>
        }
      />

      {threads.length > 1 ? (
        <div
          role="tablist"
          aria-label="Conversations"
          className="flex flex-wrap gap-1.5 border-b border-rule px-4 py-2.5 sm:px-5"
        >
          {threads.map((thread, index) => (
            <ToggleButton
              key={thread.id}
              role="tab"
              pressed={current?.id === thread.id}
              onClick={() => setConversationId(thread.id)}
              className="max-w-[18rem]"
            >
              <span className="truncate">{conversationTitle(thread, index)}</span>
              <span className="tabular-nums opacity-70">{thread.messages.length}</span>
            </ToggleButton>
          ))}
        </div>
      ) : null}

      <PanelBody>
        {current?.messages.length ? (
          <ol className="grid gap-4">
            {current.messages.map((message, index) => (
              <li key={`${message.asked_at}-${index}`} className="grid gap-2">
                <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
                  <Label>Question</Label>
                  <p className="mt-1 text-sm leading-6 text-ink">{message.question}</p>
                </div>
                <div className="rounded-md border border-rule bg-sunken/50 px-3 py-2.5">
                  <Label>Grounded answer</Label>
                  <p className="mt-1 whitespace-pre-line text-sm leading-6 text-ink-2">
                    {message.answer.text}
                  </p>
                  {message.answer.supporting_candidate_ids.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-rule pt-2">
                      {message.answer.supporting_candidate_ids.map((id) => {
                        const finding = review.findings.find((item) => item.candidate.id === id);
                        const label = finding?.candidate.summary ?? shortId(id, 12);
                        // An answer is told where the evidence sits but never shown the code
                        // there, so a citation is the way to it rather than a footnote.
                        return finding && onOpen ? (
                          <button key={id} type="button" onClick={() => onOpen(id)}>
                            <Tag className="transition hover:border-rule-strong hover:text-ink">
                              {label}
                            </Tag>
                          </button>
                        ) : (
                          <Tag key={id}>{label}</Tag>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState title="No questions asked yet">
            Ask what the review found — why a candidate was cleared, what a policy covers — or what
            to do about it: how a finding would be fixed, and which one to take first.
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
            placeholder="How would the gateway finding be fixed?"
          />
          <Button disabled={!question.trim() || ask.isPending} onClick={() => ask.mutate()}>
            {ask.isPending ? <Spinner /> : "Ask"}
          </Button>
        </div>

        {/* Deleting is asked about rather than undone, because there is nowhere to undo it
            to — the conversation is not part of the immutable record. */}
        {current ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {confirming === current.id ? (
              <>
                <span className="text-xs text-ink-3">
                  Discard this conversation? Its questions and answers go with it.
                </span>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={discard.isPending}
                  onClick={() => discard.mutate(current.id)}
                >
                  {discard.isPending ? <Spinner /> : "Discard"}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>
                  Keep
                </Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setConfirming(current.id)}>
                Discard this conversation
              </Button>
            )}
          </div>
        ) : null}

        {ask.error ? (
          <div className="mt-3">
            <ErrorNotice error={ask.error} />
          </div>
        ) : null}
        {discard.error ? (
          <div className="mt-3">
            <ErrorNotice error={discard.error} />
          </div>
        ) : null}
        {open.error ? (
          <div className="mt-3">
            <ErrorNotice error={open.error} />
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
