import { useEffect, useRef } from "react";

import type { Question, Review } from "../../api";
import { plural } from "../../lib/format";
import { Button } from "../../ui/button";
import { ChevronDown } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { Prose, plainProse } from "../../ui/prose";
import { ErrorNotice, LiveRegion, Skeleton, Spinner } from "../../ui/states";
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
  open,
  onDraft,
  onOpenChange,
  onUseAnswer,
}: {
  question: Question;
  review: Review;
  /** What has been half-typed here, held by the page — the panel unmounts, the round does not. */
  draft: string;
  /**
   * Whether the panel is open, held by the page for the same reason `draft` is.
   *
   * Open-or-closed is DOM state, and the round mounts a question's children only while its
   * row is open — so `asking` kept somebody's two half-typed sentences and the `<details>`
   * around them shut itself on every remount, which put the sentences behind a summary that
   * says nothing about them. Held rather than derived: `open={Boolean(draft) || messages.length}`
   * would re-open a panel the reader deliberately closed, every time they stepped away and
   * back, which is what "closed by default and quiet about itself" exists to prevent.
   */
  open: boolean;
  onDraft: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  /** Put wording in the answer box, and remember who wrote it. */
  onUseAnswer: (text: string, model: string) => void;
}) {
  const { conversations, current, ask } = useConversations(review, question.id);
  const messages = current?.messages ?? [];
  const landed = useRef<HTMLDivElement>(null);

  /**
   * Go to the answer when it arrives, rather than leaving it below whatever is on screen.
   *
   * An ask runs an agent over the atlas with no request timeout, so the reply lands tens of
   * seconds later and a paragraph long. `nearest` keeps a reader who is already looking at
   * the right place exactly where they are; it only moves anybody who is not.
   */
  useEffect(() => {
    if (!ask.isSuccess) return;
    landed.current?.scrollIntoView?.({ block: "nearest" });
  }, [ask.isSuccess, messages.length]);

  return (
    /* No box. Closed, this was a `rounded-md border border-rule bg-surface-2` block sitting
       6px under a column of proposed answers drawn from the same recipe, so the blocking
       question appeared to offer a last option reading "I do not understand this question" —
       which is not an answer and records nothing. The one control here that is a different
       *kind* of thing was the only one drawn the same as its neighbours. A hairline separates
       and a border belongs to something you could pick up; this is the first, so it wears a
       rule and no ground of its own. */
    <details
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
      className="group mt-4 border-t border-rule pt-3"
    >
      <summary className="-ml-2.5 flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-sm px-2.5 text-ink-2 transition hover:bg-sunken hover:text-ink">
        <span className="min-w-0 flex-1 text-xs font-semibold">
          {/* The label is the reader's own sentence, not a feature name. Somebody stuck here
              is thinking "why am I being asked this", and "Ask about this question" would
              make them work out that the two are the same thing. */}
          I do not understand this question
        </span>
        {/* The unit, not the digit. A closed panel with a history showed a bare "2", which a
            screen reader announced as "I do not understand this question 2" and which told a
            sighted reader nothing about what had been counted. The same fact is written out
            properly on the Rounds surface, with this helper. */}
        {messages.length ? (
          <span className="shrink-0 text-[11px] tabular-nums">
            {plural(messages.length, "question")} asked
          </span>
        ) : null}
        <ChevronDown className="size-4 shrink-0 transition group-open:rotate-180" />
      </summary>

      <div className="mt-1">
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

        {messages.length || ask.isPending ? (
          <>
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
              {/* The question, kept on screen while it is being answered, and the shape of the
                  answer before the answer exists. Asking used to change one thing — a 14px
                  spinner inside the button — while an agent ran a toolbox over the atlas, the
                  policy corpus and the files at the revision under review, with no request
                  timeout: the box emptied, the list stayed exactly as it was, and a paragraph
                  appeared silently tens of seconds later. The skeletons are what stop that
                  arrival being a jump. Same device as the Ask surface, which reasoned this
                  out first. */}
              {ask.isPending && ask.variables ? (
                <li aria-live="polite">
                  <div className="grid gap-2">
                    <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
                      <Label>Question</Label>
                      {/* Drawn the way `ConversationExchange` draws the same string once the
                          real exchange arrives, so the placeholder does not visibly change
                          shape when it is replaced. */}
                      <p className="mt-1 max-w-[62ch] text-sm leading-6 text-ink wrap-anywhere">
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
            {/* An anchor rather than a ref on the list, because what a reader wants brought
                into view is the end of it. */}
            <div ref={landed} aria-hidden="true" />
            <LiveRegion>
              {ask.isPending
                ? "Working out an answer to your question."
                : ask.isSuccess
                  ? "The agent answered your question."
                  : ""}
            </LiveRegion>
          </>
        ) : (
          /* Not an `EmptyState`, which is a centred block with a heading and would be half
             the panel before anything is in it. Two sentences saying what this can do and
             what it will not do — the second matters as much as the first, because an agent
             beside an answer box reads as one that will fill it in. */
          <p className="mb-3 max-w-[62ch] text-[13px] leading-6 text-ink-2">
            Ask what the question means, why the review needs it, or what each answer would
            change. It can read the code and the policies to answer you. It will not decide
            the answer — that is the part only you can give.
          </p>
        )}

        <AskBox
          // Stripped here rather than inside `AskBox`, which puts this on a textarea's
          // `aria-label`. `AskBox` is also given static labels, and a component that started
          // rewriting whatever it was handed would be doing it to strings that never came
          // from a model.
          label={`Ask about the question: ${plainProse(question.text)}`}
          placeholder="What is this actually asking?"
          pending={ask.isPending}
          value={draft}
          onChange={onDraft}
          // `mutateAsync`, so the box clears when the ask *lands* rather than when it is
          // pressed. This request has no timeout because it runs an agent, and the value used
          // to be wiped on the press — so a failure left the sentence gone from the screen
          // with only a button offering to resend the identical text. A rejection here is
          // handled: `AskBox` keeps the words, and `ask.error` below is what says so.
          onAsk={(text) => ask.mutateAsync(text)}
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
