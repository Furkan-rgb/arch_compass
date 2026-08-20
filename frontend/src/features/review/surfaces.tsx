import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { cn } from "../../lib/cn";
import { humanise, shortId, splitQualified } from "../../lib/format";
import { Tag, VerdictBadge } from "../../ui/badge";
import { Button, ExternalButtonLink, ToggleButton } from "../../ui/button";
import { Input } from "../../ui/field";
import { Markdown } from "../../ui/markdown";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";


type DeltaState = "addressed" | "changed" | "new" | "unchanged";

/**
 * The four states, in the order a reader who came back for the change wants them.
 *
 * `addressed` leads because it is the only one of the four that exists nowhere else in the
 * product: the candidate is gone, so there is no finding to open and no queue row to meet it
 * in. If this list does not say it, nothing does. `changed` and `new` follow — both are also
 * hoisted to the top of the queue — and `unchanged` is last, because it is exactly what a
 * returning reader opened this surface to skip.
 *
 * Only one of the four carries a hue, and it is the one the palette rule allows. `changed`
 * used to be amber, which is the bug that rule exists for: `held` is a verdict the model
 * reached, not "this row moved", and a changed candidate can come back material, held or
 * cleared. `addressed` keeps `cleared` because an addressed candidate really is settled —
 * the concern that was raised is gone.
 */
const DELTA_STATES: ReadonlyArray<{
  id: DeltaState;
  label: string;
  glyph: string;
  tone: string;
  says: string;
}> = [
  {
    id: "addressed",
    label: "Addressed",
    glyph: "✓",
    tone: "text-cleared",
    says: "Raised last time, gone now",
  },
  {
    id: "changed",
    label: "Changed",
    glyph: "~",
    tone: "text-ink",
    says: "The same candidate, judged again",
  },
  { id: "new", label: "New", glyph: "+", tone: "text-ink", says: "Not in the previous review" },
  { id: "unchanged", label: "Unchanged", glyph: "=", tone: "text-ink-3", says: "As it was" },
];

/**
 * Why a candidate is in the delta, said from the reader's side.
 *
 * `content`, `shape`, `case`, `policies`, `model`, `prompt` and `resurfaced` are the
 * `ChangeCause` enum — schema values the analyser, the wire and the report all use, and
 * should keep using. A person reading a row is not being shown a field, they are being told
 * why last time's verdict could not simply be carried forward, so the row says it in words.
 * The raw cause still travels on the wire, and still appears in the Markdown report, which
 * is where machine names belong.
 */
const CHANGE_REASONS: Record<string, string> = {
  content: "the evidence behind it changed",
  shape: "the shape of the candidate changed",
  case: "the architecture case it is judged against changed",
  policies: "the policy corpus changed",
  model: "a different model judged it",
  prompt: "the judging prompt changed",
  resurfaced: "it was absent last review and has come back",
};

/** `["a", "b", "c"]` → `"a, b and c"`. A row and a footer both read as a sentence. */
function saidInOrder(parts: readonly string[]): string {
  if (parts.length <= 1) return parts[0] ?? "";
  return `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
}

/** `content` + `policies` → "the evidence behind it changed and the policy corpus changed". */
function whyChanged(causes: readonly string[]): string {
  // An unrecognised cause is one the backend added and this table has not caught up with.
  // Spacing it out and showing it is worse than a sentence and better than dropping it: a
  // reader can still see that something moved, and which something.
  const said = causes.map((cause) => CHANGE_REASONS[cause] ?? humanise(cause).toLowerCase());
  return said.length ? saidInOrder(said) : "something it was judged against moved";
}

type DeltaEntry = {
  state: DeltaState;
  candidateId: string;
  /** The name to scan for. Falls back to the summary, then to the bare id. */
  identity: string;
  /**
   * Whether `identity` is a string the machine produced — a qualified name or an id — rather
   * than a sentence. An addressed candidate is carried through the delta by its summary,
   * and a sentence set in mono and split on its last full stop reads as an identifier that
   * has gone wrong.
   */
  identityIsName: boolean;
  summary: string | null;
  finding: Review["findings"][number] | null;
  /** What moved, in one clause. Rendered after the state's own word. */
  reason: string;
  /** The verdict this candidate carried last time, when that is known and it has moved. */
  wasVerdict: string | null;
  /** The verdict it carries now. Null for an addressed candidate: there is no finding. */
  nowVerdict: string | null;
};

/**
 * One row of the delta.
 *
 * Led by the identifier rather than by the sentence: a returning reviewer is scanning for
 * *which* things moved, and a column of full sentences has to be read rather than scanned.
 * The name is the key — the same mono treatment the queue uses, so the two surfaces are
 * visibly about the same objects — and the sentence sits under it, at two lines, for when
 * the name alone is not enough.
 *
 * Under both of those is the line this surface exists for: what moved, and why. The state
 * used to be carried by a glyph, a colour and a screen-reader-only word, which is the
 * charter's rule inverted — a hue is the last of the three, never the first — so the word is
 * on the row now, and beside it the verdict it moved between. The row is one column of
 * content rather than a name on the left and a badge pinned right, because a verdict
 * transition is two badges and an arrow, and a 390px phone has no fixed column to spare for
 * it: pinned right it either squashed the name or pushed the list wider than the page.
 */
function DeltaRow({
  entry,
  hoisted,
  onOpen,
}: {
  entry: DeltaEntry;
  /** What the header above already said, and this row therefore does not repeat. */
  hoisted: { movement: boolean; verdict: boolean };
  onOpen?: () => void;
}) {
  const state = DELTA_STATES.find((item) => item.id === entry.state)!;
  const { namespace, leaf } = entry.identityIsName
    ? splitQualified(entry.identity)
    : { namespace: "", leaf: entry.identity };
  const body = (
    <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-3">
      <span
        aria-hidden="true"
        className={cn("mt-0.5 text-center font-mono text-sm font-bold leading-6", state.tone)}
      >
        {state.glyph}
      </span>
      <span className="min-w-0">
        {namespace ? (
          <span className="block truncate font-mono text-[10.5px] text-ink-3">{namespace}</span>
        ) : null}
        {/* The namespace above may be cut — it is context. The name is the identity and the
            sentence is the reason, so both get two lines and break mid-token rather than
            ending in an ellipsis. On a phone one truncated line of either said nothing but
            `src.audiobook.preparation.provid…`, which the namespace had already said. Same
            rule as the queue, which is the list this one is read against. */}
        <span
          className={cn(
            "line-clamp-2 text-[13px] font-medium leading-[1.35] text-ink wrap-anywhere",
            entry.identityIsName && "font-mono",
          )}
        >
          {leaf}
        </span>
        {entry.summary ? (
          <span className="mt-0.5 line-clamp-2 text-xs leading-5 text-ink-2 wrap-anywhere">
            {entry.summary}
          </span>
        ) : null}
        {/* Wrapping, not truncating: on a phone the transition takes the first line and the
            sentence the next two, and neither of them is allowed to set the row's width. */}
        {/* Nothing to say when the group header said all of it — and on the first review of
            a lineage it says all of it for every row, which is how six identical HELD pills
            over six copies of one sentence got onto one phone screen. Same rule as the
            queue: a fact shared by every row belongs on the group. */}
        {hoisted.movement && hoisted.verdict ? null : (
        <span className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          {/* The arrow is the whole sentence for the eye and says nothing at all to a screen
              reader, so the two words it stands for are spelled out beside it. */}
          {entry.wasVerdict && !hoisted.verdict ? (
            <>
              <span className="sr-only">was </span>
              <VerdictBadge verdict={entry.wasVerdict} className="px-2 py-0.5 text-[10px]" />
              <span aria-hidden="true" className="text-[11px] leading-none text-ink-3">
                →
              </span>
              <span className="sr-only">, now </span>
            </>
          ) : null}
          {entry.nowVerdict && !hoisted.verdict ? (
            <VerdictBadge verdict={entry.nowVerdict} className="px-2 py-0.5 text-[10px]" />
          ) : !hoisted.verdict && entry.state === "addressed" ? (
            <Tag className="text-[10px] font-bold uppercase tracking-[0.08em]">
              No longer detected
            </Tag>
          ) : null}
          {hoisted.movement ? null : (
            <span className="text-[11px] leading-5 text-ink-3">
              <span className="font-semibold text-ink-2">{state.label}</span> · {entry.reason}
            </span>
          )}
        </span>
        )}
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
        // The ring is drawn `outline-offset: 2px`, which on a full-bleed row in a divided
        // list lands on the neighbouring row's rule. Pulled inside, it frames the row it is
        // actually on. `min-h-11` is the target floor: a row with a short name and no
        // sentence is otherwise about 40px on a phone.
        className="flex min-h-11 w-full flex-col justify-center px-4 py-3 text-left transition hover:bg-sunken focus-visible:-outline-offset-2 sm:px-5"
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
 * container it happens to be in — and it is ordered so that what moved is read first.
 *
 * What a row says is the change, not the finding: the state in a word, the clause that says
 * what moved, and the verdict it moved between. The summary is still there, under the name,
 * but a reader who wanted the summary already read it last review — that is the whole
 * premise of the surface.
 */
export function DeltaSurface({
  review,
  onOpen,
}: {
  review: Review;
  onOpen?: (candidateId: string) => void;
}) {
  const [state, setState] = useState<DeltaState | "all">("all");
  /**
   * The lineage, for the one thing the delta cannot say on its own.
   *
   * `ReviewDelta` records the last verdict only for a candidate that has gone away; for one
   * that changed it records the causes and nothing about what the model used to say. So the
   * before half of "was held, now material" has to come from the previous review itself.
   * This is the query the revision rail already runs, under the same key, so it is served
   * from the cache rather than fetched again — and if the previous review is not in the
   * lineage the list returned, no transition is claimed. Saying nothing is the honest
   * failure here; guessing at a verdict is not.
   */
  const lineage = useQuery({
    queryKey: ["reviews"],
    queryFn: api.reviews,
    enabled: Boolean(review.previous_review_id),
  });
  const previous =
    lineage.data?.find((item) => item.id === review.previous_review_id) ?? null;

  const findingOf = (candidateId: string) =>
    review.findings.find((item) => item.candidate.id === candidateId) ?? null;
  /**
   * What to lead the row with, and whether it is a machine string or a sentence.
   *
   * A qualified name is what a reviewer scans for, so it leads and it is set in mono. When
   * a candidate has none, the summary stands in — but it is prose, and prose set in mono at
   * a name's weight reads as an identifier that has gone wrong. The bare id is the last
   * resort and is a machine string again.
   */
  const identityOf = (candidateId: string): Pick<DeltaEntry, "identity" | "identityIsName"> => {
    const finding = findingOf(candidateId);
    const qualified = finding?.candidate.participants[0]?.qualified_name;
    if (qualified) return { identity: qualified, identityIsName: true };
    if (finding?.candidate.summary)
      return { identity: finding.candidate.summary, identityIsName: false };
    return { identity: shortId(candidateId, 16), identityIsName: true };
  };
  const verdictLastTime = (candidateId: string) =>
    previous?.findings.find((item) => item.candidate.id === candidateId)?.verdict ?? null;
  // The number a person calls the review before this one. Reviews are sequenced per branch
  // and case, so the one this delta was taken against is the one below it — the same
  // arithmetic the queue's "Moved since review 1" heading does.
  const lastReview = review.sequence - 1;

  const entries: DeltaEntry[] = [
    ...review.delta.addressed.map((item) => ({
      state: "addressed" as const,
      candidateId: item.candidate_id,
      // `AddressedCandidate.title` is the candidate's summary: the candidate itself is gone,
      // so its name went with it and the sentence is all that survived into this review.
      identity: item.title,
      identityIsName: false,
      summary: null,
      finding: null,
      reason: `raised in review ${lastReview}, and not detected in this one`,
      wasVerdict: item.last_verdict,
      nowVerdict: null,
    })),
    ...review.delta.changed.map((change) => {
      const finding = findingOf(change.candidate_id);
      const was = verdictLastTime(change.candidate_id);
      return {
        state: "changed" as const,
        candidateId: change.candidate_id,
        ...identityOf(change.candidate_id),
        summary: finding?.candidate.summary ?? null,
        finding,
        reason: whyChanged(change.causes),
        // Only when it actually moved. "Held → held" is a transition a reader has to read
        // twice to find out that nothing happened.
        wasVerdict: was && was !== finding?.verdict ? was : null,
        nowVerdict: finding?.verdict ?? null,
      };
    }),
    ...review.delta.new.map((candidateId) => ({
      state: "new" as const,
      candidateId,
      ...identityOf(candidateId),
      summary: findingOf(candidateId)?.candidate.summary ?? null,
      finding: findingOf(candidateId),
      reason: review.previous_review_id
        ? `not detected in review ${lastReview}`
        : "this is the first review of this lineage",
      // A new candidate has no last time to have moved from, so there is nothing to look up
      // in the previous review and nothing to claim if something is found there.
      wasVerdict: null,
      nowVerdict: findingOf(candidateId)?.verdict ?? null,
    })),
    ...review.delta.unchanged.map((candidateId) => ({
      state: "unchanged" as const,
      candidateId,
      ...identityOf(candidateId),
      summary: findingOf(candidateId)?.candidate.summary ?? null,
      finding: findingOf(candidateId),
      // Short on purpose. This clause is on every carried-forward row, and the thirtieth
      // repetition of a definition is noise; what the row is actually telling a reader is
      // where it came from, which is a fact about this row rather than about the state.
      reason: `carried forward from review ${lastReview}`,
      wasVerdict: null,
      nowVerdict: findingOf(candidateId)?.verdict ?? null,
    })),
  ];

  const counts = Object.fromEntries(
    DELTA_STATES.map((item) => [
      item.id,
      entries.filter((entry) => entry.state === item.id).length,
    ]),
  ) as Record<DeltaState, number>;
  const visible = state === "all" ? entries : entries.filter((entry) => entry.state === state);
  const elsewhere =
    state === "all"
      ? []
      : DELTA_STATES.filter((item) => item.id !== state && counts[item.id] > 0).map(
          (item) => `${counts[item.id]} ${item.label.toLowerCase()}`,
        );
  /**
   * What every visible row agrees about, said once above them instead of once each.
   *
   * The same rule the queue follows, and for the same reason: on the first review of a
   * lineage every candidate is new, for the same reason, carrying the same verdict — so six
   * rows carried six identical badges under six identical sentences, restating a fact the
   * panel description had already given. A group of one hoists nothing, because there is no
   * repetition to remove and the row would lose facts to a header saying the same thing.
   */
  const agreesOn = <T,>(read: (entry: DeltaEntry) => T): T | null => {
    if (visible.length < 2) return null;
    const first = read(visible[0]);
    return visible.every((entry) => read(entry) === first) ? first : null;
  };
  const sharedMovement = agreesOn((entry) => `${entry.state}\u0000${entry.reason}`);
  const sharedVerdict = visible.some((entry) => entry.wasVerdict)
    ? null
    : agreesOn((entry) => entry.nowVerdict);
  const hoisted = { movement: Boolean(sharedMovement), verdict: Boolean(sharedVerdict) };

  const moved = counts.addressed + counts.changed + counts.new;
  // The reader came for the change. When there is none, the answer is a sentence — not four
  // zeroes on four chips for them to add up themselves.
  const nothingMoved = Boolean(review.previous_review_id) && !moved && entries.length > 0;

  return (
    <div className="grid gap-4">
      <Panel>
        <PanelHeader
          title="What moved since the previous review"
          description={
            review.previous_review_id ? (
              <>
                {nothingMoved
                  ? `Nothing moved: every candidate is the one that was there before, in the state it was in. `
                  : null}
                Compared against review {lastReview} (
                {/* The sequence is what a person calls a review; the id is what the record is
                    filed under, and it stays in mono because that is what it is. */}
                <span className="font-mono">{shortId(review.previous_review_id, 8)}</span>) by
                candidate identity — not by what the model said either time.
              </>
            ) : (
              "This is the first review in this lineage, so every candidate below is new and there is nothing yet to compare it against."
            )
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
        // Reachable in one way only: the review detected nothing at all. A count of zero
        // disables its own chip, so there is no way to filter yourself into an empty list.
        <EmptyState title="No candidates in this review">
          {review.previous_review_id
            ? `Nothing was detected this time, so there is nothing to compare against review ${lastReview}.`
            : "The first review in a lineage has nothing to be different from, and this one found nothing to list."}
        </EmptyState>
      ) : (
        <Panel>
          {hoisted.movement || hoisted.verdict ? (
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 border-b border-rule px-4 py-2.5 sm:px-5">
              <span className="text-[11px] font-semibold text-ink-2">
                All {visible.length}
              </span>
              {sharedVerdict ? (
                <VerdictBadge verdict={sharedVerdict} className="px-2 py-0.5 text-[10px]" />
              ) : null}
              {sharedMovement ? (
                <span className="text-[11px] leading-5 text-ink-3">
                  <span className="font-semibold text-ink-2">
                    {DELTA_STATES.find((item) => item.id === visible[0].state)!.label}
                  </span>{" "}
                  · {visible[0].reason}
                </span>
              ) : null}
            </div>
          ) : null}
          <ul aria-label="Candidates by change" className="divide-y divide-rule">
            {visible.map((entry) => (
              <DeltaRow
                key={`${entry.state}-${entry.candidateId}`}
                entry={entry}
                hoisted={hoisted}
                onOpen={entry.finding && onOpen ? () => onOpen(entry.candidateId) : undefined}
              />
            ))}
          </ul>
          {/* A filter hides rows, and a hidden row that nothing accounts for is the same
              gamble as a collapsed section with a bare caret on it. So the end of a filtered
              list says what it is not showing, by count and by name. Unfiltered there is
              nothing to declare and the footer does not exist. */}
          {elsewhere.length ? (
            <PanelFooter className="text-xs leading-5 text-ink-3">
              Showing {visible.length} of {entries.length}. Also in this review:{" "}
              {saidInOrder(elsewhere)}.
            </PanelFooter>
          ) : null}
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
  const markdown = report.data?.trim() ?? "";
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
        {/* The fourth state. A request that succeeds and returns nothing used to render as a
            panel with a header and a blank body, which reads as a component that failed
            rather than as a review with nothing in it yet — and the download beside it would
            have handed over an empty file without saying so. */}
        {markdown ? (
          <Markdown>{markdown}</Markdown>
        ) : (
          <EmptyState title="The report is empty">
            This review has been composed but has nothing in it to write up yet. It fills in as
            candidates are judged.
          </EmptyState>
        )}
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

/** The question in full, for the `title` on a tab that had to cut it short. */
function conversationQuestion(conversation: ReviewConversation): string | undefined {
  return conversation.messages[0]?.question.trim() || undefined;
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

      {/* One thread is read at a time, so the strip is where the others are accounted for:
          the question each was opened with, cut to a tab's width, and how many exchanges are
          inside it. A tab that said only "New question 2" would be the caret with nothing
          behind it. `title` carries the question back in full, because the cut is for the
          eye and not a decision to hide anything. */}
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
              // `role="tab"` is what this is; `aria-selected` is what a tab says about
              // itself. `ToggleButton` writes `aria-pressed`, which is the right word for a
              // filter chip and the wrong one here, so the tab states it in its own.
              aria-selected={current?.id === thread.id}
              pressed={current?.id === thread.id}
              title={conversationQuestion(thread)}
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
        {/* Four states, not one. A surface whose whole content arrives over the network used
            to render "No questions asked yet" while the request was still in flight, and to
            say the same thing when the request had failed — which is the one case where it
            is not true and the reader can do something about it. */}
        {conversations.isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2.5 text-sm text-ink-2"
          >
            <Spinner />
            Looking for the questions asked about this review…
          </div>
        ) : conversations.error ? (
          <ErrorNotice
            error={conversations.error}
            title="The questions asked about this review could not be loaded"
          />
        ) : current?.messages.length ? (
          <ol className="grid gap-4">
            {current.messages.map((message, index) => (
              <li key={`${message.asked_at}-${index}`} className="grid gap-2">
                <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
                  <Label>Question</Label>
                  {/* `wrap-anywhere` on both halves: a question is regularly a qualified
                      name with a few words around it, and an answer quotes paths back. One
                      token wider than a phone and nothing else in the panel can help. */}
                  <p className="mt-1 text-sm leading-6 text-ink wrap-anywhere">
                    {message.question}
                  </p>
                </div>
                <div className="rounded-md border border-rule bg-sunken/50 px-3 py-2.5">
                  <Label>Grounded answer</Label>
                  <p className="mt-1 whitespace-pre-line text-sm leading-6 text-ink-2 wrap-anywhere">
                    {message.answer.text}
                  </p>
                  {message.answer.supporting_candidate_ids.length ? (
                    <div className="mt-2 border-t border-rule pt-2">
                      {/* The charter asks every claim to say where it came from, and a row
                          of unheaded chips under a paragraph does not say what it is. */}
                      <Label>Answered from these findings</Label>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {message.answer.supporting_candidate_ids.map((id) => {
                          const finding = review.findings.find((item) => item.candidate.id === id);
                          // An answer is told where the evidence sits but never shown the code
                          // there, so a citation is the way to it rather than a footnote.
                          // `text-left` because a button centres its text by default, and a
                          // citation is a whole sentence — on a phone it wrapped to four
                          // centred lines, which reads as a pull quote rather than as a link.
                          if (finding && onOpen) {
                            return (
                              <button
                                key={id}
                                type="button"
                                title={finding.candidate.summary}
                                onClick={() => onOpen(id)}
                                className="max-w-full text-left"
                              >
                                <Tag className="transition hover:border-rule-strong hover:text-ink">
                                  {finding.candidate.summary}
                                </Tag>
                              </button>
                            );
                          }
                          if (finding) return <Tag key={id}>{finding.candidate.summary}</Tag>;
                          // No finding to name it with. A truncated id standing in as a
                          // label reads as the candidate's name, which it is not — so the
                          // chip says what happened and keeps the id in mono, where a
                          // machine string belongs.
                          return (
                            <Tag key={id} className="gap-1.5">
                              Cited candidate, not in this review
                              <span className="font-mono text-[11px] text-ink-3">
                                {shortId(id, 12)}
                              </span>
                            </Tag>
                          );
                        })}
                      </div>
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
          {/* `shrink-0`: everything on this page may be narrower than its content, which is
              what keeps a path from widening the page — but a three-letter button has
              nothing to give, and at 390px it was being squeezed to "As…". */}
          <Button
            className="shrink-0"
            disabled={!question.trim() || ask.isPending}
            onClick={() => ask.mutate()}
          >
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
