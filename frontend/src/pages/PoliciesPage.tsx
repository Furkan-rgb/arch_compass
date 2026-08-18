import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { coreApi } from "../api";
import { Card, Empty, ErrorNotice, Loading, PageTitle, StatusBadge } from "../components/ui";

export function PoliciesPage() {
  const client = useQueryClient();
  const policies = useQuery({ queryKey: ["policies"], queryFn: coreApi.policies });
  const [query, setQuery] = useState("");
  const [authoring, setAuthoring] = useState(false);
  const [draft, setDraft] = useState({ title: "", description: "", body: "", tags: "", strength: "guidance" as "guidance" | "preferred" | "required" });
  const create = useMutation({ mutationFn: () => coreApi.createPolicy({ title: draft.title, description: draft.description, body: draft.body, tags: draft.tags.split(",").map((item) => item.trim()).filter(Boolean), strength: draft.strength }), onSuccess: async () => { setAuthoring(false); setDraft({ title: "", description: "", body: "", tags: "", strength: "guidance" }); await client.invalidateQueries({ queryKey: ["policies"] }); } });
  const remove = useMutation({ mutationFn: coreApi.deletePolicy, onSuccess: () => client.invalidateQueries({ queryKey: ["policies"] }) });
  if (policies.isLoading) return <Loading />;
  if (policies.error) return <ErrorNotice error={policies.error} />;
  const visible = (policies.data || []).filter((policy) => `${policy.title} ${policy.body} ${policy.tags.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div>
      <PageTitle eyebrow="Architectural guidance" title="Policy corpus">
        <div className="flex gap-2"><input aria-label="Search policies" value={query} onChange={(event) => setQuery(event.target.value)} className="rounded-md border border-rule bg-surface px-3 py-2 text-sm" placeholder="Search policies" /><button onClick={() => setAuthoring(!authoring)} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent">Author policy</button></div>
      </PageTitle>
      {authoring ? <Card className="mb-6"><h2 className="font-display text-xl font-semibold">New workspace policy</h2><div className="mt-5 grid gap-4"><input aria-label="Policy title" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className="rounded-md border border-rule bg-canvas px-3 py-2" placeholder="Policy title" /><input aria-label="Policy description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="rounded-md border border-rule bg-canvas px-3 py-2" placeholder="What this policy protects" /><textarea aria-label="Policy body" value={draft.body} onChange={(event) => setDraft({ ...draft, body: event.target.value })} className="min-h-40 rounded-md border border-rule bg-canvas p-3" placeholder="Markdown policy body" /><div className="grid gap-3 sm:grid-cols-2"><input aria-label="Policy tags" value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} className="rounded-md border border-rule bg-canvas px-3 py-2" placeholder="tags, comma-separated" /><select aria-label="Policy strength" value={draft.strength} onChange={(event) => setDraft({ ...draft, strength: event.target.value as typeof draft.strength })} className="rounded-md border border-rule bg-canvas px-3 py-2"><option value="guidance">Guidance</option><option value="preferred">Preferred</option><option value="required">Required</option></select></div><div><button disabled={!draft.title.trim() || !draft.description.trim() || !draft.body.trim() || create.isPending} onClick={() => create.mutate()} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">Save policy</button></div></div>{create.error ? <div className="mt-4"><ErrorNotice error={create.error} /></div> : null}</Card> : null}
      {!visible.length ? <Empty>No policies match.</Empty> : <div className="grid gap-3">{visible.map((policy) => <details key={policy.id} className="group rounded-xl border border-rule bg-surface p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-4"><div><div className="font-display text-lg font-semibold">{policy.title}</div><div className="mt-1 text-xs text-ink-3">{policy.scope}{policy.applies_to ? ` · ${policy.applies_to}` : ""} · {policy.source.author}</div></div><StatusBadge status={policy.strength} /></summary><div className="mt-5 whitespace-pre-wrap border-t border-rule pt-5 text-sm leading-7 text-ink-2">{policy.body}</div>{policy.origin === "workspace" ? <button onClick={() => remove.mutate(policy.id)} className="mt-4 text-xs text-danger">Delete workspace policy</button> : null}</details>)}</div>}
    </div>
  );
}
