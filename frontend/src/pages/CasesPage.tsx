import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi, type CaseSummary } from "../api";
import { Card, Empty, ErrorNotice, Loading, PageTitle } from "../components/ui";

function CaseCard({ value, onSelect }: { value: CaseSummary; onSelect: () => void }) {
  return <button onClick={onSelect} className="rounded-xl border border-rule bg-surface p-4 text-left hover:border-primary"><div className="font-medium">{value.goal || "Unstated architecture goal"}</div><div className="mt-2 text-xs text-ink-3">Revision {value.revision} · {value.constraints.length} constraints · {value.decisions.length} decisions</div></button>;
}

export function CasesPage() {
  const client = useQueryClient();
  const cases = useQuery({ queryKey: ["cases"], queryFn: coreApi.cases });
  const [selected, setSelected] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [authoring, setAuthoring] = useState(false);
  const history = useQuery({ queryKey: ["case-history", selected], queryFn: () => coreApi.caseHistory(selected!), enabled: Boolean(selected) });
  const create = useMutation({ mutationFn: () => coreApi.createCase(goal), onSuccess: async (created) => { setSelected(created.case_id); setGoal(""); setAuthoring(false); await client.invalidateQueries({ queryKey: ["cases"] }); } });
  if (cases.isLoading) return <Loading />;
  if (cases.error) return <ErrorNotice error={cases.error} />;
  return (
    <div>
      <PageTitle eyebrow="Human context" title="Architecture cases"><button onClick={() => setAuthoring(!authoring)} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent">New case</button></PageTitle>
      {authoring ? <Card className="mb-5"><h2 className="font-display text-xl font-semibold">State the architecture goal</h2><div className="mt-4 flex gap-3"><input aria-label="Architecture goal" value={goal} onChange={(event) => setGoal(event.target.value)} className="min-w-0 flex-1 rounded-md border border-rule bg-canvas px-3 py-2" placeholder="What should this architecture make easy or protect?" /><button disabled={!goal.trim() || create.isPending} onClick={() => create.mutate()} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">Create</button></div>{create.error ? <div className="mt-3"><ErrorNotice error={create.error} /></div> : null}</Card> : null}
      {!cases.data?.length ? <Empty>Cases are created when a repository review begins or authored here.</Empty> : <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]"><div className="grid content-start gap-3">{cases.data.map((item) => <CaseCard key={item.case_id} value={item} onSelect={() => setSelected(item.case_id)} />)}</div><Card><h2 className="font-display text-xl font-semibold">Revision history</h2>{!selected ? <p className="mt-4 text-sm text-ink-3">Select a case to see how its architectural context evolved.</p> : history.isLoading ? <Loading /> : history.error ? <ErrorNotice error={history.error} /> : <div className="mt-4 grid gap-4">{history.data?.map((item) => <div key={item.revision} className="border-l-2 border-primary/30 pl-4"><div className="text-xs font-semibold uppercase text-primary">Revision {item.revision}</div><div className="mt-1 font-medium">{item.goal || "Goal not stated"}</div>{item.constraints.map((constraint, index) => <div key={index} className="mt-1 text-sm text-ink-2">{constraint.facet}: {constraint.text}</div>)}</div>)}</div>}</Card></div>}
    </div>
  );
}
