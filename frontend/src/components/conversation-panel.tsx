import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { coreApi } from "../api";
import { Button, Card, ErrorNotice, Input, SectionHeading } from "./ui";

export function ConversationPanel({ reviewId }: { reviewId: string }) {
  const client = useQueryClient();
  const conversations = useQuery({ queryKey: ["conversations", reviewId], queryFn: () => coreApi.conversations(reviewId) });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  useEffect(() => { if (!conversationId && conversations.data?.[0]) setConversationId(conversations.data[0].id); }, [conversationId, conversations.data]);
  const turn = useMutation({ mutationFn: async () => { const id = conversationId || (await coreApi.createConversation(reviewId)).id; setConversationId(id); return coreApi.ask(id, question); }, onSuccess: async () => { setQuestion(""); await client.invalidateQueries({ queryKey: ["conversations", reviewId] }); } });
  const current = turn.data || conversations.data?.find((item) => item.id === conversationId) || conversations.data?.[0];
  return <Card><SectionHeading title="Ask about this review" description="Answers are grounded in the immutable review, its case, policies, and pinned evidence." /><div className="mt-6 grid gap-4">{current?.messages.map((message, index) => <div key={`${message.asked_at}-${index}`} className="grid gap-2"><div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-3 text-sm leading-6 text-on-accent">{message.question}</div><div className="max-w-[90%] rounded-2xl rounded-bl-md bg-canvas-strong px-4 py-3 text-sm leading-6 text-ink-2">{message.answer.text}{message.answer.supporting_candidate_ids.length ? <div className="mt-3 border-t border-rule pt-2 text-xs text-ink-3">Grounded in {message.answer.supporting_candidate_ids.length} candidate(s)</div> : null}</div></div>)}</div><div className="mt-6 flex gap-2 border-t border-rule pt-5"><Input aria-label="Question about this review" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && question.trim()) turn.mutate(); }} className="min-w-0 flex-1" placeholder="Ask a grounded follow-up…" /><Button disabled={!question.trim() || turn.isPending} onClick={() => turn.mutate()}>{turn.isPending ? "Answering…" : "Ask"}</Button></div>{turn.error ? <div className="mt-3"><ErrorNotice error={turn.error} /></div> : null}</Card>;
}
