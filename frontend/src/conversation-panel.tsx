import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "./api";
import type { ConversationMessage, ReportConversation } from "./types";

/**
 * Ask questions about one finished consultation.
 *
 * The conversation is pinned to the run's exact case revision, Atlas version and
 * policy index, and is read-only with respect to the recommendation: nothing asked
 * here revises the decision. Answers cite the evidence the original run surfaced, so
 * the panel shows the assistant's rendered text rather than reformatting it.
 */
export function ConversationPanel({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  const conversations = useQuery({
    queryKey: ["conversations", runId],
    queryFn: () => api.conversations(runId),
  });

  const activeId = selected ?? conversations.data?.[0]?.conversation_id ?? null;

  const history = useQuery({
    queryKey: ["conversation-history", activeId],
    queryFn: () => api.conversationHistory(activeId as string),
    enabled: activeId !== null,
  });

  const start = useMutation({
    mutationFn: () => api.createConversation(runId),
    onSuccess: (created: ReportConversation) => {
      setSelected(created.conversation_id ?? null);
      void queryClient.invalidateQueries({ queryKey: ["conversations", runId] });
    },
  });

  const ask = useMutation({
    mutationFn: (value: string) =>
      api.askConversation(activeId as string, value),
    onSuccess: () => {
      setQuestion("");
      void queryClient.invalidateQueries({
        queryKey: ["conversation-history", activeId],
      });
    },
  });

  const failure = (start.error ?? ask.error) as ApiError | null;

  return (
    <section className="panel" aria-label="Report conversation">
      <header className="panel-header">
        <h2>Ask about this report</h2>
        <p className="muted">
          Pinned to this run&rsquo;s exact evidence. Answers explain the recorded
          recommendation; they never change it.
        </p>
      </header>

      {conversations.isLoading ? <p>Loading conversations&hellip;</p> : null}

      {conversations.data && conversations.data.length > 1 ? (
        <label>
          Conversation
          <select
            value={activeId ?? ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {conversations.data.map((item) => (
              <option key={item.conversation_id} value={item.conversation_id}>
                {item.title ?? item.conversation_id}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {activeId === null && conversations.isSuccess ? (
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending}
        >
          {start.isPending ? "Starting…" : "Start a conversation"}
        </button>
      ) : null}

      {failure ? (
        <p role="alert" className="error">
          {failure.message}
        </p>
      ) : null}

      {activeId !== null ? (
        <>
          <ol className="conversation-messages">
            {(history.data ?? []).map((message: ConversationMessage) => (
              <li key={message.message_id} data-role={message.role}>
                <span className="muted">
                  {message.role === "user" ? "You" : "ArchCompass"}
                </span>
                <p>{message.text}</p>
              </li>
            ))}
          </ol>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              const trimmed = question.trim();
              if (trimmed) {
                ask.mutate(trimmed);
              }
            }}
          >
            <label>
              Question
              <textarea
                value={question}
                maxLength={4000}
                rows={3}
                placeholder="Which evidence supports FIND-001?"
                onChange={(event) => setQuestion(event.target.value)}
              />
            </label>
            <button type="submit" disabled={ask.isPending || !question.trim()}>
              {ask.isPending ? "Asking…" : "Ask"}
            </button>
          </form>
        </>
      ) : null}
    </section>
  );
}
