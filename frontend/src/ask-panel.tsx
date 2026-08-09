import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, Plus, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { api } from "./api";
import {
  applyAskPanelWidth,
  askPanelIsResizable,
  askPanelWidthFromPointer,
  clampAskPanelWidth,
  maxAskPanelWidth,
  MIN_ASK_PANEL_WIDTH,
  saveAskPanelWidth,
  storedAskPanelWidth,
} from "./ask-panel-width";
import { ErrorPanel } from "./components";
import { FindingSource } from "./finding-source";
import { InvestigationDisclosure } from "./investigation-disclosure";
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

/* The grab strip on the panel's left edge.
   Six pixels wide and paints nothing until it is pointed at: the edge is already drawn by the
   drawer's own border, and a second visible rule there would read as a divider inside the panel
   rather than as its boundary. Wider than it looks by way of `before`, because a 6px target is
   a fair mouse target and a poor one for anybody whose hand is not steady.
   `inset-y-0` and `-left-px` so it straddles the border rather than sitting inside the padding,
   which is where a reader's cursor actually goes looking for it. */
const resizeHandle = cn(
  "absolute inset-y-0 -left-px z-10 w-1.5 cursor-col-resize touch-none border-0 bg-transparent p-0",
  "before:absolute before:inset-y-0 before:-left-1 before:-right-1 before:content-['']",
  "after:absolute after:inset-y-0 after:left-0 after:w-px after:bg-transparent after:content-['']",
  "hover:after:bg-accent-rule focus-visible:after:bg-accent-ink",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
);

/** How far one arrow press moves the edge, and how far one with a modifier held moves it. */
const KEYBOARD_STEP = 16;
const KEYBOARD_LEAP = 96;

/**
 * The drag that sets the panel's width, and the reader's stored preference for it.
 *
 * Written as a hook beside the panel rather than in `ask-panel-width.ts` because it is all
 * effect: the arithmetic, the storage and the decision about which custom property to write are
 * pure and live there, tested without a pointer. What is left here is the two things only a
 * component can do — hold the pointer capture and keep a rendered value in step with it.
 *
 * The width is applied to `document.documentElement`, not to the panel. Two rules read the token
 * and the second one is the padding `<main>` reserves for the drawer, so a width set on the
 * panel would widen the drawer over the ledger it is supposed to sit beside. That the page
 * moves with the drag is not a side effect; it is the reason the token exists.
 */
function useAskPanelWidth(enabled: boolean) {
  /** The settled width, held only so the handle can report it to a screen reader. */
  const [width, setWidth] = useState<number | null>(null);
  const dragging = useRef<number | null>(null);
  /** Where the edge is mid-drag, in a ref because a re-render per frame is what it avoids. */
  const live = useRef<number | null>(null);

  // Restored once, on mount, before anything is measured. Writing it here rather than in a
  // layout effect on the panel means the room is already reserved for the drawer on the first
  // paint of a review whose reader has asked before.
  useEffect(() => {
    const saved = storedAskPanelWidth(window.localStorage);
    if (saved === null) return;
    const fitted = clampAskPanelWidth(saved, window.innerWidth);
    applyAskPanelWidth(document.documentElement, fitted);
    setWidth(fitted);
  }, []);

  /**
   * A window narrower than the panel's own minimum is a window the reader has resized under a
   * width they chose earlier. The choice is kept in storage and only the applied value is
   * refitted, so widening the window again gives back what they picked rather than the ceiling
   * it was clipped to.
   */
  useEffect(() => {
    const refit = () => {
      setWidth((current) => {
        if (current === null) return null;
        const fitted = clampAskPanelWidth(current, window.innerWidth);
        applyAskPanelWidth(document.documentElement, fitted);
        return fitted;
      });
    };
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
  }, []);

  /**
   * The width, applied and remembered. Everything except a drag in progress goes through here.
   *
   * A drag does not, and the split is the whole of why `live` exists below: this writes storage
   * and sets React state, and a pointer that fires sixty times a second would mean sixty
   * synchronous `localStorage` writes and sixty re-renders of a conversation — to move an edge
   * that a single custom property already moves on its own.
   */
  const set = useCallback((next: number) => {
    applyAskPanelWidth(document.documentElement, next);
    saveAskPanelWidth(window.localStorage, next);
    setWidth(next);
  }, []);

  /** Back to the responsive default, and the stored preference goes with it. */
  const reset = useCallback(() => {
    applyAskPanelWidth(document.documentElement, null);
    saveAskPanelWidth(window.localStorage, null);
    setWidth(null);
  }, []);

  const begin = (event: ReactPointerEvent<HTMLElement>) => {
    if (!enabled || event.button !== 0) return;
    // The handle keeps the pointer for the whole gesture, so the drag survives the cursor
    // leaving the strip — which it does immediately, because the strip is what is moving.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragging.current = event.pointerId;
    // Suppressed for the length of the drag only. Without it the gesture selects the
    // conversation behind the handle, and the reader ends a resize with half a thread
    // highlighted; a permanent `select-none` on the panel would cost them copying an answer.
    document.body.style.userSelect = "none";
    event.preventDefault();
  };

  /**
   * Every frame of the drag writes the custom property and nothing else.
   *
   * That property is all the movement needs: the drawer's width and the room `<main>` reserves
   * for it both read the token it feeds, so the browser reflows both from one declaration without React
   * being involved. State and storage wait for the gesture to finish — the value a screen reader
   * is told and the value kept for next time are both about where the edge came to rest, not
   * about where it passed through.
   */
  const move = (event: ReactPointerEvent<HTMLElement>) => {
    if (dragging.current !== event.pointerId) return;
    const next = askPanelWidthFromPointer(event.clientX, window.innerWidth);
    live.current = next;
    applyAskPanelWidth(document.documentElement, next);
  };

  const end = (event: ReactPointerEvent<HTMLElement>) => {
    if (dragging.current !== event.pointerId) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    dragging.current = null;
    document.body.style.removeProperty("user-select");
    // A press with no movement is not a resize, so it stores nothing — which is what keeps a
    // double-click on the handle a reset rather than a reset immediately overwritten by the
    // width the second press happened to land on.
    if (live.current !== null) set(live.current);
    live.current = null;
  };

  /**
   * The same resize from the keyboard, because a drag is not an interaction everyone has.
   *
   * Left widens and right narrows: the handle is the thing with focus, so the arrow that matches
   * where *it* travels is the one that will not surprise anybody, even though the panel grows in
   * the opposite direction. Shift takes bigger steps and Home and End go to the two limits.
   *
   * Escape is deliberately not bound. It closes the panel, which is the drawer's own behaviour
   * and the one thing a reader can be sure of anywhere inside it; a handle that swallowed it to
   * mean "undo my resize" would make the key mean two things a few pixels apart.
   *
   * Where nothing has been chosen yet the first press starts from what the panel currently
   * measures, read off the element the handle is positioned against — which is the panel, since
   * the handle is absolute inside it. The alternative is parsing the computed token, and what
   * `getComputedStyle` hands back for a custom property is the unresolved `var(…, clamp(…))`
   * rather than a length.
   */
  const key = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!enabled) return;
    const panel = event.currentTarget.offsetParent;
    const measured = panel instanceof HTMLElement ? panel.offsetWidth : MIN_ASK_PANEL_WIDTH;
    const from = width ?? clampAskPanelWidth(measured, window.innerWidth);
    const step = event.shiftKey ? KEYBOARD_LEAP : KEYBOARD_STEP;
    const moves: Record<string, number> = {
      ArrowLeft: from + step,
      ArrowRight: from - step,
      Home: maxAskPanelWidth(window.innerWidth),
      End: MIN_ASK_PANEL_WIDTH,
    };
    const next = moves[event.key];
    if (next === undefined) return;
    event.preventDefault();
    set(clampAskPanelWidth(next, window.innerWidth));
  };

  return { width, begin, move, end, key, reset };
}

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
  /**
   * The window's width, tracked so two things derived from it cannot go stale.
   *
   * The first is whether the handle is offered at all. The sheet hides it below the same
   * measurement, which is what a reader sees; this is what stops the logic running there — a
   * `display: none` strip is unreachable by mouse and would still leave a focused handle
   * answering arrow keys, writing a width the narrow-window rule then correctly ignores, which
   * is a control quietly doing nothing.
   *
   * The second is `aria-valuemax`, and it is why this is a width rather than the boolean it
   * started as: the ceiling is a fraction of the window, so a boolean only re-rendered when the
   * threshold was crossed and left a screen reader being told the maximum for whatever size the
   * window happened to be when the panel opened.
   */
  const [viewport, setViewport] = useState(() => window.innerWidth);
  useEffect(() => {
    const measure = () => setViewport(window.innerWidth);
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  const resizable = askPanelIsResizable(viewport);
  const panelWidth = useAskPanelWidth(resizable);
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
        {/* The panel's own edge, made draggable.
            A `separator` with an orientation and a value, which is what a resizer between two
            regions is — it separates the conversation from the review, and its position is the
            fact a screen reader needs. Not a `slider`: nothing here is a value being chosen from
            a range for its own sake, and announcing "480 of 1280" as a setting would describe the
            implementation rather than what moved.

            `aria-valuenow` is absent until the reader has set one, because before that the width
            is a responsive expression rather than a number, and reporting the number it currently
            computes to would claim a precision that is not there. */}
        {resizable ? (
          <div
            data-slot="ask-resize"
            className={resizeHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the question panel"
            aria-valuemin={MIN_ASK_PANEL_WIDTH}
            aria-valuemax={maxAskPanelWidth(viewport)}
            aria-valuenow={panelWidth.width ?? undefined}
            tabIndex={0}
            onPointerDown={panelWidth.begin}
            onPointerMove={panelWidth.move}
            onPointerUp={panelWidth.end}
            onPointerCancel={panelWidth.end}
            onKeyDown={panelWidth.key}
            // Back to the responsive default. On the handle rather than as a button beside it:
            // the gesture that undoes a drag belongs on the thing that was dragged, and a reset
            // control sitting in the header would be chrome for something most readers never do.
            onDoubleClick={panelWidth.reset}
            title="Drag to resize, or double-click to reset"
          />
        ) : null}

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
                  {/* What this reply looked up before it was composed — the same record a
                      run keeps, scoped to one answer. Under the prose rather than above
                      it: the answer is what was asked for, and the checking is its
                      warrant. */}
                  {message.investigation ? (
                    <InvestigationDisclosure investigation={message.investigation} />
                  ) : null}
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
            {/* The question is still in `ask.variables` after the turn failed, so asking
                again is one press rather than retyping what was already typed. The box
                below was cleared only on success, so the two never disagree. */}
            <ErrorPanel
              error={ask.error}
              onRetry={ask.variables ? () => ask.mutate(ask.variables!) : undefined}
              retrying={ask.isPending}
              retryLabel="Ask again"
            />
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
