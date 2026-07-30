import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { api } from "./api";
import { ErrorPanel } from "./components";
import { FindingSource } from "./finding-source";
import { AnswerProse } from "./markdown";

/**
 * Asking about a review, in a panel beside it rather than a dock beneath it.
 *
 * The conversation used to ride the bottom of the page in a slot that measured how close the
 * reader was to the end of the document and grew when they got there. It cost a scroll
 * listener, a reserved 20vh of every review, and a permanent band of chrome under the
 * verdicts — for a surface most readings never open. It is now a panel the reader asks for,
 * floating at the right edge; the page keeps its full height and nothing measures anything.
 *
 * Non-modal on purpose: a question is asked *about* what is on screen, so the ledger stays
 * readable and clickable behind it. Nothing here traps focus, and Escape closes it.
 */

/* One message bubble, in the two shapes a turn has. The question is the reader's and sits
   against the right edge in the accent; the answer is the review's and sits against the
   left on the plain surface, with the corner nearest its own side squared off. */
const bubble = "m-0 min-w-0 max-w-[92%] rounded-panel px-3.5 py-2.5 text-meta leading-[1.55] [overflow-wrap:anywhere]";
const asked = `${bubble} justify-self-end rounded-br-control border border-accent-rule bg-accent-soft`;
const answered = `${bubble} justify-self-start rounded-bl-control border border-rule bg-surface text-ink-2`;
/* Labelled, never hidden: a reader has to be able to tell "the review says this" from
   "the model thinks this". */
const grounding = "mt-2 text-micro text-ink-3";
/* One row of threads: durable, so worth returning to, and never more than a handful. A pill
   rather than a segmented well — they are places to go back to, not a filter over one list. */
const threadPill = cn(
  "inline-flex max-w-full cursor-pointer items-center gap-1 rounded-pill border border-rule",
  "bg-surface px-2 py-0.5 text-micro whitespace-nowrap text-ink-2",
  "hover:border-ink-3 hover:text-ink",
  "aria-pressed:border-accent-rule aria-pressed:bg-accent-soft aria-pressed:text-accent-ink",
);

export function AskPanel({
  reviewId,
  open,
  onClose,
}: {
  reviewId: string;
  open: boolean;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [question, setQuestion] = useState("");
  /**
   * The question being answered right now, and the prose that has arrived for it.
   *
   * Held apart from the thread's messages on purpose: those are the record, and this is text
   * on its way to being validated. Nothing here is grounded — citations come from flags that
   * do not exist until the whole reply has arrived — so it is labelled as still being written
   * rather than shown as an answer the review supports.
   */
  const [pending, setPending] = useState<{ question: string; prose: string } | null>(null);

  const conversations = useQuery({
    queryKey: ["review-conversations", reviewId],
    queryFn: () => api.reviewConversations(reviewId),
    enabled: Boolean(reviewId),
  });

  /**
   * Which thread is being read. Threads are durable and there may be many, so the newest is
   * shown by default and the rest stay reachable. `"new"` means the next question starts a
   * thread: an empty conversation is a record that then has to be explained in a listing, so
   * one is created when there is finally something to put in it.
   */
  const threads = conversations.data || [];
  const [threadId, setThreadId] = useState<string | "new" | null>(null);
  const conversation =
    threadId === "new"
      ? undefined
      : threads.find((item) => item.conversation_id === threadId) || threads[0];
  const messages = conversation?.messages || [];

  /**
   * Keep the newest exchange in view inside the log's own scroller.
   *
   * The list runs oldest to newest and the window onto it is small, so without this a new
   * answer lands below the fold of that window and the reader is left looking at a question
   * they asked three turns ago. It follows the arriving prose too, so a streamed answer stays
   * visible as it is written rather than growing downwards out of sight.
   */
  const logRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const list = logRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, pending?.prose, open]);

  /**
   * Focus moves in when the panel opens and back to whatever opened it when it closes.
   *
   * Deliberately not a focus trap. The panel is not modal — the whole point is to read the
   * ledger while asking about it — so Tab leads out of the panel and into the page, the way
   * it would from any other region. The drawer's own mount and unmount focus are both waved
   * off below, because "the input" and "whatever opened it" are more specific answers than
   * the primitive's.
   */
  const inputRef = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    opener.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    inputRef.current?.focus();
    const returnTo = opener.current;
    return () => returnTo?.focus();
  }, [open]);

  const ask = useMutation({
    mutationFn: async (text: string) => {
      // Created on first use rather than alongside the review: a conversation with no
      // questions in it is an empty record that then has to be explained in a listing.
      const target = conversation ?? (await api.createReviewConversation(reviewId));
      if (!target.conversation_id) {
        throw new Error("The workspace returned a conversation without an identifier.");
      }
      // Streamed, so the answer reads as it is written. `pending` is only ever what the
      // fragments have built — never the record — and is dropped the moment the appended
      // message arrives, which is what a re-read of this thread will show.
      setPending({ question: text, prose: "" });
      const message = await api.streamReviewQuestion(
        target.conversation_id,
        text,
        (fragment) =>
          setPending((current) =>
            current ? { ...current, prose: current.prose + fragment } : current,
          ),
      );
      return { message, target };
    },
    onSuccess: async ({ target }) => {
      setQuestion("");
      // A question asked into a new thread lands in that thread, not back in the newest.
      setThreadId(target.conversation_id || null);
      await client.invalidateQueries({
        queryKey: ["review-conversations", reviewId],
      });
      // Cleared after the history has been refetched, so the answer never blinks out of
      // existence between the preview going and the stored message arriving.
      setPending(null);
    },
    // A failed turn is appended as a failure, so the log below is where it shows. The
    // half-written prose goes: it was on its way to being checked and did not pass.
    onError: () => setPending(null),
  });

  return (
    <Sheet
      open={open}
      // Non-modal: no backdrop, no focus trap, and the page underneath keeps its pointer
      // events. Escape still dismisses, which is the drawer's own doing.
      modal={false}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <SheetContent
        overlay={false}
        showCloseButton={false}
        // Below the chrome bar rather than over it, as a margin rather than a `top`: the
        // drawer's own `inset-y-0` is written with an attribute selector, and a margin is
        // the one way to move it that does not have to outrank that.
        className={cn(
          "mt-12 flex flex-col gap-0 overflow-visible bg-chrome backdrop-blur-[var(--chrome-blur)] p-0 text-ink shadow-float",
          "z-30 data-[side=right]:h-auto",
          // The one deliberate change to this page's design: 360px read grounded answers
          // through a slot, and every grounded answer carries an excerpt of the reader's
          // own code. The page gives back exactly this much, from the same measurement.
          "data-[side=right]:w-[var(--ask-panel-width)]",
          // Too narrow to hold a ledger beside it, so it stops pretending to be beside one.
          "max-[860px]:data-[side=right]:border-l-0",
        )}
        // Clicking outside must not dismiss it. The ledger behind is the thing being asked
        // about, and a panel that closed when you reached for its subject would be modal
        // in everything but the backdrop.
        onInteractOutside={(event) => event.preventDefault()}
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
        // No standing description to point at, and a dangling reference reads worse to a
        // screen reader than none at all.
        aria-describedby={undefined}
      >
        <div className="flex items-center justify-between gap-2 border-b border-rule px-5 py-3">
          <SheetTitle className="text-ui tracking-normal">Ask about this review</SheetTitle>
          <Button
            type="button"
            size="icon"
            aria-label="Close the question panel"
            onClick={onClose}
          >
            <X size={15} aria-hidden />
          </Button>
        </div>

        {/* Threads are durable, so they are worth returning to. Each is labelled by its
            first question rather than by its title: every thread on one review would
            otherwise carry the same generated name. */}
        {threads.length > 0 || threadId === "new" ? (
          <div
            data-slot="ask-threads"
            className="flex flex-wrap gap-1 border-b border-rule-soft px-5 py-3"
            role="group"
            aria-label="Question threads"
          >
            {/* Oldest first, though the listing arrives newest first: a thread should not
                move along the row every time another one is started. The newest is still
                what opens by default — that is the one you came back to. */}
            {[...threads].reverse().map((thread) => (
              <button
                key={thread.conversation_id}
                type="button"
                className={threadPill}
                aria-pressed={conversation?.conversation_id === thread.conversation_id}
                onClick={() => setThreadId(thread.conversation_id || null)}
                title={thread.messages?.[0]?.question || thread.title}
              >
                {/* The label needs its own box: an ellipsis cannot form on a flex container. */}
                <span className="min-w-0 overflow-hidden text-ellipsis">
                  {thread.messages?.[0]?.question || thread.title}
                </span>
              </button>
            ))}
            <button
              type="button"
              className={threadPill}
              aria-pressed={threadId === "new"}
              onClick={() => setThreadId("new")}
            >
              <Plus size={12} aria-hidden /> New thread
            </button>
          </div>
        ) : null}

        {/* The only part that scrolls. `min-h-0` is what lets it shrink inside the column —
            a flex item's automatic minimum is its content, so without it a long thread
            pushes the input off the bottom instead of scrolling.

            `minmax(0,1fr)` on both levels, not `1fr`. A grid track's automatic minimum is
            its content, so an answer carrying a code excerpt — which every grounded answer
            does — sized the track to the widest line in the file and painted the whole
            thread out through the right edge of the panel. The track is bounded by the
            panel instead, and the `pre` inside scrolls sideways on its own. */}
        <ol
          data-slot="ask-log"
          className="m-0 grid min-h-0 flex-auto list-none grid-cols-[minmax(0,1fr)] content-start gap-2 overflow-y-auto p-3"
          ref={logRef}
        >
          {messages.length === 0 && !pending ? (
            <li className="text-meta leading-[1.55] text-ink-3">
              Ask about a boundary, a policy or a verdict. Answers are grounded on this
              review's own findings and say when they are not.
            </li>
          ) : null}
          {messages.map((message) => (
            <li key={message.message_id} className="grid grid-cols-[minmax(0,1fr)] gap-1">
              <p className={asked}>{message.question}</p>
              {message.answer ? (
                <div data-slot="answer" className={answered}>
                  <AnswerProse text={message.answer.answer} />
                  {/* The code the answer rests on, rendered from the file rather than retyped
                      into the answer. §12.0: where the application already holds a value, a
                      model reproducing it can only produce a second copy that disagrees —
                      which is what "chelsine" for "chelsie" was. Marking the boundary is how
                      the stage puts these lines on screen. */}
                  {(message.answer.supporting_references || []).map((reference) => (
                    <FindingSource key={reference} reviewId={reviewId} reference={reference} />
                  ))}
                  {(message.answer.supporting_references || []).length > 0 ? (
                    <p data-slot="grounding" className={grounding}>
                      Grounded on {(message.answer.supporting_references || []).join(", ")}
                    </p>
                  ) : (
                    <p data-slot="grounding" className={cn(grounding, "text-material")}>
                      Not grounded on any reviewed boundary
                    </p>
                  )}
                </div>
              ) : (
                <p className={cn(bubble, "justify-self-start text-danger")}>
                  {message.failure}
                </p>
              )}
            </li>
          ))}
          {/* The turn in flight. `aria-live` so the answer is read as it arrives rather than
              announced once at the end; `aria-busy` so a screen reader is told this is
              unfinished, which is the same thing the caption below says in text. */}
          {pending ? (
            <li
              className="grid grid-cols-[minmax(0,1fr)] gap-1"
              aria-live="polite"
              aria-busy="true"
            >
              <p className={asked}>{pending.question}</p>
              {pending.prose ? (
                <div data-slot="answer" className={answered}>
                  <AnswerProse text={pending.prose} />
                  {/* Not "not grounded" — nothing is settled yet, and a grounding line here
                      would be a claim about an answer that is still being written. The
                      arriving words are already the progress indicator, so nothing spins. */}
                  <p className={cn(grounding, "italic")}>Still being written</p>
                </div>
              ) : (
                <p className={cn(answered, "italic text-ink-3")}>Thinking…</p>
              )}
            </li>
          ) : null}
        </ol>

        {ask.isError ? (
          <div className="px-3 [&_[data-slot=error-strip]]:mt-0 [&_[data-slot=error-strip]]:mb-2">
            <ErrorPanel error={ask.error} />
          </div>
        ) : null}

        <form
          className="flex flex-none gap-2 border-t border-rule px-5 py-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (question.trim()) ask.mutate(question.trim());
          }}
        >
          {/* Stretched rather than sized: the row's height is set by the button that
              commits, and a field that stopped short of it would read as the shorter half
              of a pair. */}
          <Input
            ref={inputRef}
            type="text"
            className="h-auto min-w-0 flex-1 px-3 text-meta"
            placeholder="Ask about this review…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            disabled={ask.isPending}
            aria-label="Question about this review"
          />
          <Button
            type="submit"
            variant="primary"
            disabled={ask.isPending || !question.trim()}
          >
            {ask.isPending ? (
              "Thinking…"
            ) : (
              <>
                Ask <CornerDownLeft size={14} aria-hidden />
              </>
            )}
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
