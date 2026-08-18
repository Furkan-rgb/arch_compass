import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { coreApi } from "../api";
import { ErrorNotice, Metric } from "./ui";

export function AtlasExplorer({ root, initialTerms = [] }: { root: string; initialTerms?: string[] }) {
  const [query, setQuery] = useState(initialTerms.slice(0, 5).join(" "));
  const explore = useMutation({ mutationFn: (terms: string[]) => coreApi.exploreRepository(root, terms) });
  useEffect(() => {
    const terms = initialTerms.slice(0, 5).filter(Boolean);
    if (terms.length) explore.mutate(terms);
    // The initial review context is deliberately loaded once; subsequent searches belong to the reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root]);
  function search() {
    const terms = query.split(/\s+/).map((item) => item.trim()).filter(Boolean).slice(0, 10);
    if (terms.length) explore.mutate(terms);
  }
  return (
    <section className="rounded-xl border border-rule bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="font-display text-xl font-semibold">Repository atlas</h2><p className="mt-1 text-sm text-ink-2">Search the deterministic nodes and relationships available to the application.</p></div><div className="flex min-w-[280px] gap-2"><input aria-label="Search atlas" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") search(); }} className="min-w-0 flex-1 rounded-md border border-rule bg-canvas px-3 py-2 text-sm" placeholder="module, class, function" /><button onClick={search} disabled={!query.trim() || explore.isPending} className="rounded-md bg-primary px-3 py-2 text-sm font-semibold text-on-accent disabled:opacity-50">Search</button></div></div>
      {explore.error ? <div className="mt-4"><ErrorNotice error={explore.error} /></div> : null}
      {explore.data ? <><div className="mt-6 grid grid-cols-3 gap-4 border-y border-rule py-4"><Metric label="Matched nodes" value={explore.data.node_summaries?.length || 0} /><Metric label="Relationships" value={explore.data.relationships?.length || 0} /><Metric label="Signals" value={explore.data.signals?.length || 0} /></div><div className="mt-5 grid gap-2 md:grid-cols-2">{explore.data.node_summaries?.map((node) => <article key={node.node_id} className="rounded-lg border border-rule bg-canvas p-3"><div className="truncate font-mono text-sm">{node.qualified_name}</div><div className="mt-1 flex justify-between gap-3 text-xs text-ink-3"><span>{node.node_type}</span><span className="truncate">{node.path}</span></div></article>)}</div>{explore.data.relationships?.length ? <details className="mt-5 rounded-lg border border-rule p-4"><summary className="text-sm font-medium">Relationship records</summary><div className="mt-3 grid gap-2 font-mono text-xs text-ink-3">{explore.data.relationships.slice(0, 30).map((edge) => <div key={edge.edge_id}>{edge.source_id.slice(0, 10)} → {edge.edge_type} → {edge.target_id.slice(0, 10)}</div>)}</div></details> : null}</> : <div className="mt-6 rounded-lg border border-dashed border-rule p-8 text-center text-sm text-ink-3">Search the atlas to inspect structural context.</div>}
    </section>
  );
}
