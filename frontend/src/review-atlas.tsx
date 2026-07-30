import { useMutation, useQueries } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";

import { api } from "./api";
import { RepositoryAtlas, type AtlasEdgeView, type AtlasNodeView } from "./atlas";
import { ErrorPanel } from "./components";
import type { AtlasQueryResult, ReviewedBoundary } from "./types";

/**
 * The repository the review judged, drawn around the boundaries it examined.
 *
 * Built from the review outward rather than from the repository inward. A map of the whole
 * atlas beside a review would be a second, unrelated thing on the page; what a reader wants
 * here is where these particular boundaries sit and what reaches them, so each reviewed
 * abstraction is inspected and its neighbourhood is the map.
 *
 * The verdict is on the node. A boundary that was examined and cleared is drawn as cleared,
 * not as an ordinary node: the difference between "found to be earning its place" and
 * "never looked at" is the whole value of an exhaustive sweep, and a map that erased it
 * would undo what the review is for.
 */

/* One swatch of the legend, in the two verdict hues the map draws a judged node in and the
   sunken well it draws every other node in. Named by the verdict rather than by the atlas's
   own node tokens, which are aliases of exactly these: a legend that named the alias would
   go on agreeing with itself while drifting from the thing it labels. */
const legendKey = "size-[11px] rounded-control border border-ink-3";

/** Every node of an inspection, keyed so repeated appearances collapse into one. */
function collectNodes(results: AtlasQueryResult[]) {
  return new Map(
    results.flatMap((result) => result.node_summaries).map((node) => [node.node_id, node]),
  );
}

export function reviewAtlasNodes(
  results: AtlasQueryResult[],
  boundaries: ReviewedBoundary[],
): AtlasNodeView[] {
  const verdicts = new Map(
    boundaries
      .map((item) => [item.candidate.participants[0]?.node_id, item] as const)
      .filter((pair): pair is readonly [string, ReviewedBoundary] => Boolean(pair[0])),
  );
  // The one implementation each boundary stands in front of. Named separately so it reads
  // as part of the finding rather than as one more node that happens to be nearby.
  const implementations = new Map(
    boundaries
      .map((item) => [item.candidate.participants[1]?.node_id, item] as const)
      .filter((pair): pair is readonly [string, ReviewedBoundary] => Boolean(pair[0])),
  );
  return [...collectNodes(results).values()].map((node): AtlasNodeView => {
    const reviewed = verdicts.get(node.node_id);
    const implements_ = implementations.get(node.node_id);
    return {
      id: node.node_id,
      label: node.qualified_name.split(".").at(-1) || node.qualified_name,
      path: node.location
        ? `${node.path}:${node.location.start_line}–${node.location.end_line}`
        : node.path,
      kind: node.node_type,
      isPublic: node.is_public,
      state: reviewed
        ? reviewed.material
          ? "hotspot"
          : "cleared"
        : ["repository", "package"].includes(node.node_type)
          ? "contained"
          : "normal",
      description: reviewed
        ? `${reviewed.reference} · ${reviewed.verdict_label}. ${reviewed.rationale}`
        : implements_
          ? `The one implementation behind ${implements_.reference}.`
          : undefined,
      metrics: [],
      signals: [],
    };
  });
}

export function reviewAtlasEdges(
  results: AtlasQueryResult[],
  nodes: AtlasNodeView[],
): AtlasEdgeView[] {
  const known = new Set(nodes.map((node) => node.id));
  const seen = new Set<string>();
  const edges: AtlasEdgeView[] = [];
  for (const edge of results.flatMap((result) => result.relationships)) {
    if (!known.has(edge.source_id) || !known.has(edge.target_id)) continue;
    if (seen.has(edge.edge_id)) continue;
    seen.add(edge.edge_id);
    edges.push({
      id: edge.edge_id,
      sourceId: edge.source_id,
      targetId: edge.target_id,
      kind: edge.edge_type,
      confidence: edge.confidence,
    });
  }
  return edges;
}

/**
 * Which node is selected is the page's business, not this component's: a finding above can
 * ask the map to show its boundary, so the two have to agree on one answer rather than each
 * keeping their own.
 */
export function ReviewAtlas({
  repositoryRoot,
  boundaries,
  selectedNodeId,
  onSelectNode,
}: {
  repositoryRoot: string;
  boundaries: ReviewedBoundary[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
}) {
  const [explored, setExplored] = useState<AtlasQueryResult[]>([]);

  // One inspection per boundary, which is what makes the map about this review. They are
  // separate queries rather than one call because that is the shape the atlas port has, and
  // a review examines a handful of boundaries, not hundreds.
  const nodeIds = boundaries
    .map((item) => item.candidate.participants[0]?.node_id)
    .filter((id): id is string => Boolean(id));
  const inspections = useQueries({
    queries: nodeIds.map((nodeId) => ({
      queryKey: ["repository-inspect", repositoryRoot, nodeId],
      queryFn: () => api.repositoryInspect(repositoryRoot, nodeId),
    })),
  });

  const explore = useMutation({
    mutationFn: api.repositoryExplore,
    onSuccess: (result) => {
      setExplored((current) => [
        ...current.filter(
          (item) => JSON.stringify(item.query) !== JSON.stringify(result.query),
        ),
        result,
      ]);
    },
  });

  const results = useMemo(
    () => [
      ...inspections.flatMap((query) => (query.data ? [query.data] : [])),
      ...explored,
    ],
    [inspections, explored],
  );
  const nodes = useMemo(() => reviewAtlasNodes(results, boundaries), [results, boundaries]);
  const edges = useMemo(() => reviewAtlasEdges(results, nodes), [results, nodes]);

  const failed = inspections.find((query) => query.error)?.error;
  const loading = inspections.some((query) => query.isLoading) || explore.isPending;

  return (
    <section
      data-slot="review-atlas"
      className="mb-10"
      aria-label="Where these boundaries sit"
    >
      <h2 className="m-0 mb-1 flex items-center gap-2 border-b border-rule pb-3 text-sub tracking-[-.01em]">
        Where these boundaries sit
      </h2>
      <p className="m-0 text-body text-ink-2">
        The same atlas the review was judged against, drawn around the boundaries it
        examined. Selecting one shows its verdict beside the map; the arrows are what the
        parser found, not what the model said.
      </p>
      <p className="m-0 mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-ui text-ink-2">
        <span className={cn(legendKey, "border-material bg-material-soft")} /> should change
        <span className={cn(legendKey, "border-cleared bg-cleared-soft")} /> left as it is
        <span className={cn(legendKey, "bg-sunken")} /> not a boundary the detector surfaces
      </p>
      {failed ? <ErrorPanel error={failed} /> : null}
      {explore.isError ? <ErrorPanel error={explore.error} /> : null}
      <RepositoryAtlas
        title={`${repositoryRoot.split("/").at(-1)} atlas`}
        description="Nodes carry this review's verdicts; everything else is the parser's own evidence."
        nodes={nodes}
        edges={edges}
        loading={loading}
        emptyMessage="This review's boundaries are no longer in the indexed atlas."
        selectedNodeId={selectedNodeId}
        // Selecting a node used to set the location hash, which threw the reader back up
        // the page to the finding — away from the map they had just started reading. The
        // verdict is already on the node and in the detail panel beside it, so a click can
        // simply answer where it was made.
        onSelectNode={onSelectNode}
        onExploreNode={(nodeId, operation, depth) =>
          explore.mutate({
            root_path: repositoryRoot,
            operation,
            node_id: nodeId,
            depth: depth ?? 1,
            limit: 60,
          })
        }
        onSearch={(term) =>
          explore.mutate({
            root_path: repositoryRoot,
            operation: "search",
            terms: term.trim().split(/\s+/).slice(0, 10),
            limit: 30,
          })
        }
      />
    </section>
  );
}
