import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";

import { api, type Decision, type DecisionDisposition, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, dispositionOf, verdictOf } from "../../lib/format";
import { hasOpenModal, isTyping } from "../../lib/keyboard";
import { DispositionBadge } from "../../ui/badge";
import { buttonClass } from "../../ui/button";
import { controlClass } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion, Spinner } from "../../ui/states";
import { decisionIsStale } from "./docket-rules";

/** What `GET /api/branches/{id}/decisions` answers with, named where it is written to. */
type BranchDecisions = Awaited<ReturnType<typeof api.decisions>>;

/**
 * The branch's standing decisions with one candidate's replaced, or added where it is new.
 *
 * A standing decision is one per candidate per branch — the record of what the team has
 * decided, not a log of what they have decided over time — so writing one is a replacement.
 * The history of the earlier ones is its own request, behind the fold at the foot of the bar.
 */
function withDecision(current: BranchDecisions, decision: Decision): BranchDecisions {
  return {
    ...current,
    decisions: [
      ...current.decisions.filter((item) => item.candidate_id !== decision.candidate_id),
      decision,
    ],
  };
}

/**
 * The three dispositions, in the order a reviewer meets them, each with the key that takes it.
 *
 * `waive` is last and is the only one that opens anything. It is the rarest of the three and
 * the only one that cannot be recorded without a sentence — which is exactly why it stopped
 * owning the widest control in the bar. A reason input on permanent display was empty in
 * every state but one, and it was wider than the three decisions it sat above.
 */
export const CHOICES: Array<{ id: DecisionDisposition; label: string; key: string; help: string }> = [
  {
    id: "accept",
    label: "Accept and act",
    key: "A",
    help: "The team intends to act on this finding.",
  },
  { id: "park", label: "Park", key: "P", help: "Acknowledged, deliberately not now." },
  {
    id: "waive",
    label: "Waive",
    key: "W",
    help: "The team disagrees, or accepts the trade-off. Needs a reason.",
  },
];

/**
 * The key that takes this decision, shown on the control that takes it.
 *
 * `aria-hidden`, with the shortcut announced by `aria-keyshortcuts` on the button instead:
 * folding the hint into the accessible name would make the button "Accept and act A", which
 * is a worse name for anyone listening to it and a worse thing to ask for by name in a test.
 *
 * Mono, because a key cap is a literal keystroke rather than a word, and `border-current` so
 * the cap reads on an ink fill and on a surface without knowing which it is on.
 */
function KeyCap({ children }: { children: string }) {
  return (
    <kbd
      aria-hidden="true"
      className="rounded-xs border border-current px-1 font-mono text-[10px] font-semibold leading-4 opacity-55"
    >
      {children}
    </kbd>
  );
}

/**
 * The human half of the review, kept visibly separate from the model's half.
 *
 * A standing decision belongs to the branch, not to this review: it survives the next run
 * and is what the team, rather than ArchCompass, has decided. Waiving needs a reason,
 * because a waiver with no reasoning is the one decision nobody can audit later — so the
 * reason field is revealed by `Waive` and by nothing else, and the confirm stays disabled
 * until there is one. Accept and Park carry no reason and stay one press.
 *
 * A decision also records the verdict it was taken against. When that no longer matches
 * what ArchCompass says, this leads with the discrepancy rather than with the decision:
 * the team settled a different question, and nothing withdraws the old record on their
 * behalf — it is stated, and the same three dispositions are offered again.
 */
export function DecisionBar({ review, finding }: { review: Review; finding: Finding }) {
  const client = useQueryClient();
  const branchId = review.repository.branch_id;
  const candidateId = finding.candidate.id;

  const [waiving, setWaiving] = useState(false);
  const [reason, setReason] = useState("");
  const waiveRef = useRef<HTMLButtonElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  // Set when a waiver is recorded from inside the reveal, so the focus that was in the reveal
  // has somewhere to land once it unmounts. Focus dropped on an unmounted button falls to the
  // body, and a keyboard reviewer starts the next candidate from the top of the document.
  const returning = useRef(false);

  const uid = useId();
  const panelId = `waiver-panel-${uid}`;
  const noteId = `waiver-note-${uid}`;
  // Scoped to this bar rather than a fixed string. Only one row of the docket is open at a
  // time today, so a constant id happened to be unique — which is a property of the docket,
  // not of this component, and the wrong thing for a component to rely on.
  const titleId = `standing-decision-${uid}`;

  const decisions = useQuery({
    queryKey: ["decisions", branchId],
    queryFn: () => api.decisions(branchId),
  });
  const current = decisions.data?.decisions.find((item) => item.candidate_id === candidateId);
  const stale = decisionIsStale(finding, current);

  /**
   * The decision lands on the list before the request does, and is taken back if it fails.
   *
   * It used to be two blocking round trips with a 45% fade over them: the POST, and then a
   * refetch of every standing decision on the branch — three hundred of them on an old
   * branch, re-downloaded to learn one new row — before the docket would settle the row and
   * move on. From the keyboard, scrolled away from the bar, there was no signal at all.
   *
   * So the optimistic row is written into the branch's list, which is where `needsAttention`
   * reads from, and the answer is *merged* into it rather than invalidating the query. What
   * the server adds — the id, the timestamp, the identities the finding was judged under — is
   * exactly what makes the merge worth doing rather than keeping the guess.
   *
   * The failure path is deliberately not only this bar. `main.tsx` toasts every mutation
   * error that a call site does not claim, and this one does not claim it: a decision taken
   * from the keyboard fails somewhere the reader is not looking, which is the whole reason
   * the toast exists.
   */
  const decide = useMutation({
    mutationFn: ({
      disposition,
      reasoning,
    }: {
      disposition: DecisionDisposition;
      reasoning: string | null;
    }) => api.decide(review.id, candidateId, disposition, reasoning),
    onMutate: async ({ disposition, reasoning }) => {
      await client.cancelQueries({ queryKey: ["decisions", branchId] });
      const previous = client.getQueryData<BranchDecisions>(["decisions", branchId]);
      const optimistic: Decision = {
        // The one field that is honestly a guess until the server answers. It is never shown:
        // the row keys on `candidate_id`, and the id exists so the merge has something to
        // replace.
        id: `pending-${candidateId}`,
        branch_id: branchId,
        candidate_id: candidateId,
        disposition,
        author: "user",
        reasoning,
        decided_at: new Date().toISOString(),
        review_id: review.id,
        // Decided against what is on screen, which is what makes the row settle rather than
        // re-raise the moment it is written.
        finding_verdict: finding.verdict,
        finding_model_identity: finding.model_identity,
        finding_prompt_identity: finding.prompt_identity,
        finding_retrieval_identity: finding.retrieval_identity,
      };
      client.setQueryData<BranchDecisions>(["decisions", branchId], (current) =>
        withDecision(current ?? { branch_id: branchId, decisions: [] }, optimistic),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      // Back to exactly what was there. A rolled-back row returns to the attention filter,
      // which is the truth: nothing was recorded.
      if (context?.previous) client.setQueryData(["decisions", branchId], context.previous);
    },
    onSuccess: (recorded, variables) => {
      returning.current = variables.disposition === "waive" && waiving;
      setWaiving(false);
      setReason("");
      client.setQueryData<BranchDecisions>(["decisions", branchId], (current) =>
        withDecision(current ?? { branch_id: branchId, decisions: [] }, recorded),
      );
      // Every decision about this candidate, which the fold below reads. It is lazy, so this
      // only matters where somebody has opened it — and there it is the one query that
      // genuinely gained a row.
      void client.invalidateQueries({ queryKey: ["decision-history", branchId, candidateId] });
    },
  });

  const busy = decide.isPending;
  const mutate = decide.mutate;
  const missing = !reason.trim();

  // Walking to the next candidate closes anything half-open. A reason typed against one
  // finding is not a reason for the next one, and a reveal left open would put the previous
  // candidate's half-written waiver under this candidate's name.
  useEffect(() => {
    setWaiving(false);
    setReason("");
  }, [candidateId]);

  // The reveal exists to be typed in, so it takes focus. Anything else asks the reviewer to
  // find the box that just appeared. Closing hands focus back to the control that opened it —
  // `busy` is in the dependencies because the trigger is disabled until the request settles,
  // and focusing a disabled button does nothing at all.
  useEffect(() => {
    if (waiving) {
      reasonRef.current?.focus();
      return;
    }
    if (!busy && returning.current) {
      returning.current = false;
      waiveRef.current?.focus();
    }
  }, [busy, waiving]);

  /**
   * `A`, `P` and `W` decide without leaving the keyboard.
   *
   * Bound at the document rather than at the bar, because the reviewer is usually still in
   * the queue when they decide — `j`/`k` to walk, then one letter — and the bar is scrolled
   * past on a phone. Three things are refused: a keystroke inside a text field, a keystroke
   * with a modifier (that is a browser command, not ours), and a keystroke while a drawer is
   * open, which is a focus trap and not this surface. The first and third are `lib/keyboard`,
   * which is where every surface that binds at the document asks the same two questions.
   *
   * `W` opens the reveal rather than waiving, because a waiver without a reason is not a
   * decision this product will record.
   */
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target) || hasOpenModal()) return;
      const choice = CHOICES.find((item) => item.key.toLowerCase() === event.key.toLowerCase());
      if (!choice || busy) return;
      event.preventDefault();
      if (choice.id === "waive") setWaiving(true);
      else mutate({ disposition: choice.id, reasoning: null });
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, mutate]);

  function cancelWaiver() {
    setWaiving(false);
    setReason("");
    waiveRef.current?.focus();
  }

  return (
    <section aria-labelledby={titleId} className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <Label>
          <span id={titleId}>Standing decision</span>
        </Label>
        {current ? <DispositionBadge disposition={current.disposition} /> : null}
      </div>

      {/* When it was decided, and what was said. `wrap-anywhere` because the reason is free
          text somebody pasted, and the bar is the narrowest column on a phone.

          It used to lead with `current.author`, set in ink as though it were a name. Every
          decision this product records carries the author `"user"`, so it printed a person
          called user, and the name travelled into the immutable record and into every future
          review's comparison. The content rule is explicit that an explicit unknown outranks
          an implied one, and a fake name is worse than a blank — so until there is an
          identity to record, the sentence says what is actually known: this branch, and
          when. The field stays on the wire, where a real identity will arrive. */}
      <p className="mt-1.5 max-w-[58ch] text-sm leading-6 text-ink-2 wrap-anywhere">
        {current ? (
          <>
            Recorded on this branch on {absoluteTime(current.decided_at)}.
            {current.reasoning ? (
              <span className="mt-1 block text-ink-3">“{current.reasoning}”</span>
            ) : null}
          </>
        ) : (
          "Nobody has decided this."
        )}
      </p>

      {stale && current ? (
        <div className="mt-3 border-l-2 border-held pl-3.5">
          <Label className="text-held">Decided against a different verdict</Label>
          <p className="mt-1.5 max-w-[58ch] text-[13px] leading-6 text-ink-2">
            The team decided this when ArchCompass called it{" "}
            <span className="font-semibold text-ink">
              {verdictOf(current.finding_verdict).label.toLowerCase()}
            </span>
            . This review calls it{" "}
            <span className="font-semibold text-ink">
              {verdictOf(finding.verdict).label.toLowerCase()}
            </span>
            . The record stands as it was made — recording a decision again is what settles
            it against what ArchCompass says now.
          </p>
        </div>
      ) : null}

      {/* The controls. Deliberately not pinned.

          This was `sticky bottom-0`, and it was inert: `finding-detail.tsx` wraps the article
          in `overflow-hidden` — it has to, because the article is `rounded-lg` and its last
          child paints a background into the corner — and an `overflow` ancestor becomes the
          scrollport for anything sticky inside it, so the bar pinned to a box that never
          scrolls.

          It was removed rather than repaired, because the reason for pinning it went away.
          A floating bar was compensating for a finding long enough that the decision fell off
          the bottom of it; folding measurement, policies and provenance behind honest closed
          states is what actually fixed that, and it cut the article by roughly a quarter. The
          decision now sits a short scroll from the verdict that prompts it. `A`, `P` and `W`
          reach it from anywhere on the page without scrolling at all.

          If a finding ever grows long enough that this stops being true, the fix is to make
          the bar a direct child of the article and drop the `overflow-hidden` in favour of
          rounding the last child — not to re-add a declaration the ancestor cancels. */}
      <div className="mt-3.5 border-t border-rule bg-surface pt-3.5">
        {/* Deliberate wrapping, not accidental. At 390px the three labels plus their key caps
            do not fit on one line, and letting flex-wrap decide gives "Accept and act" and
            "Park" a row and leaves "Waive" alone under them. Two columns with the primary
            spanning both is the same three buttons at a thumb's width each. */}
        <div
          role="group"
          aria-label="Record a standing decision"
          className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap"
        >
          {CHOICES.map((choice) => {
            const isWaive = choice.id === "waive";
            // The ink fill says "this is what stands", not "do this". Which of the three a
            // team should take is not ArchCompass's to suggest.
            const recorded = current?.disposition === choice.id && !stale;
            return (
              <button
                key={choice.id}
                ref={isWaive ? waiveRef : undefined}
                type="button"
                title={choice.help}
                aria-keyshortcuts={choice.key}
                aria-expanded={isWaive ? waiving : undefined}
                aria-controls={isWaive ? panelId : undefined}
                disabled={busy}
                onClick={() =>
                  isWaive
                    ? setWaiving(true)
                    : mutate({ disposition: choice.id, reasoning: null })
                }
                className={cn(
                  buttonClass(recorded ? "primary" : "secondary", "md"),
                  // 44px rather than the control default of 40: this is the row of the page a
                  // phone is most likely to be aimed at with a thumb.
                  "min-h-11 px-3",
                  choice.id === "accept" && "col-span-2 sm:col-span-1",
                )}
              >
                <span>{choice.label}</span>
                <KeyCap>{choice.key}</KeyCap>
              </button>
            );
          })}
        </div>

        {/* The region the trigger names in `aria-controls`, and one label inside it.
            Labelling the region *and* the field with the same words gives two elements the
            same accessible name, which is ambiguous to read out and ambiguous to ask for:
            the field is the thing being named, so it is the only thing that carries it. */}
        {waiving ? (
          <div
            id={panelId}
            className="animate-expand mt-2.5 rounded-md border border-rule bg-surface-2 p-3"
          >
            <label
              htmlFor={`${panelId}-field`}
              className="block text-xs font-semibold text-ink"
            >
              Why the team waives this
            </label>
            <textarea
              ref={reasonRef}
              id={`${panelId}-field`}
              value={reason}
              aria-describedby={noteId}
              disabled={busy}
              onChange={(event) => setReason(event.target.value)}
              onKeyDown={(event) => {
                // Escape is how a reveal is closed everywhere else on this page.
                if (event.key === "Escape") {
                  event.preventDefault();
                  cancelWaiver();
                }
              }}
              placeholder="What the team knows that this finding does not."
              className={cn(controlClass, "mt-1.5 min-h-20 resize-y leading-6")}
            />
            {/* Said in words, not only by a disabled button. A control that is grey for a
                reason nobody states is a control a reviewer clicks twice and then abandons. */}
            <p id={noteId} className="mt-1.5 text-xs leading-5 text-ink-3">
              {missing
                ? "A waiver needs a reason. It is the part of this decision the next review reads back."
                : "Recorded on the branch, and shown against this candidate in the next review."}
            </p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy || missing}
                onClick={() => mutate({ disposition: "waive", reasoning: reason.trim() })}
                className={cn(buttonClass("primary", "md"), "min-h-11 grow sm:grow-0")}
              >
                Record waiver
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={cancelWaiver}
                className={cn(buttonClass("ghost", "md"), "min-h-11 grow sm:grow-0")}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}

        {decide.isSuccess ? <LiveRegion>Standing decision recorded.</LiveRegion> : null}
        {decide.error ? (
          <div className="mt-3">
            <ErrorNotice
              error={decide.error}
              title="That decision was not recorded"
              action={
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    // The same decision, not a fresh one: what failed was the request, and
                    // asking the reviewer to choose again would be asking them to re-decide.
                    if (decide.variables) mutate(decide.variables);
                  }}
                  className={cn(buttonClass("secondary", "sm"))}
                >
                  Record it again
                </button>
              }
            />
          </div>
        ) : null}

        {current ? <DecisionHistory branchId={branchId} finding={finding} /> : null}
      </div>
    </section>
  );
}

/**
 * What the team has decided about this candidate before, newest first.
 *
 * `api.decisionHistory` has been written, typed and called from nowhere. The question it
 * answers is the one a re-raised row now provokes: the bar says "the team decided this when
 * ArchCompass called it held", and the immediate next question is what was decided the last
 * four times, by whom, and against what.
 *
 * Fetched on opening rather than with the review. Most rows are never asked this, and a
 * request per row of a forty-row docket to fill a fold nobody opened is the shape of thing
 * this audit exists to remove.
 *
 * It reads the identity triple as well as the verdict. A decision taken when a different
 * model judged, or against a different policy corpus, is a decision made about something
 * else — which the row-level staleness check cannot see, because it compares verdicts, and
 * two models can agree on a verdict for different reasons.
 */
function DecisionHistory({ branchId, finding }: { branchId: string; finding: Finding }) {
  const candidateId = finding.candidate.id;
  const [asked, setAsked] = useState(false);
  const history = useQuery({
    queryKey: ["decision-history", branchId, candidateId],
    queryFn: () => api.decisionHistory(branchId, candidateId),
    enabled: asked,
    // A decision that has been recorded cannot change; only a new one can arrive, and the
    // bar above invalidates this when it records one.
    staleTime: Infinity,
  });

  return (
    <details
      className="group mt-3 border-t border-rule pt-3"
      onToggle={(event) => {
        if (event.currentTarget.open) setAsked(true);
      }}
    >
      <summary className="flex min-h-11 list-none items-center gap-2 rounded-sm transition focus-visible:-outline-offset-2">
        <Label className="min-w-0 flex-1 text-left">
          Decided before{history.data ? ` · ${history.data.length}` : ""}
        </Label>
        <ChevronDown className="size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
      </summary>

      {history.isLoading ? (
        <p className="flex items-center gap-2 text-[12.5px] text-ink-3">
          <Spinner label="" /> Reading what was decided before…
        </p>
      ) : history.error ? (
        <ErrorNotice
          error={history.error}
          title="That history could not be read"
          action={
            <button
              type="button"
              onClick={() => void history.refetch()}
              className={cn(buttonClass("secondary", "sm"))}
            >
              Try again
            </button>
          }
        />
      ) : !history.data?.length ? (
        <p className="text-[12.5px] leading-6 text-ink-3">
          Nothing was decided about this candidate before the record above.
        </p>
      ) : (
        <ol className="grid gap-1.5">
          {history.data.map((entry) => {
            const disposition = dispositionOf(entry.disposition);
            // The whole judgement it answered, not only its verdict. A decision taken under
            // a different model or a different corpus is one taken about a different thing,
            // and today that passes in silence on every model change.
            const judgedBy = [
              entry.finding_model_identity === finding.model_identity ? null : "a different model",
              entry.finding_prompt_identity === finding.prompt_identity
                ? null
                : "a different prompt",
              entry.finding_retrieval_identity === finding.retrieval_identity
                ? null
                : "a different retrieval",
            ].filter(Boolean) as string[];
            return (
              <li
                key={entry.id}
                className="rounded-md border border-rule bg-surface-2 px-3 py-2 text-[12.5px] leading-5 text-ink-2"
              >
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="font-semibold text-ink">{disposition.label}</span>
                  <span className="text-ink-3">
                    against {verdictOf(entry.finding_verdict).label.toLowerCase()}
                  </span>
                  <span className="font-mono text-[11px] text-ink-3">
                    {absoluteTime(entry.decided_at)}
                  </span>
                </div>
                {judgedBy.length ? (
                  <p className="mt-1 text-ink-3">Judged by {judgedBy.join(", ")} than this one.</p>
                ) : null}
                {entry.reasoning ? (
                  <p className="mt-1 wrap-anywhere">“{entry.reasoning}”</p>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
    </details>
  );
}
