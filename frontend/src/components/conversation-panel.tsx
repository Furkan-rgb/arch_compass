import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { coreApi } from "../api";
import { ErrorNotice } from "./ui";

export function ConversationPanel({ reviewId }: { reviewId: string }) {
  const client = useQueryClient();
  const conversations = useQuery({ queryKey: ["conversations", reviewId], queryFn: () => coreApi.conversations(reviewId) });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  useEffect(() => { if (!conversationId && conversations.data?.[0]) setConversationId(conversations.data[0].id); }, [conversationId, conversations.data]);
  const turn = useMutation({ mutationFn: async () => { const id = conversationId || (await coreApi.createConversation(reviewId)).id; setConversationId(id); return coreApi.ask(id, question); }, onSuccess: async () => { setQuestion(""); await client.invalidateQueries({ queryKey: ["conversations", reviewId] }); } });
  const current = turn.data || conversations.data?.find((item) => item.id === conversationId) || conversations.data?.[0];
  return <section className="rounded-xl border border-rule bg-surface p-5"><h2 className="font-display text-xl font-semibold">Ask about this review</h2><p className="mt-2 text-sm text-ink-2">Answers are grounded in the immutable review, its case, policies, and pinned evidence.</p><div className="mt-5 grid gap-3">{current?.messages.map((message, index) => <div key={`${message.asked_at}-${index}`} className="grid gap-2"><div className="ml-auto max-w-[85%] rounded-xl bg-primary px-4 py-3 text-sm text-on-accent">{message.question}</div><div className="max-w-[90%] rounded-xl bg-canvas px-4 py-3 text-sm leading-6 text-ink-2">{message.answer.text}{message.answer.supporting_candidate_ids.length ? <div className="mt-2 text-xs text-ink-3">Grounded in {message.answer.supporting_candidate_ids.length} candidate(s)</div> : null}</div></div>)}</div><div className="mt-5 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && question.trim()) turn.mutate(); }} className="min-w-0 flex-1 rounded-md border border-rule bg-canvas px-3 py-2.5 text-sm" placeholder="Ask a grounded follow-up" /><button disabled={!question.trim() || turn.isPending} onClick={() => turn.mutate()} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">Ask</button></div>{turn.error ? <div className="mt-3"><ErrorNotice error={turn.error} /></div> : null}</section>;
}
