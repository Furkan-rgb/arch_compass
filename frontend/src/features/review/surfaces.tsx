import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { cn } from "../../lib/cn";
import { type MarkShape, humanise, shortId, splitQualified, verdictOf } from "../../lib/format";
import { Badge, VerdictBadge } from "../../ui/badge";
import { Button, ToggleButton } from "../../ui/button";
import { ArrowRight, ChevronDown } from "../../ui/icons";
import { Mark } from "../../ui/mark";
import { TONE_EDGE } from "../../ui/meta";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { Prose, plainProse } from "../../ui/prose";
import { EmptyState, ErrorNotice, LiveRegion, Skeleton, Spinner } from "../../ui/states";
import { AskBox, ConversationExchange, useConversations } from "./conversation-thread";

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
 * **None of the four carries a hue.** `changed` used to be amber, which is the bug the palette
 * rule exists for: `held` is a verdict the model reached, not "this row moved", and a changed
 * candidate can come back material, held or cleared. `addressed` used to be green on the
 * argument that its row had no verdict badge to carry colour — true at the time, and fixed by
 * giving it one (`No longer detected`, in the cleared tone, in the slot every other row fills
 * with its verdict) rather than by tinting a glyph.
 *
 * What that leaves is the arrangement the palette rule was always asking for: **one coloured
 * thing per row, in one place.** The badge slot says where the candidate stands, in the
 * verdict's own hue; this column says how it moved, in ink; and a reader can scan either
 * without the two competing.
 *
 * So the step here is weight, in the order this list is read — `addressed` and `changed` at
 * full ink because both want re-reading, `new` at `ink-2` because it is also sitting in the
 * docket, `unchanged` at `ink-3` because it is exactly what a returning reader opened this
 * surface to skip.
 */
const DELTA_STATES: ReadonlyArray<{
  id: DeltaState;
  label: string;
  glyph: MarkShape;
  tone: string;
  says: string;
}> = [
  // Diff notation, drawn rather than typed. These were `✓ ~ + =` set in mono — the same
  // failure the geometric shapes were, surviving longer only because three of them are ASCII
  // and the guard looked at one Unicode block. `addressed` losing its tick is the point of
  // the change and not a casualty of it: "raised last time, gone now" is a comparison between
  // two reviews, and a tick is the mark the *cleared verdict* wears. A minus beside a plus
  // says what actually happened — it left the list — and reads as a diff at a glance.
  {
    id: "addressed",
    label: "Addressed",
    glyph: "minus",
    tone: "text-ink",
    says: "Raised last time, gone now",
  },
  {
    id: "changed",
    label: "Changed",
    glyph: "swap",
    tone: "text-ink",
    says: "The same candidate, judged again",
  },
  { id: "new", label: "New", glyph: "plus", tone: "text-ink-2", says: "Not in the previous review" },
  { id: "unchanged", label: "Unchanged", glyph: "equals", tone: "text-ink-3", says: "As it was" },
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
    <div className="min-w-0">
      {/* Above the grid rather than inside its second column, and indented to line up with
          the name below it. The movement mark used to be optically centred on whatever the
          first line happened to be, which on a row with a namespace was the 10.5px eyebrow —
          so the plus read as attached to the package rather than to the candidate. With the
          eyebrow lifted out, the mark centres on the identifier, which is what it is about. */}
      {namespace ? (
        <span className="block truncate pl-7 font-mono text-[10.5px] text-ink-3">{namespace}</span>
      ) : null}
      <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-3">
        <span className={cn("mt-[3px] grid place-items-center", state.tone)}>
          <Mark shape={state.glyph} className="size-[15px]" />
        </span>
        <span className="min-w-0">
          {/* The namespace above may be cut — it is context. The name is the identity and the
            sentence is the reason, so both get two lines and break mid-token rather than
            ending in an ellipsis. On a phone one truncated line of either said nothing but
            `src.audiobook.preparation.provid…`, which the namespace had already said. Same
            rule as the queue, which is the list this one is read against.

            Three lines where the identity is a sentence rather than a name. An addressed
            candidate is carried through this list by its summary — there is no finding and
            no row to open — so that sentence is the whole of what it is, and a name needs
            one line fewer than a sentence does. */}
          <span
            className={cn(
              "text-[13px] font-medium leading-[1.35] text-ink wrap-anywhere",
              entry.identityIsName ? "line-clamp-2 font-mono" : "line-clamp-3",
            )}
          >
            {/* `bare` here and on the sentence below it, and only ever bare: this is a
                scanning surface. A chip's border and its `px-1 py-0.5` add about five pixels
                to whatever line box it lands in, so one clamped row in a column of forty
                grows taller than its neighbours and the column stops lining up — the same
                shape of problem the heading exception in `ui/markdown.tsx` was written for.
                The face alone still says the word is a name.

                Only the sentence branch of the identity takes it: where the identity is a
                name this span is already `font-mono`, and that name came from the atlas
                rather than from a model, so there is nothing in it to parse. */}
            {entry.identityIsName ? leaf : <Prose bare>{leaf}</Prose>}
          </span>
          {entry.summary ? (
            <span className="mt-0.5 line-clamp-2 text-xs leading-5 text-ink-2 wrap-anywhere">
              <Prose bare>{entry.summary}</Prose>
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
                  <ArrowRight className="size-[13px] shrink-0 text-ink-3" />
                  <span className="sr-only">, now </span>
                </>
              ) : null}
              {entry.nowVerdict && !hoisted.verdict ? (
                <VerdictBadge verdict={entry.nowVerdict} className="px-2 py-0.5 text-[10px]" />
              ) : !hoisted.verdict && entry.state === "addressed" ? (
                // In the slot every other row fills with a verdict badge, so the surface has
                // one coloured thing per row saying where the candidate stands. It was a
                // neutral tag, which left the one state that exists nowhere else in the product
                // as the dimmest row on the page. The tone comes from the table, not from here.
                <Badge tone="cleared" glyph="minus" className="px-2 py-0.5 text-[10px]">
                  No longer detected
                </Badge>
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
    </div>
  );

  /**
   * The verdict as a left edge, which is the device the docket row uses and the reason this
   * row was missing one.
   *
   * Both rows open the same finding, and the hoisting rule above deliberately removes the
   * verdict badge from every row whenever the whole visible list shares one — which is the
   * ordinary case on a first review. So on the surface the charter calls first-class for the
   * second visit, a candidate could carry no statement of its verdict at all. An edge is read
   * without being looked at, costs no horizontal space, and survives hoisting because it is
   * not a thing on the row: it is the row's own boundary. The hue comes from the tone table
   * in `ui/meta.tsx`, the same way the badge above gets its own.
   */
  const edge = entry.nowVerdict
    ? TONE_EDGE[verdictOf(entry.nowVerdict).tone]
    : entry.state === "addressed"
      ? TONE_EDGE.cleared
      : "border-l-transparent";

  // An addressed candidate is not in this review, so there is nothing to open — it is shown
  // as a record, not as a destination. `title` carries the whole of what it is: this row's
  // identity is its summary sentence, that sentence is clamped, and unlike every other row
  // there is no button underneath it holding the full string.
  if (!onOpen) {
    return (
      <li title={plainProse(entry.identity)} className={cn("border-l-[3px] px-4 py-3 sm:px-5", edge)}>
        {body}
      </li>
    );
  }
  return (
    <li className={cn("border-l-[3px]", edge)}>
      <button
        type="button"
        onClick={onOpen}
        title={plainProse(entry.identity)}
        // The ring is drawn `outline-offset: 2px`, which on a full-bleed row in a divided
        // list lands on the neighbouring row's rule. Pulled inside, it frames the row it is
        // actually on. `min-h-11` is the target floor: a row with a short name and no
        // sentence is otherwise about 40px on a phone.
        className="flex min-h-11 w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-sunken focus-visible:-outline-offset-2 sm:px-5"
      >
        <span className="min-w-0 flex-1">{body}</span>
        {/* Pointing right, not down: this row opens the finding on another surface rather
            than expanding in place, and the docket's rotating disclosure chevron would
            promise the wrong thing. Below `sm` it goes — a phone has no width to spend on an
            affordance a tap already carries. */}
        <ChevronDown
          aria-hidden="true"
          className="hidden size-4 shrink-0 -rotate-90 text-ink-3 sm:block"
        />
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
export function DeltaSurface({ review, onOpen }: { review: Review; onOpen?: (candidateId: string) => void }) {
  const [state, setState] = useState<DeltaState | "all">("all");
  /**
   * The lineage, for the one thing the delta cannot say on its own.
   *
   * `ReviewDelta` records the last verdict only for a candidate that has gone away; for one
   * that changed it records the causes and nothing about what the model used to say. So the
   * before half of "was held, now material" has to come from the previous review itself.
   *
   * That review, by its id — not the whole review list filtered down to it. A stored review
   * is most of a repository's atlas, so asking for every review on the workspace to read one
   * verdict off one of them downloaded megabytes to print a badge. Where it cannot be read,
   * no transition is claimed: saying nothing is the honest failure here, and guessing at a
   * verdict is not.
   */
  const earlier = useQuery({
    queryKey: ["review", review.previous_review_id],
    queryFn: () => api.review(review.previous_review_id!),
    enabled: Boolean(review.previous_review_id),
    // A recorded review cannot change, so this is fetched once for the life of the tab.
    staleTime: Infinity,
  });
  const previous = earlier.data ?? null;

  const findingOf = (candidateId: string) => review.findings.find((item) => item.candidate.id === candidateId) ?? null;
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
    if (finding?.candidate.summary) return { identity: finding.candidate.summary, identityIsName: false };
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
  const sharedVerdict = visible.some((entry) => entry.wasVerdict) ? null : agreesOn((entry) => entry.nowVerdict);
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
                <span className="font-mono">{shortId(review.previous_review_id, 8)}</span>) by candidate identity — not
                by what the model said either time.
              </>
            ) : (
              // The group header below hoists this same sentence onto the list, one screen
              // lower and in the words the rows are read in, so the description says only
              // what the header cannot: that there is no predecessor at all.
              "Nothing to compare against yet."
            )
          }
        />
        {/* The counts are the filter. Four numbers you can only read, next to a list you
            then have to scan by hand, is two controls' worth of screen doing one job.

            `role="group"` because five `aria-pressed` buttons with no container are five
            unrelated toggles to anything that is not looking at them, rather than one filter
            over the list below — which is what the docket's identical control already says
            about itself. */}
        <PanelBody>
          <div role="group" aria-label="Filter by what moved" className="flex flex-wrap gap-1.5">
            <ToggleButton pressed={state === "all"} onClick={() => setState("all")}>
              All
              <span className="tabular-nums">{entries.length}</span>
            </ToggleButton>
            {/* The states that have candidates come first, in declared order, and the empty
              ones wrap below them. Declared order is right when every state is populated and
              wrong on a first review, where three of the four are zero and a phone put the
              one live chip on a second line behind a queue of dead ones. Every chip stays:
              the zero is the answer to "was anything addressed", which is the most useful
              fact on a second visit. */}
            {[...DELTA_STATES]
              .sort(
                (left, right) =>
                  Number(Boolean(counts[right.id])) - Number(Boolean(counts[left.id])),
              )
              .map((item) => (
                <ToggleButton
                  key={item.id}
                  pressed={state === item.id}
                  disabled={!counts[item.id]}
                  onClick={() => setState(item.id)}
                  title={item.says}
                >
                  <Mark shape={item.glyph} className={cn("size-[14px]", item.tone)} />
                  {item.label}
                  <span className="tabular-nums">{counts[item.id]}</span>
                </ToggleButton>
              ))}
          </div>
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
            /* `bg-surface-2`, the ground the elevation contract gives a panel's header and
               every static strip set into a panel. This one is drawn here rather than by
               `PanelHeader`, so it had the panel's own white — the same white as the rows
               beneath it, which hover to `--sunken` — and nothing on the panel said which of
               its two parts did something. `rounded-t-lg` because a strip that paints to the
               edge is the part that notices the panel's 14px corner. */
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-t-lg border-b border-rule bg-surface-2 px-4 py-2.5 sm:px-5">
              <span className="text-[11px] font-semibold text-ink-2">All {visible.length}</span>
              {sharedVerdict ? <VerdictBadge verdict={sharedVerdict} className="px-2 py-0.5 text-[10px]" /> : null}
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
          {/* The same sentence the footer prints, for anybody who is not looking at the list
              a filter chip just rewrote. It is `sr-only` and costs no layout, so it stands
              whether or not the footer is drawn. */}
          <LiveRegion>
            Showing {visible.length} of {entries.length}.
          </LiveRegion>
          {elsewhere.length ? (
            <PanelFooter className="text-xs leading-5 text-ink-3">
              Showing {visible.length} of {entries.length}. Also in this review: {saidInOrder(elsewhere)}.
            </PanelFooter>
          ) : null}
        </Panel>
      )}
    </div>
  );
}

/**
 * What a conversation is called: the question that opened it.
 *
 * Cut from the stripped string rather than from the raw one. A `title` and a tab label are
 * both strings, so neither can hold a rendered name — and slicing the raw question at 44
 * characters can land inside a quoted one, which leaves a single unpaired backtick sitting on
 * the tab with nothing to explain it.
 */
function conversationTitle(conversation: ReviewConversation, index: number): string {
  const first = plainProse(conversation.messages[0]?.question.trim() ?? "");
  if (!first) return `New question ${index + 1}`;
  return first.length > 44 ? `${first.slice(0, 44)}…` : first;
}

/**
 * Three openings, offered rather than described.
 *
 * The surface already knew these — it printed them as one centred sentence over an empty
 * field, which is the charter's rule inverted: never make somebody type what they could
 * pick. Pressing one writes it into the box rather than sending it, because an opening is a
 * starting point somebody is expected to finish in their own words.
 */
const ASK_OPENERS = [
  "Why was this cleared?",
  "What does this policy cover?",
  "Which finding should I take first?",
];

/** The question in full, for the `title` on a tab that had to cut it short. */
function conversationQuestion(conversation: ReviewConversation): string | undefined {
  return plainProse(conversation.messages[0]?.question.trim() ?? "") || undefined;
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
export function AskSurface({ review, onOpen }: { review: Review; onOpen?: (candidateId: string) => void }) {
  // The unscoped family. Threads opened under a clarification question belong to that
  // question's panel and to the Rounds surface, and listing them here would put a reader's
  // half-finished working-out of question two among their notes about the review.
  const client = useQueryClient();
  const { conversations, threads, current, setConversationId, ask } =
    useConversations(review);
  const [question, setQuestion] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);

  // A thread with nothing in it is the one being started; there is never a reason to have
  // two, so the button that starts one steps aside once an empty one exists.
  const empty = threads.find((item) => !item.messages.length);

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
          // Not disabled while an empty thread exists. The press already did something
          // useful in that case — it selects the empty thread — so the disabled state was
          // hiding a working action, taking the control out of the tab order and leaving its
          // only explanation in a `title` that a keyboard, a screen reader and a phone all
          // reach in exactly no ways. The button says what it will do instead.
          <Button
            variant="secondary"
            size="sm"
            disabled={open.isPending}
            onClick={() => (empty ? setConversationId(empty.id) : open.mutate())}
          >
            {/* The word stays and the mark joins it: swapping the label for a spinner
                collapsed the button to about 32px in a header row and changed its accessible
                name to "Working". */}
            {open.isPending ? (
              <>
                <Spinner label="" /> Opening
              </>
            ) : empty ? (
              "Go to the empty conversation"
            ) : (
              "New conversation"
            )}
          </Button>
        }
      />

      {/* One thread is read at a time, so the strip is where the others are accounted for:
          the question each was opened with, cut to a tab's width, and how many exchanges are
          inside it. A tab that said only "New question 2" would be the caret with nothing
          behind it. `title` carries the question back in full, because the cut is for the
          eye and not a decision to hide anything. */}
      {threads.length > 1 ? (
        /**
         * A tablist has to behave like one, and this one only claimed to be one.
         *
         * `role="tablist"` promises a single tab stop with the arrow keys walking between
         * the tabs, and every tab pointing at the panel it governs. None of that was here:
         * five separate tab stops, no keyboard traversal, no `aria-controls`, and each tab
         * announcing `aria-selected` *and* `aria-pressed` — two different state words on one
         * control, because `ToggleButton` writes the second unconditionally. `aria-pressed`
         * is now cleared explicitly; the spread runs after the base, so `undefined` removes
         * the attribute rather than setting it.
         *
         * `ui/tabs.tsx` does implement all of this, and this strip still does not use it:
         * its solid variant is a track-and-pill drawn for a control that sits in a row, where
         * this is a full-bleed strip with its own bottom rule, and its `TabItem` label is
         * `whitespace-nowrap` with no truncation — a 44-character question would push the
         * strip wider than the panel. Teaching `Tabs` a truncating label is the right fix and
         * it is not this file's to make.
         */
        <div
          role="tablist"
          aria-label="Conversations"
          className="flex flex-wrap gap-1.5 border-b border-rule px-4 py-2.5 sm:px-5"
          onKeyDown={(event) => {
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            const at = threads.findIndex((item) => item.id === current?.id);
            const to =
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? threads.length - 1
                  : step
                    ? (at + step + threads.length) % threads.length
                    : -1;
            if (to < 0) return;
            event.preventDefault();
            setConversationId(threads[to].id);
            // The tab a reader arrows onto takes the focus with it, which is what makes the
            // single tab stop navigable rather than merely tidy.
            event.currentTarget.querySelectorAll("button")[to]?.focus();
          }}
        >
          {threads.map((thread, index) => {
            const selected = current?.id === thread.id;
            return (
              <ToggleButton
                key={thread.id}
                id={`conversation-tab-${thread.id}`}
                role="tab"
                // `role="tab"` is what this is; `aria-selected` is what a tab says about
                // itself, and `aria-pressed` is the word for a filter chip.
                aria-selected={selected}
                aria-pressed={undefined}
                aria-controls="conversation-panel"
                tabIndex={selected ? 0 : -1}
                pressed={selected}
                title={conversationQuestion(thread)}
                onClick={() => setConversationId(thread.id)}
                className="max-w-[18rem]"
              >
                <span className="truncate">{conversationTitle(thread, index)}</span>
                <span className="tabular-nums">{thread.messages.length}</span>
              </ToggleButton>
            );
          })}
        </div>
      ) : null}

      <PanelBody>
        {/* The panel the strip above points at. Without it every tab claimed to control
            something that was not in the document. It is only a tabpanel where there is a
            tablist: one thread is a transcript, not a tab. */}
        <div
          id="conversation-panel"
          role={threads.length > 1 ? "tabpanel" : undefined}
          aria-labelledby={
            threads.length > 1 && current ? `conversation-tab-${current.id}` : undefined
          }
        >
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
              {/* The sentence beside it says what is being waited on, so the spinner does not
                say it a second time. */}
              <Spinner label="" />
              Looking for the questions asked about this review…
            </div>
          ) : conversations.error ? (
            <ErrorNotice
              error={conversations.error}
              title="The questions asked about this review could not be loaded"
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void conversations.refetch()}
                >
                  Try again
                </Button>
              }
            />
          ) : current?.messages.length || ask.isPending ? (
            <ol className="grid gap-4">
              {(current?.messages ?? []).map((message, index) => (
                <li key={`${message.asked_at}-${index}`}>
                  <ConversationExchange message={message} review={review} onOpen={onOpen} />
                </li>
              ))}
              {/* The question, kept on screen while it is being answered. `AskBox` clears its
                box on send and nothing writes the question optimistically, so for the tens of
                seconds a round trip takes the reader's own words were simply gone and nothing
                had taken their place — on a first question, the empty state sat unchanged for
                the whole wait. The placeholder unmounts when the real exchange arrives. */}
              {ask.isPending && ask.variables ? (
                <li aria-live="polite">
                  <div className="grid gap-2">
                    <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
                      <Label>Question</Label>
                      {/* Drawn exactly as `ConversationExchange` draws the same string one
                          render later, so the placeholder does not change shape the moment
                          the real exchange replaces it. */}
                      <p className="mt-1 text-sm leading-6 text-ink wrap-anywhere">
                        <Prose>{ask.variables}</Prose>
                      </p>
                    </div>
                    <div className="grid gap-1.5 px-3 py-1">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-2/3" />
                    </div>
                  </div>
                </li>
              ) : null}
            </ol>
          ) : null}

          <div
            className={cn(
              current?.messages.length || ask.isPending ? "mt-4 border-t border-rule pt-4" : "",
            )}
          >
            <AskBox
              label="Question about this review"
              placeholder="How would the gateway finding be fixed?"
              pending={ask.isPending}
              value={question}
              onChange={setQuestion}
              onAsk={(text) => ask.mutate(text)}
            />
            {/* What used to be an `EmptyState`: 16px semibold, centred, in a dashed box 205px
              tall, which pushed the only thing on the surface a reader can act on a quarter
              of the panel down. An announcement that nothing has happened does not outrank
              the control that makes something happen, so it is a line of guidance under the
              box — and the three things it suggests are offered rather than described,
              because the charter's rule is never to make somebody type what they could pick. */}
            {!current?.messages.length && !ask.isPending ? (
              <div className="mt-2.5">
                <p className="text-[13px] leading-6 text-ink-3">
                  Ask what the review found, or what to do about it. Every fact in an answer comes
                  from this review.
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {ASK_OPENERS.map((opener) => (
                    <ToggleButton key={opener} pressed={false} onClick={() => setQuestion(opener)}>
                      {opener}
                    </ToggleButton>
                  ))}
                </div>
              </div>
            ) : null}
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
                    {/* The word stays, the mark joins it: a confirm row that shrinks its own
                      destructive button to 32px moves Keep sideways under the pointer. */}
                    {discard.isPending ? (
                      <>
                        <Spinner label="" /> Discarding
                      </>
                    ) : (
                      "Discard"
                    )}
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
              <ErrorNotice
                error={ask.error}
                title="That question was not answered"
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={ask.isPending || !ask.variables}
                    onClick={() => ask.variables && ask.mutate(ask.variables)}
                  >
                    Ask it again
                  </Button>
                }
              />
            </div>
          ) : null}
          {discard.error && confirming ? (
            <div className="mt-3">
              <ErrorNotice
                error={discard.error}
                title="That conversation was not discarded"
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={discard.isPending}
                    onClick={() => discard.mutate(confirming)}
                  >
                    Try again
                  </Button>
                }
              />
            </div>
          ) : null}
          {open.error ? (
            <div className="mt-3">
              <ErrorNotice
                error={open.error}
                title="That conversation was not opened"
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={open.isPending}
                    onClick={() => open.mutate()}
                  >
                    Try again
                  </Button>
                }
              />
            </div>
          ) : null}
        </div>
      </PanelBody>
    </Panel>
  );
}
