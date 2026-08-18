import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { coreApi } from "../api";
import { Button, Card, Empty, ErrorNotice, Field, Input, Loading, Metric, PageTitle, SectionHeading, buttonClass, cn } from "../components/ui";

export function RepositoriesPage() {
  const client = useQueryClient();
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: coreApi.repositories });
  const [selected, setSelected] = useState<string | null>(null);
  const [remote, setRemote] = useState("");
  const [branch, setBranch] = useState("");
  const selectedRoot = selected || repositories.data?.[0]?.root_path || null;
  const summary = useQuery({ queryKey: ["repository-summary", selectedRoot], queryFn: () => coreApi.repositorySummary(selectedRoot!), enabled: Boolean(selectedRoot) });
  const checkout = useMutation({ mutationFn: () => coreApi.checkoutRepository(remote.trim(), branch.trim() || null), onSuccess: async (value) => { setSelected(value.root_path); setRemote(""); setBranch(""); await client.invalidateQueries({ queryKey: ["repositories"] }); } });
  if (repositories.isLoading) return <Loading label="Loading repository atlases…" />;
  if (repositories.error) return <ErrorNotice error={repositories.error} />;

  return <div>
    <PageTitle eyebrow="Deterministic atlas" title="Repositories" description="Inspect indexed repository snapshots or check out a remote repository into the workspace."><Link to="/start" className={buttonClass()}>Review repository</Link></PageTitle>
    <Card className="mb-6"><SectionHeading title="Checkout a remote repository" description="The checkout stays in the workspace and is indexed when you start a review." /><div className="mt-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_200px_auto] md:items-end"><Field label="Repository URL" htmlFor="repository-url"><Input id="repository-url" value={remote} onChange={(event) => setRemote(event.target.value)} placeholder="https://github.com/org/repository" /></Field><Field label="Branch" htmlFor="repository-branch" hint="Optional"><Input id="repository-branch" value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="main" /></Field><Button variant="secondary" disabled={!remote.trim() || checkout.isPending} onClick={() => checkout.mutate()}>{checkout.isPending ? "Checking out…" : "Checkout"}</Button></div>{checkout.error ? <div className="mt-4"><ErrorNotice error={checkout.error} /></div> : null}</Card>
    {!repositories.data?.length ? <Empty title="No repositories indexed">Start a review or check out a remote repository to build the first atlas.</Empty> : <div className="grid gap-5 xl:grid-cols-[minmax(280px,.75fr)_minmax(0,1.25fr)]"><div className="grid content-start gap-2">{repositories.data.map((repository) => <button key={repository.version_id} onClick={() => setSelected(repository.root_path)} className={cn("rounded-2xl border p-4 text-left transition", selectedRoot === repository.root_path ? "border-primary bg-primary-soft shadow-sm" : "border-rule bg-surface hover:border-primary/35")}><div className="font-display text-lg font-semibold">{repository.root_path.split("/").pop()}</div><div className="mt-1 truncate font-mono text-[11px] text-ink-3">{repository.root_path}</div><div className="mt-4 flex gap-4 text-xs font-medium text-ink-2"><span>{repository.node_count} nodes</span><span>{repository.edge_count} edges</span><span>{repository.signal_count} signals</span></div></button>)}</div><Card>{summary.isLoading ? <Loading label="Reading atlas summary…" /> : summary.error ? <ErrorNotice error={summary.error} /> : <><SectionHeading title="Atlas summary" description={selectedRoot || undefined} /><p className="mt-5 text-sm leading-7 text-ink-2">{summary.data?.summary}</p><div className="mt-6 grid grid-cols-3 gap-4 border-t border-rule pt-5"><Metric label="Nodes" value={summary.data?.node_ids?.length || 0} /><Metric label="Relations" value={summary.data?.relationships?.length || 0} /><Metric label="Signals" value={summary.data?.signals?.length || 0} /></div></>}</Card></div>}
  </div>;
}
