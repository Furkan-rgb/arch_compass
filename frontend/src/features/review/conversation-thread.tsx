import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Review, type ReviewConversation } from "../../api";
import { shortId } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Input } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { Label } from "../../ui/panel";
import { Spinner } from "../../ui/states";
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
  return (
    <div className="grid gap-2">
      <div className="rounded-md border border-rule bg-surface-2 px-3 py-2.5">
        <Label>Question</Label>
        {/* `wrap-anywhere` on both halves: a question is regularly a qualified name with a
            few words around it, and an answer quotes paths back. One token wider than a
            phone and nothing else in the panel can help. */}
        <p className="mt-1 text-sm leading-6 text-ink wrap-anywhere">{message.question}</p>
      </div>
      <div className="rounded-md border border-rule bg-sunken/50 px-3 py-2.5">
        <Label>Agent</Label>
        <p className="mt-1 whitespace-pre-line text-sm leading-6 text-ink-2 wrap-anywhere">
          {message.answer.text}
        </p>

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
            <p className="mt-1 whitespace-pre-line text-sm leading-6 text-ink wrap-anywhere">
              {suggested}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => onUseAnswer(suggested)}>
                Put this in my answer
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
              <Label>Looked up</Label>
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
                      title={finding.candidate.summary}
                      onClick={() => onOpen(id)}
                      className="max-w-full text-left"
                    >
                      <Tag className="transition hover:border-rule-strong hover:text-ink">
                        {finding.candidate.summary}
                      </Tag>
                    </button>
                  );
                }
                if (finding) return <Tag key={id}>{finding.candidate.summary}</Tag>;
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
 * Shared for the same reason the exchange is: two surfaces, one gesture. Enter sends, and
 * the button is `shrink-0` — everything on this page may be narrower than its content, which
 * is what keeps a path from widening it, but a three-letter button has nothing to give and
 * at 390px it was being squeezed to "As…".
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
  onAsk: (text: string) => void;
}) {
  const send = () => {
    if (!value.trim() || pending) return;
    onAsk(value.trim());
    onChange("");
  };
  return (
    <div className="flex gap-2">
      <Input
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") send();
        }}
        className="min-w-0 flex-1"
        placeholder={placeholder}
      />
      <Button className="shrink-0" disabled={!value.trim() || pending} onClick={send}>
        {pending ? <Spinner /> : "Ask"}
      </Button>
    </div>
  );
}
