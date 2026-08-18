import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { coreApi } from "../api";
import { Card, Empty, ErrorNotice, Loading, Metric, PageTitle } from "../components/ui";

export function RepositoriesPage() {
  const client = useQueryClient();
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: coreApi.repositories });
  const [selected, setSelected] = useState<string | null>(null);
  const [remote, setRemote] = useState("");
  const [branch, setBranch] = useState("");
  const summary = useQuery({ queryKey: ["repository-summary", selected], queryFn: () => coreApi.repositorySummary(selected!), enabled: Boolean(selected) });
  const checkout = useMutation({ mutationFn: () => coreApi.checkoutRepository(remote, branch.trim() || null), onSuccess: async (value) => { setSelected(value.root_path); setRemote(""); await client.invalidateQueries({ queryKey: ["repositories"] }); } });
  if (repositories.isLoading) return <Loading />;
  if (repositories.error) return <ErrorNotice error={repositories.error} />;
  return (
    <div>
      <PageTitle eyebrow="Deterministic atlas" title="Repositories"><Link to="/start" className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-accent">Review repository</Link></PageTitle>
      <Card className="mb-5"><h2 className="font-display text-lg font-semibold">Checkout a remote repository</h2><div className="mt-4 grid gap-3 md:grid-cols-[1fr_180px_auto]"><input aria-label="Repository URL" value={remote} onChange={(event) => setRemote(event.target.value)} className="rounded-md border border-rule bg-canvas px-3 py-2 text-sm" placeholder="https://github.com/org/repository" /><input aria-label="Branch" value={branch} onChange={(event) => setBranch(event.target.value)} className="rounded-md border border-rule bg-canvas px-3 py-2 text-sm" placeholder="Branch (optional)" /><button disabled={!remote.trim() || checkout.isPending} onClick={() => checkout.mutate()} className="rounded-md border border-primary px-4 py-2 text-sm font-medium text-primary disabled:opacity-50">Checkout</button></div>{checkout.error ? <div className="mt-3"><ErrorNotice error={checkout.error} /></div> : null}</Card>
      {!repositories.data?.length ? <Empty>No repositories have been indexed.</Empty> : <div className="grid gap-5 lg:grid-cols-[.9fr_1.1fr]"><div className="grid content-start gap-3">{repositories.data.map((repository) => <button key={repository.version_id} onClick={() => setSelected(repository.root_path)} className={`rounded-xl border p-4 text-left ${selected === repository.root_path ? "border-primary bg-primary/5" : "border-rule bg-surface"}`}><div className="font-medium">{repository.root_path.split("/").pop()}</div><div className="mt-1 truncate font-mono text-xs text-ink-3">{repository.root_path}</div><div className="mt-3 flex gap-4 text-xs text-ink-2"><span>{repository.node_count} nodes</span><span>{repository.edge_count} edges</span><span>{repository.signal_count} signals</span></div></button>)}</div><Card>{!selected ? <div className="text-sm text-ink-3">Select a repository to inspect its atlas summary.</div> : summary.isLoading ? <Loading /> : summary.error ? <ErrorNotice error={summary.error} /> : <><h2 className="font-display text-xl font-semibold">Atlas summary</h2><p className="mt-3 text-sm leading-6 text-ink-2">{summary.data?.summary}</p><div className="mt-6 grid grid-cols-3 gap-4"><Metric label="Nodes" value={summary.data?.node_ids?.length || 0} /><Metric label="Relations" value={summary.data?.relationships?.length || 0} /><Metric label="Signals" value={summary.data?.signals?.length || 0} /></div></>}</Card></div>}
    </div>
  );
}
