import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { shortId } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Textarea } from "../../ui/field";
import { CheckIcon, ChevronDown } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { ModelProse, Prose, plainProse } from "../../ui/prose";
import { Spinner } from "../../ui/states";
import { Attribution } from "./finding-detail";
import { InvestigationTranscript, investigationSummary } from "./investigation";

/**
 * One exchange, drawn the same way wherever it is read.
 *
 * Two surfaces hold these now — the Ask tab, over the whole review, and the panel under a
 * clarification question the review is waiting on — and they were never going to stay the
 * same drawn twice. What a reader has to be able to do in both is the same thing: read the
 * answer, open what it looked up, and follow a citation to the finding it rests on.
 */
export function ConversationExchange({
  message,
  review,
  onOpen,
  onUseAnswer,
}: {
  message: ReviewConversation["messages"][number];
  review: Review;
  onOpen?: (candidateId: string) => void;
  /**
   * What "use this wording" does, where the surface has somewhere to put it. Absent on the
   * Ask tab, which has no answer box — and absent is why the control is not drawn there
   * rather than drawn and inert.
   */
  onUseAnswer?: (text: string) => void;
}) {
  const suggested = message.answer.suggested_answer?.trim();
  const [taken, setTaken] = useState(false);
  return (
    <div className="grid gap-2">
      <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
        <Label>Question</Label>
        {/* `wrap-anywhere` on both halves: a question is regularly a qualified name with a
            few words around it, and an answer quotes paths back. One token wider than a
            phone and nothing else in the panel can help.

            `max-w-[62ch]` because nothing in this exchange capped its measure, and on the Ask
            surface it is drawn inside the page's whole 76rem column — about 150 characters a
            line, the longest prose in the product at the loosest measure. */}
        {/* Through `Prose` even though these are the reader's own typed words, not the
            model's. It is the top half of a pair whose bottom half is rendered, and rendering
            one and not the other is the visible inconsistency — a reviewer who types a
            backtick around a name means it the way the model does. */}
        <p className="mt-1 max-w-[62ch] text-sm leading-6 text-ink wrap-anywhere">
          <Prose>{message.question}</Prose>
        </p>
      </div>
      {/* `bg-sunken`, not `bg-sunken/50`: half of `#ebebeb` over the panel composites to a
          grey on no ramp in light and to something else again in dark. This is a quiet inset,
          which is the job `--sunken` is named for, in both themes. */}
      <div className="rounded-md border border-rule bg-sunken px-3 py-2.5">
        {/* The model's voice, named and set at the reading size — which is the design system's
            central claim and the one place in the product that ignored it. This was 14px of
            `--ink-2` under a generic 10px "Agent", so a reader could not tell which model had
            answered and the paragraph read as chrome rather than as the judged voice. The
            identity is in the payload and is already trusted enough to be stamped onto the
            answer the reviewer submits, and `Attribution` is the line the finding and the
            report already use for exactly this. */}
        <Attribution voice="Answered" by={message.answer.model_identity || "model not recorded"} />
        {/* Through `ModelProse`, which is where the reading size now lives. This block had the
            same claim on it as the two above — the model's voice, named and set at the reading
            size — and set it at `62ch` against the finding's `58ch` and the synopsis's `46ch`,
            with no sentence split on any answer however long. An answer here is the same kind
            of paragraph a judgement is, from the same models under the same "prose" contract,
            so it is drawn the same way and the measure is argued once.

            The contract also asks the model, in as many words, to "name one by its backticked
            participant, the way the listing does", and the listing it is fed on the way in
            backticks every line. So a span here is guaranteed rather than incidental, and
            `ModelProse` renders it. */}
        <ModelProse className="mt-1">{message.answer.text}</ModelProse>

        {suggested && onUseAnswer ? (
          /* Words offered for the reader's own box, and nothing more than offered.
             Deliberately below the answer rather than beside it: what the agent worked out
             is the thing they came for, and a draft presented first would read as the
             conclusion with the reasoning as footnotes.

             It is also why the button says "put this in my answer" rather than "accept".
             Nothing here submits: the text lands in the box, they change it or delete it,
             and they submit the round. */
          <div className="mt-2.5 border-t border-rule pt-2.5">
            <Label>Wording you could use</Label>
            {/* `text-ink-2`, under an answer that now carries the stronger ink. Placement
                already obeyed the argument above — the reasoning is what the reader came for
                — and the weights reversed it: the explanation was secondary and the
                ready-made sentence beneath it was full ink, so the eye landed on the words to
                submit before the reasons for them, under a panel whose own doc says the agent
                must never decide the answer. */}
            {/* Same model, same call, same contract as the answer above — and deliberately
                not the same treatment, which is the correction this comment carries. It said
                "so the same treatment" while setting 14px `--ink-2` at `62ch` beside a
                `ModelProse` block at 16px full ink, so it described the one thing it did not
                do, in a file where the block above it had just been converged.

                It stays subordinate on the argument the comment directly above already makes:
                the reasoning is what the reader came for and the ready-made sentence is
                offered under it, so promoting this to the reading size and full ink puts the
                eye on the words to submit before the reasons for them — the exact inversion
                that was corrected here. There is a second reason it cannot go through
                `ModelProse` even if somebody wanted it to: the reading size is the one thing
                that marks the model's voice, and two blocks at it inside one bubble say the
                answer and the draft are two utterances rather than one answer and an offer
                taken out of it. `ui/design-system.test.ts` holds that line for the whole tree.

                What is the same is the rendering, and it always was: `Prose` draws the quoted
                names, because the raw string is what the button below writes into the
                reviewer's own box and a delimiter left standing here travels into the record
                as part of their answer. `62ch` is 14px's measure in this file, shared with the
                reviewer's own question above — the pairing this block belongs to. */}
            <p className="mt-1 max-w-[62ch] whitespace-pre-line text-sm leading-6 text-ink-2 wrap-anywhere">
              <Prose>{suggested}</Prose>
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {/* The tick is the whole confirmation, and it is the device `CopyButton` already
                  uses. The press writes into a box that is above this in the DOM and does not
                  yet exist, so the only thing that visibly happened was the panel dropping a
                  hundred pixels; the control the reader was looking at said nothing at all. */}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  onUseAnswer(suggested);
                  setTaken(true);
                  window.setTimeout(() => setTaken(false), 1500);
                }}
              >
                {taken ? (
                  <>
                    <CheckIcon aria-hidden="true" className="size-3.5" /> In your answer box
                  </>
                ) : (
                  "Put this in my answer"
                )}
              </Button>
              <span className="text-[11px] leading-5 text-ink-3">
                It goes in the box for you to change. Nothing is submitted until you do it.
              </span>
            </div>
          </div>
        ) : null}

        {message.answer.investigation ? (
          /* No bleed and no full-width rule: this sits inside a bubble whose walls one
             would burst through. Closed, because the answer is what the reader came for and
             this is the working behind it. */
          <details className="group mt-2 border-t border-rule pt-2">
            <summary className="flex min-h-11 list-none items-center gap-2">
              {/* `as="span"`, because `<summary>` takes phrasing content and `Label` renders a
                  `div` by default — which is the invalid nesting its `as` prop exists for. */}
              <Label as="span">Looked up</Label>
              <span className="min-w-0 flex-1 font-mono text-[11px] leading-5 text-ink-3 [overflow-wrap:anywhere]">
                {investigationSummary(message.answer.investigation)}
              </span>
              <ChevronDown className="size-4 shrink-0 text-ink-3 transition group-open:rotate-180" />
            </summary>
            <div className="mt-2">
              <InvestigationTranscript investigation={message.answer.investigation} />
            </div>
          </details>
        ) : null}

        {message.answer.supporting_candidate_ids.length ? (
          <div className="mt-2 border-t border-rule pt-2">
            {/* The charter asks every claim to say where it came from, and a row of unheaded
                chips under a paragraph does not say what it is. */}
            <Label>Answered from these findings</Label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {message.answer.supporting_candidate_ids.map((id) => {
                const finding = review.findings.find((item) => item.candidate.id === id);
                // An answer is told where the evidence sits but never shown the code there,
                // so a citation is the way to it rather than a footnote. `text-left` because
                // a button centres its text by default, and a citation is a whole sentence —
                // on a phone it wrapped to four centred lines, which reads as a pull quote
                // rather than as a link.
                if (finding && onOpen) {
                  return (
                    <button
                      key={id}
                      type="button"
                      title={plainProse(finding.candidate.summary)}
                      onClick={() => onOpen(id)}
                      className="max-w-full text-left"
                    >
                      {/* `bare`, and `Tag` is why: it already draws `rounded-xs border
                          border-rule bg-surface-2 px-2 py-0.5`, so a chip inside it is a box
                          inside a box with two hairlines, at 12px. The mono face is the half
                          that carries the meaning and the tag is already providing the other
                          half. The `title` beside it is a string, so it gets the delimiters
                          taken off rather than drawn — and the two must say the same words. */}
                      <Tag className="transition hover:border-rule-strong hover:text-ink">
                        <Prose bare>{finding.candidate.summary}</Prose>
                      </Tag>
                    </button>
                  );
                }
                // The same citation with nothing to open, so it is drawn the same way: a
                // citation that changed shape depending on whether it was clickable would
                // read as two different kinds of thing.
                if (finding)
                  return (
                    <Tag key={id}>
                      <Prose bare>{finding.candidate.summary}</Prose>
                    </Tag>
                  );
                // No finding to name it with. A truncated id standing in as a label reads as
                // the candidate's name, which it is not — so the chip says what happened and
                // keeps the id in mono, where a machine string belongs.
                return (
                  <Tag key={id} className="gap-1.5">
                    Cited candidate, not in this review
                    <span className="font-mono text-[11px] text-ink-3">{shortId(id, 12)}</span>
                  </Tag>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The threads held against one review, and the one asking is done in.
 *
 * `questionId` picks which family: `""` is the Ask tab's, over the review as a whole, and a
 * question id is the panel under that question. They are separated here rather than at the
 * request, because the listing is one request per review and splitting it into two would
 * make the Ask tab reload every time somebody asked about a question.
 */
export function useConversations(review: Review, questionId = "") {
  const client = useQueryClient();
  const conversations = useQuery({
    queryKey: ["conversations", review.id],
    queryFn: () => api.conversations(review.id),
  });
  const [conversationId, setConversationId] = useState<string | null>(null);

  const threads = (conversations.data ?? []).filter(
    (item) => (item.question_id ?? "") === questionId,
  );
  const current =
    threads.find((item) => item.id === conversationId) ?? threads[threads.length - 1] ?? null;

  useEffect(() => {
    if (conversationId && !threads.some((item) => item.id === conversationId)) {
      setConversationId(null);
    }
  }, [conversationId, threads]);

  const ask = useMutation({
    mutationFn: async (text: string) => {
      const id = current?.id || (await api.createConversation(review.id, questionId)).id;
      setConversationId(id);
      return api.ask(id, text);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["conversations", review.id] });
    },
  });

  return { conversations, threads, current, setConversationId, ask };
}

/**
 * The box a question is typed into, with the button that sends it.
 *
 * Shared for the same reason the exchange is: two surfaces, one gesture.
 *
 * A textarea, not an input. The placeholder invites a sentence and a real question is two or
 * three lines of one, so a one-line field meant the words scrolled out of their own box while
 * being typed and could not be re-read before they were sent — at 1440 the same element was a
 * 1060px single line, which is the worst shape a sentence can be given. The button moved under
 * the box with it: beside a growing field it would have to sit somewhere arbitrary in the
 * vertical, and at 390px it was already being squeezed to "As…".
 */
export function AskBox({
  label,
  placeholder,
  pending,
  value,
  onChange,
  onAsk,
}: {
  label: string;
  placeholder: string;
  pending: boolean;
  /**
   * Controlled, and it has to be. Under a clarification question this box lives inside a
   * panel that three ordinary gestures unmount — stepping to the next question, collapsing
   * the round, walking the docket — and a half-typed question held in here would go with
   * it. The page holds it, the same way it holds the round's answers.
   */
  value: string;
  onChange: (value: string) => void;
  /**
   * Send it, and say when it landed if you can.
   *
   * The box used to be cleared the instant the button was pressed, before the request
   * resolved — and an ask has no timeout, because it runs an agent. So a failure took the
   * reader's sentence off the screen and left them a button offering to resend the identical
   * text, with no way to rephrase the question that had just failed. A caller that hands back
   * the mutation's promise gets the words kept until it resolves and kept for good if it
   * rejects; one that returns nothing keeps exactly the behaviour it had.
   */
  onAsk: (text: string) => void | Promise<unknown>;
}) {
  const send = async () => {
    if (!value.trim() || pending) return;
    try {
      await onAsk(value.trim());
      onChange("");
    } catch {
      // The failure is rendered by the caller, beside this box. What belongs here is the
      // words, still in the field, still editable.
    }
  };
  return (
    <div className="grid max-w-[64ch] gap-2">
      <Textarea
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          // `isComposing` is the whole reason this is not one condition. Anyone writing with
          // an IME — Japanese, Chinese, Korean — presses Enter to commit a candidate, and
          // that press used to send a half-composed question to an agent. Shift+Enter is then
          // the newline, in a box whose entire purpose is a written sentence.
          if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !(event.nativeEvent as KeyboardEvent).isComposing
          ) {
            event.preventDefault();
            void send();
          }
        }}
        rows={2}
        className="min-h-16"
        placeholder={placeholder}
      />
      <div className="flex justify-end">
        <Button disabled={!value.trim() || pending} onClick={() => void send()}>
          {pending ? <Spinner /> : "Ask"}
        </Button>
      </div>
    </div>
  );
}
