import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi, type CaseSummary } from "../api";
import { Button, Card, Empty, ErrorNotice, Field, Input, Loading, PageTitle, SectionHeading, cn } from "../components/ui";

function CaseCard({ value, selected, onSelect }: { value: CaseSummary; selected: boolean; onSelect: () => void }) {
  return <button onClick={onSelect} className={cn("rounded-2xl border p-4 text-left transition", selected ? "border-primary bg-primary-soft shadow-sm" : "border-rule bg-surface hover:border-primary/35")}><div className="font-display text-lg font-semibold leading-6">{value.goal || "Unstated architecture goal"}</div><div className="mt-3 flex flex-wrap gap-2 text-xs text-ink-3"><span>Revision {value.revision}</span><span>·</span><span>{value.constraints.length} constraints</span><span>·</span><span>{value.decisions.length} decisions</span></div></button>;
}

export function CasesPage() {
  const client = useQueryClient();
  const cases = useQuery({ queryKey: ["cases"], queryFn: coreApi.cases });
  const [selected, setSelected] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [authoring, setAuthoring] = useState(false);
  const selectedId = selected || cases.data?.[0]?.case_id || null;
  const history = useQuery({ queryKey: ["case-history", selectedId], queryFn: () => coreApi.caseHistory(selectedId!), enabled: Boolean(selectedId) });
  const create = useMutation({ mutationFn: () => coreApi.createCase(goal.trim()), onSuccess: async (created) => { setSelected(created.case_id); setGoal(""); setAuthoring(false); await client.invalidateQueries({ queryKey: ["cases"] }); } });
  if (cases.isLoading) return <Loading label="Loading architecture cases…" />;
  if (cases.error) return <ErrorNotice error={cases.error} />;

  return <div>
    <PageTitle eyebrow="Human context" title="Architecture cases" description="Cases capture goals, constraints, decisions, and clarifications as an immutable sequence of revisions."><Button onClick={() => setAuthoring(!authoring)} variant={authoring ? "secondary" : "primary"}>{authoring ? "Close form" : "New case"}</Button></PageTitle>
    {authoring ? <Card className="mb-6" tone="accent"><SectionHeading title="State the architecture goal" description="Describe what this architecture should make easy, protect, or deliberately trade off." /><div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end"><div className="min-w-0 flex-1"><Field label="Goal" htmlFor="architecture-goal"><Input id="architecture-goal" value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="Keep domain behavior independent from delivery mechanisms" /></Field></div><Button disabled={!goal.trim() || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Creating…" : "Create case"}</Button></div>{create.error ? <div className="mt-4"><ErrorNotice error={create.error} /></div> : null}</Card> : null}
    {!cases.data?.length ? <Empty title="No architecture cases">Cases are created when a repository review begins, or you can define one here first.</Empty> : <div className="grid gap-5 xl:grid-cols-[minmax(280px,.75fr)_minmax(0,1.25fr)]"><div className="grid content-start gap-2">{cases.data.map((item) => <CaseCard key={item.case_id} value={item} selected={selectedId === item.case_id} onSelect={() => setSelected(item.case_id)} />)}</div><Card><SectionHeading title="Revision history" description="Every clarification produces a new case revision; earlier context remains inspectable." />{history.isLoading ? <div className="mt-5"><Loading /></div> : history.error ? <div className="mt-5"><ErrorNotice error={history.error} /></div> : <div className="relative mt-6 grid gap-6 before:absolute before:bottom-3 before:left-[7px] before:top-3 before:w-px before:bg-rule-strong">{history.data?.map((item) => <div key={item.revision} className="relative pl-8 before:absolute before:left-0 before:top-1.5 before:size-[15px] before:rounded-full before:border-4 before:border-surface before:bg-primary"><div className="text-xs font-bold uppercase tracking-[0.12em] text-primary">Revision {item.revision}</div><div className="mt-1 font-display text-lg font-semibold">{item.goal || "Goal not stated"}</div>{item.constraints.length ? <div className="mt-3 grid gap-2">{item.constraints.map((constraint, index) => <div key={index} className="rounded-lg bg-canvas-strong/60 px-3 py-2 text-sm text-ink-2"><span className="font-semibold text-ink">{constraint.facet}: </span>{constraint.text}</div>)}</div> : <div className="mt-2 text-sm text-ink-3">No constraints recorded.</div>}</div>)}</div>}</Card></div>}
  </div>;
}
