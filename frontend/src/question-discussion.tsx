import { Sparkles } from "lucide-react";

import { AiChatIcon } from "./ai-icon";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { api } from "./api";
import { ErrorPanel } from "./components";
import { AnswerProse } from "./markdown";
import { DISCUSSION_DRAFTS, useQuestionDrafts } from "./question-drafts";
import type { OpenQuestion, ReviewConversation } from "./types";

/**
 * Talking about one open question with the advisor that asked it.
 *
 * Its own surface rather than a mode of the review conversation, because it runs at the one
 * moment that one refuses to: while the review is still waiting. A reader who does not
 * understand what is being asked has no way forward at all — the question is the whole of
 * what stands between them and a result — and telling them to answer it before they may
 * ask about it is the adoption tax elicitation exists to remove (master plan §6C.5).
 *
 * What makes that safe is scope. The stage behind this is shown the boundaries this
 * question cites and no others, so the provisional verdicts the page is withholding are not
 * in its input. It is not a way to read the held set through a smaller window.
 *
 * It may help the reader reach an answer and it may offer a phrasing for one. It never
 * records anything: a suggestion arrives as its own field, appears beside a button, and
 * what that button fills is the answer box — editable, and still facing the whole preview
 * before any of it becomes a case revision (§6C.4, invariant 25).
 */

export function QuestionDiscussion({
  reviewId,
  question,
  onAdopt,
  disabled,
}: {
  reviewId: string;
  question: OpenQuestion;
  /** Puts a suggested phrasing into the answer box. Called only by the reader's own click. */
  onAdopt: (text: string) => void;
  disabled: boolean;
}) {
  const client = useQueryClient();
  // Kept across a reload for the same reason the answer above it is (`question-drafts`): what
  // is in this box is the reader's own account of what they do not understand about their own
  // project, and it is often longer than the answer it is meant to unblock. The mechanism is
  // the one the answers use, under its own key — a question *about* an answer is not an answer,
  // and the two must never be read back into the same box.
  const [drafts, setDrafts] = useQuestionDrafts(DISCUSSION_DRAFTS, reviewId);
  const asked = drafts[question.reference] ?? "";
  const setAsked = (text: string) =>
    setDrafts((existing) => ({ ...existing, [question.reference]: text }));
  // Open where there is something restored to show. A draft put back into a collapsed panel is
  // the same loss as no draft at all: the reader sees an unanswered question and a closed
  // affordance, and has no reason to believe their half-written question is anywhere.
  const [open, setOpen] = useState(() => Boolean(asked));
  const [pending, setPending] = useState<{ asked: string; prose: string } | null>(null);

  // Every conversation this review holds, filtered to the ones about this question. Listed
  // rather than tracked locally so a reader who reloads the page still has what they said:
  // the thread is a stored record, not something this component is remembering.
  const conversations = useQuery({
    queryKey: ["review-conversations", reviewId],
    queryFn: () => api.reviewConversations(reviewId),
    enabled: Boolean(reviewId) && open,
  });
  const thread: ReviewConversation | undefined = (conversations.data ?? []).find(
    (item) => item.question_reference === question.reference,
  );

  const ask = useMutation({
    mutationFn: async (text: string) => {
      // Created on first use, and pinned to this question. A thread opened for every
      // question the moment the page rendered would be five empty records to explain.
      const target =
        thread ??
        (await api.createReviewConversation(reviewId, undefined, question.reference));
      if (!target.conversation_id) {
        throw new Error("The workspace returned a conversation without an identifier.");
      }
      setPending({ asked: text, prose: "" });
      await api.streamReviewQuestion(target.conversation_id, text, (fragment) =>
        setPending((current) =>
          current ? { ...current, prose: current.prose + fragment } : current,
        ),
      );
    },
    onSuccess: async () => {
      setAsked("");
      await client.invalidateQueries({ queryKey: ["review-conversations", reviewId] });
      // Cleared only after the stored history is back, so the reply never blinks out
      // between the preview going and the record arriving.
      setPending(null);
    },
    // The failed turn is appended by the server as a failure, so the history below is where
    // it shows. The half-written prose goes: it was on its way to being checked.
    onError: () => setPending(null),
  });

  const messages = thread?.messages ?? [];

  if (!open) {
    return (
      // Closed by default, and the affordance names the reason someone would open it: not
      // knowing what is being asked is the ordinary case, not a failure to admit.
      <button
        type="button"
        className="mt-2 inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-ui text-accent-ink not-disabled:hover:underline disabled:cursor-default disabled:text-ink-3"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <AiChatIcon size={14} />
        {messages.length > 0
          ? `Continue discussing this question (${messages.length})`
          : "Not sure what this is asking? Discuss it"}
      </button>
    );
  }

  return (
    // Set apart from the card it sits in rather than floated into a panel of its own: it is
    // part of answering this question, and a reader who opens it has not navigated anywhere.
    <div className="mt-3 border-t border-dashed border-accent-rule pt-3">
      <p className="mb-2 max-w-[76ch] text-ui leading-[1.55] text-ink-3">
        Ask about this question — what it means, why it is being asked, what the code
        actually does. It can help you work out an answer; it cannot give one for you, and
        nothing said here reaches your case until you write it above and save it.
      </p>

      {messages.length > 0 || pending ? (
        <ol className="m-0 mb-3 grid list-none gap-3 p-0">
          {messages.map((message) => (
            <li key={message.message_id} className="grid gap-1">
              <p className={askedBubble}>{message.question}</p>
              {message.answer ? (
                <div data-slot="discussion-reply" className={reply}>
                  <AnswerProse text={message.answer.answer} />
                  {message.answer.suggested_answer ? (
                    // Marked out as an offer rather than as a result, because that is
                    // exactly what it is: nothing has been recorded, and pressing the
                    // button only fills the box above.
                    <div className="mt-2 grid gap-2 rounded-panel border border-accent-rule bg-accent-soft px-3 py-2">
                      <p className="m-0 flex items-start gap-2 text-ui leading-[1.6] text-ink-2 [&>svg]:mt-[3px] [&>svg]:flex-none [&>svg]:text-accent-ink">
                        <Sparkles size={13} aria-hidden />
                        <span>
                          From what you have said, your answer might be:{" "}
                          <em className="font-semibold not-italic text-ink">
                            {message.answer.suggested_answer}
                          </em>
                        </span>
                      </p>
                      {/* The reader's click is what makes this theirs. It fills the box
                          above rather than saving anything, and §6C.4 is explicit that the
                          substance is still the user's where their whole contribution is
                          confirming a phrasing that was suggested to them. */}
                      <Button
                        type="button"
                        className="justify-self-start text-ui"
                        disabled={disabled}
                        onClick={() => onAdopt(message.answer?.suggested_answer ?? "")}
                      >
                        Use this as my answer
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : (
                // A turn the server recorded as failed. The strip rather than a red
                // sentence, because it is the same class of thing as every other failure on
                // this page and the reader should not have to learn a second appearance for
                // it. No retry: this one is history, already stored against the thread, and
                // the box below is where a new attempt is made rather than an old one
                // rewritten.
                <ErrorPanel
                  error={
                    new Error(
                      message.failure ||
                        "The workspace recorded no answer to this and no reason.",
                    )
                  }
                />
              )}
            </li>
          ))}
          {pending ? (
            <li className="grid gap-1">
              <p className={askedBubble}>{pending.asked}</p>
              {/* Prose on its way to being checked, so it is never given a suggestion or a
                  citation — both exist only once the whole reply has been validated. */}
              <div data-slot="discussion-reply" className={reply} aria-live="polite">
                {pending.prose ? <AnswerProse text={pending.prose} /> : <span>Thinking…</span>}
              </div>
            </li>
          ) : null}
        </ol>
      ) : null}

      {/* The turn that never reached the server, as against the one above it that did. What
          was typed is still in `ask.variables` — and still in the box, which is cleared only
          on success — so asking again is one press rather than retyping the question. */}
      {ask.isError ? (
        <div className="[&_[data-slot=error-strip]]:mt-0 [&_[data-slot=error-strip]]:mb-2">
          <ErrorPanel
            error={ask.error}
            onRetry={ask.variables ? () => ask.mutate(ask.variables!) : undefined}
            retrying={ask.isPending}
            retryLabel="Ask again"
          />
        </div>
      ) : null}

      <div className="flex items-start gap-2">
        {/* Two lines, not the field's usual three: this box sits under a thread the reader
            is reading, and a taller one would push it further off the screen for every
            question asked. */}
        <Textarea
          rows={2}
          className="min-h-0 flex-1"
          value={asked}
          disabled={disabled || ask.isPending}
          placeholder="What does this question mean for my project?"
          onChange={(event) => setAsked(event.target.value)}
        />
        <Button
          type="button"
          className="text-ui"
          disabled={disabled || ask.isPending || !asked.trim()}
          onClick={() => ask.mutate(asked.trim())}
        >
          {ask.isPending ? "Asking…" : "Ask"}
        </Button>
      </div>
    </div>
  );
}

/* The reader's question and the advisor's reply, as a pair. The question is a bubble with
   the corner nearest its own side squared off; the reply is plain prose at reading width,
   because it is the thing being read rather than a message in a chat. */
const askedBubble =
  "m-0 max-w-[62ch] justify-self-start rounded-panel rounded-bl-control bg-sunken px-3 py-2 text-ui leading-[1.55] text-ink";
const reply = "max-w-[76ch] text-body leading-[1.65] text-ink-2";
