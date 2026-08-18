import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { coreApi } from "../api";
import { Button, Card, Empty, ErrorNotice, Input, Metric, SectionHeading } from "./ui";

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
    <Card>
      <SectionHeading title="Repository atlas" description="Search the deterministic nodes and relationships available to the application."><div className="flex w-full gap-2 sm:w-auto sm:min-w-[340px]"><Input aria-label="Search atlas" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") search(); }} className="min-w-0 flex-1" placeholder="module, class, function" /><Button onClick={search} disabled={!query.trim() || explore.isPending}>Search</Button></div></SectionHeading>
      {explore.error ? <div className="mt-4"><ErrorNotice error={explore.error} /></div> : null}
      {explore.data ? <><div className="mt-6 grid grid-cols-3 gap-4 border-y border-rule py-5"><Metric label="Matched nodes" value={explore.data.node_summaries?.length || 0} /><Metric label="Relationships" value={explore.data.relationships?.length || 0} /><Metric label="Signals" value={explore.data.signals?.length || 0} /></div><div className="mt-5 grid gap-2 md:grid-cols-2">{explore.data.node_summaries?.map((node) => <article key={node.node_id} className="rounded-xl border border-rule bg-canvas-strong/45 p-4"><div className="truncate font-mono text-sm font-medium">{node.qualified_name}</div><div className="mt-2 flex justify-between gap-3 text-xs text-ink-3"><span className="rounded-full bg-surface px-2 py-0.5">{node.node_type}</span><span className="truncate">{node.path}</span></div></article>)}</div>{explore.data.relationships?.length ? <details className="mt-5 rounded-xl border border-rule p-4"><summary className="text-sm font-semibold">Relationship records · {explore.data.relationships.length}</summary><div className="mt-3 grid gap-2 font-mono text-xs text-ink-3">{explore.data.relationships.slice(0, 30).map((edge) => <div key={edge.edge_id}>{edge.source_id.slice(0, 10)} → {edge.edge_type} → {edge.target_id.slice(0, 10)}</div>)}</div></details> : null}</> : <div className="mt-6"><Empty title="Explore the repository graph">Search the atlas to inspect structural context.</Empty></div>}
    </Card>
  );
}
