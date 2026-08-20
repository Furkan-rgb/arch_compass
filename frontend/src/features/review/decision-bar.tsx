import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";

import { api, type DecisionDisposition, type Finding, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { absoluteTime, verdictOf } from "../../lib/format";
import { DispositionBadge } from "../../ui/badge";
import { buttonClass } from "../../ui/button";
import { controlClass } from "../../ui/field";
import { Label } from "../../ui/panel";
import { ErrorNotice, LiveRegion } from "../../ui/states";
import { decisionIsStale } from "./attention-queue";

/**
 * The three dispositions, in the order a reviewer meets them, each with the key that takes it.
 *
 * `waive` is last and is the only one that opens anything. It is the rarest of the three and
 * the only one that cannot be recorded without a sentence — which is exactly why it stopped
 * owning the widest control in the bar. A reason input on permanent display was empty in
 * every state but one, and it was wider than the three decisions it sat above.
 */
const CHOICES: Array<{ id: DecisionDisposition; label: string; key: string; help: string }> = [
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
 * Whether the keystroke belongs to something being typed into.
 *
 * The queue's `j`/`k` already carries this guard and the reason is the same one, one letter
 * worse: a reviewer typing the word "Park" into a waiver's reason box means the word. With
 * `A`, `P` and `W` bound at the document there is no keystroke in a text field that is not
 * also a decision, so the guard is what makes the shortcuts safe to have at all.
 */
function isTyping(target: EventTarget | null): boolean {
  const node = target as HTMLElement | null;
  return Boolean(
    node && (node.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(node.tagName)),
  );
}

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

  const decisions = useQuery({
    queryKey: ["decisions", branchId],
    queryFn: () => api.decisions(branchId),
  });
  const current = decisions.data?.decisions.find((item) => item.candidate_id === candidateId);
  const stale = decisionIsStale(finding, current);

  const decide = useMutation({
    mutationFn: ({
      disposition,
      reasoning,
    }: {
      disposition: DecisionDisposition;
      reasoning: string | null;
    }) => api.decide(review.id, candidateId, disposition, reasoning),
    onSuccess: async (_result, variables) => {
      returning.current = variables.disposition === "waive" && waiving;
      setWaiving(false);
      setReason("");
      await client.invalidateQueries({ queryKey: ["decisions", branchId] });
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
   * open, which is a focus trap and not this surface.
   *
   * `W` opens the reveal rather than waiving, because a waiver without a reason is not a
   * decision this product will record.
   */
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target)) return;
      if (document.querySelector('[aria-modal="true"]')) return;
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
    <section aria-labelledby="standing-decision" className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <Label>
          <span id="standing-decision">Standing decision</span>
        </Label>
        {current ? <DispositionBadge disposition={current.disposition} /> : null}
      </div>

      {/* Who decided, and what they said. `wrap-anywhere` because both are free text from a
          person: an author name from a shell environment and a reason someone pasted are the
          two strings here long enough to widen the bar, and the bar is the narrowest column
          on a phone. */}
      <p className="mt-1.5 max-w-[58ch] text-sm leading-6 text-ink-2 wrap-anywhere">
        {current ? (
          <>
            <span className="font-medium text-ink">{current.author}</span> decided this on{" "}
            {absoluteTime(current.decided_at)}.
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
          <div className="text-[10px] font-bold uppercase tracking-[0.11em] text-held">
            Decided against a different verdict
          </div>
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
            <ErrorNotice error={decide.error} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
