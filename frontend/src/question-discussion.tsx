import { MessagesSquare, Sparkles } from "lucide-react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { AnswerProse } from "./markdown";
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
  const [open, setOpen] = useState(false);
  const [asked, setAsked] = useState("");
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
      <button
        type="button"
        className="discussion__open"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <MessagesSquare size={14} aria-hidden />
        {messages.length > 0
          ? `Continue discussing this question (${messages.length})`
          : "Not sure what this is asking? Discuss it"}
      </button>
    );
  }

  return (
    <div className="discussion">
      <p className="discussion__lead">
        Ask about this question — what it means, why it is being asked, what the code
        actually does. It can help you work out an answer; it cannot give one for you, and
        nothing said here reaches your case until you write it above and save it.
      </p>

      {messages.length > 0 || pending ? (
        <ol className="discussion__turns">
          {messages.map((message) => (
            <li key={message.message_id} className="discussion__turn">
              <p className="discussion__asked">{message.question}</p>
              {message.answer ? (
                <div className="discussion__replied">
                  <AnswerProse text={message.answer.answer} />
                  {message.answer.suggested_answer ? (
                    <div className="discussion__suggestion">
                      <p>
                        <Sparkles size={13} aria-hidden />
                        <span>
                          From what you have said, your answer might be:{" "}
                          <em>{message.answer.suggested_answer}</em>
                        </span>
                      </p>
                      {/* The reader's click is what makes this theirs. It fills the box
                          above rather than saving anything, and §6C.4 is explicit that the
                          substance is still the user's where their whole contribution is
                          confirming a phrasing that was suggested to them. */}
                      <button
                        type="button"
                        className="button discussion__adopt"
                        disabled={disabled}
                        onClick={() => onAdopt(message.answer?.suggested_answer ?? "")}
                      >
                        Use this as my answer
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="discussion__failed">{message.failure}</p>
              )}
            </li>
          ))}
          {pending ? (
            <li className="discussion__turn">
              <p className="discussion__asked">{pending.asked}</p>
              {/* Prose on its way to being checked, so it is never given a suggestion or a
                  citation — both exist only once the whole reply has been validated. */}
              <div className="discussion__replied" aria-live="polite">
                {pending.prose ? <AnswerProse text={pending.prose} /> : <span>Thinking…</span>}
              </div>
            </li>
          ) : null}
        </ol>
      ) : null}

      {ask.isError ? (
        <p className="discussion__error">
          {ask.error instanceof Error
            ? ask.error.message
            : "That could not be asked just now."}
        </p>
      ) : null}

      <div className="discussion__compose">
        <textarea
          rows={2}
          value={asked}
          disabled={disabled || ask.isPending}
          placeholder="What does this question mean for my project?"
          onChange={(event) => setAsked(event.target.value)}
        />
        <button
          type="button"
          className="button"
          disabled={disabled || ask.isPending || !asked.trim()}
          onClick={() => ask.mutate(asked.trim())}
        >
          {ask.isPending ? "Asking…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
