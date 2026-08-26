import type { Question, Review } from "../../api";
import { Button } from "../../ui/button";
import { ChevronDown } from "../../ui/icons";
import { ErrorNotice, Spinner } from "../../ui/states";
import { AskBox, ConversationExchange, useConversations } from "./conversation-thread";

/**
 * Somewhere to go when the question itself is the problem.
 *
 * A clarification round asks about intent the code cannot carry, and the questions are
 * written by a model reasoning about a candidate it has just judged. They land on somebody
 * who did not write the code and has not read the finding — and a question you cannot parse
 * is not a question you can answer. Until this existed the only ways out were to guess, to
 * skip, or to leave the review stopped.
 *
 * So this is an agent with the same toolbox the judgement had: the atlas, the policy corpus,
 * and the files at the revision under review. Its job is to explain — what is being asked,
 * which finding is waiting on it, and what each answer would change — and never to decide.
 * The one thing it may write is wording for the answer box, which the reviewer edits and
 * submits themselves; the contract that governs that lives in `langchain.py`.
 *
 * Closed by default and quiet about itself. Most questions are answered without it, and a
 * panel that announced itself under every question would be a model volunteering an opinion
 * on a decision the charter reserves for a person.
 */
export function QuestionHelp({
  question,
  review,
  draft,
  onDraft,
  onUseAnswer,
}: {
  question: Question;
  review: Review;
  /** What has been half-typed here, held by the page — the panel unmounts, the round does not. */
  draft: string;
  onDraft: (value: string) => void;
  /** Put wording in the answer box, and remember who wrote it. */
  onUseAnswer: (text: string, model: string) => void;
}) {
  const { conversations, current, ask } = useConversations(review, question.id);
  const messages = current?.messages ?? [];

  return (
    <details className="group mt-3 rounded-md border border-rule bg-surface-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 py-2">
        <span className="min-w-0 flex-1 text-xs font-semibold text-ink-2">
          {/* The label is the reader's own sentence, not a feature name. Somebody stuck here
              is thinking "why am I being asked this", and "Ask about this question" would
              make them work out that the two are the same thing. */}
          I do not understand this question
        </span>
        {messages.length ? (
          <span className="shrink-0 text-[11px] tabular-nums text-ink-3">
            {messages.length}
          </span>
        ) : null}
        <ChevronDown className="size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
      </summary>

      <div className="border-t border-rule px-3 py-3">
        {conversations.isLoading ? (
          <div role="status" aria-live="polite" className="flex items-center gap-2.5 text-sm text-ink-2">
            <Spinner label="" />
            Looking for what has already been asked here…
          </div>
        ) : conversations.error ? (
          <ErrorNotice
            error={conversations.error}
            title="What was already asked here could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => void conversations.refetch()}>
                Try again
              </Button>
            }
          />
        ) : null}

        {messages.length ? (
          <ol className="mb-3 grid gap-4">
            {messages.map((message, index) => (
              <li key={`${message.asked_at}-${index}`}>
                <ConversationExchange
                  message={message}
                  review={review}
                  onUseAnswer={(text) => onUseAnswer(text, message.answer.model_identity ?? "")}
                />
              </li>
            ))}
          </ol>
        ) : (
          /* Not an `EmptyState`, which is a centred block with a heading and would be half
             the panel before anything is in it. Two sentences saying what this can do and
             what it will not do — the second matters as much as the first, because an agent
             beside an answer box reads as one that will fill it in. */
          <p className="mb-3 max-w-[62ch] text-[13px] leading-6 text-ink-3">
            Ask what the question means, why the review needs it, or what each answer would
            change. It can read the code and the policies to answer you. It will not decide
            the answer — that is the part only you can give.
          </p>
        )}

        <AskBox
          label={`Ask about the question: ${question.text}`}
          placeholder="What is this actually asking?"
          pending={ask.isPending}
          value={draft}
          onChange={onDraft}
          onAsk={(text) => ask.mutate(text)}
        />

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
      </div>
    </details>
  );
}
