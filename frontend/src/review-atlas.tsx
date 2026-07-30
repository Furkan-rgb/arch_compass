import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "./api";
import {
  RepositoryAtlas,
  type AtlasEdgeView,
  type AtlasMetricView,
  type AtlasNodeState,
  type AtlasNodeView,
} from "./atlas";
import { ErrorPanel, humanizeLabel } from "./components";
import type {
  AtlasExploreRequest,
  AtlasMetricValue,
  AtlasQueryResult,
  AtlasSignal,
  ReviewedBoundary,
} from "./types";

/**
 * The repository the review judged, drawn around the boundaries it examined.
 *
 * Built from the review outward rather than from the repository inward. A map of the whole
 * atlas beside a review would be a second, unrelated thing on the page; what a reader wants
 * here is where these particular boundaries sit and what reaches them, so the neighbourhood of
 * every reviewed abstraction — and of the implementation behind it — is the map.
 *
 * The verdict is on the node. A boundary that was examined and cleared is drawn as cleared,
 * not as an ordinary node: the difference between "found to be earning its place" and
 * "never looked at" is the whole value of an exhaustive sweep, and a map that erased it
 * would undo what the review is for.
 */

/**
 * What this page calls each state the map draws a node in.
 *
 * The map's legend, in the review's own words, rather than a second legend above the canvas
 * saying something else. There were two: this page named the verdicts and the toolbar named
 * the atlas's node tokens — "Hotspot" for a boundary that should change — and left `cleared`
 * out of both, which is the one state a review invents. One key, one vocabulary, beside the
 * thing it labels.
 */
const VERDICT_LEGEND: Partial<Record<AtlasNodeState, string>> = {
  hotspot: "Should change",
  cleared: "Left as it is",
  normal: "Not a boundary the detector surfaces",
  contained: "Where the boundaries sit",
};

/** Every node of a result, keyed so repeated appearances collapse into one. */
function collectNodes(results: AtlasQueryResult[]) {
  return new Map(
    results.flatMap((result) => result.node_summaries).map((node) => [node.node_id, node]),
  );
}

/**
 * What was measured of each node, in the shape the detail panel reads.
 *
 * These used to be dropped on the floor: the review context returns them for every node it
 * carries, and the map handed the panel an empty list — so a reader who selected a boundary
 * was shown "Evidence references: 0" where the atlas held its reach and its fan-in. The
 * measurement keeps its nature, scope and limitations, because a number whose scope the reader
 * cannot see is a number they will read as meaning more than it does.
 */
function collectMetrics(results: AtlasQueryResult[]) {
  const byNode = new Map<string, Map<string, AtlasMetricView>>();
  for (const value of results.flatMap((result) => result.metric_values)) {
    const metrics = byNode.get(value.node_id) || new Map<string, AtlasMetricView>();
    // Keyed by the metric, not appended: the same node arrives in the review context and again
    // in whatever the reader has explored since, carrying the same measurement each time.
    metrics.set(value.metric, metricView(value));
    byNode.set(value.node_id, metrics);
  }
  return byNode;
}

function metricView(value: AtlasMetricValue): AtlasMetricView {
  return {
    label: humanizeLabel(value.metric),
    value: value.value,
    nature: value.nature,
    scope: value.scope,
    definition: value.definition,
    limitations: value.limitations,
  };
}

/** The structural signals raised against each node, deduplicated the same way. */
function collectSignals(results: AtlasQueryResult[]) {
  const byNode = new Map<string, Map<string, AtlasSignal>>();
  for (const signal of results.flatMap((result) => result.signals)) {
    const signals = byNode.get(signal.node_id) || new Map<string, AtlasSignal>();
    // A node can carry two signals of one code at two places, so where it was raised is part
    // of which signal it is.
    const where = signal.location
      ? `${signal.location.path}:${signal.location.start_line}`
      : "";
    signals.set(`${signal.code}\n${where}`, signal);
    byNode.set(signal.node_id, signals);
  }
  return byNode;
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
  const metrics = collectMetrics(results);
  const signals = collectSignals(results);
  return [...collectNodes(results).values()].map((node): AtlasNodeView => {
    const reviewed = verdicts.get(node.node_id);
    const implements_ = implementations.get(node.node_id);
    const raised = [...(signals.get(node.node_id)?.values() || [])];
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
      metrics: [...(metrics.get(node.node_id)?.values() || [])],
      signals: raised,
      signalCount: raised.length,
      // Only the abstraction a verdict was written about. The implementation behind it is on
      // the map and named as such, but the finding is filed under the boundary.
      hasFinding: Boolean(reviewed),
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
 * The nodes this review's map is drawn around: every boundary and the implementation behind it.
 *
 * Both participants, not just the abstraction. The implementation was already labelled by
 * `reviewAtlasNodes` and the label never appeared, because nothing ever asked the atlas for
 * that node — a boundary and the single class behind it are the two halves of the finding, and
 * a map that drew one of them was drawing half of it.
 *
 * Sorted, so the same review asks the same question however its findings are ordered, and
 * deduplicated because a class can implement two of the boundaries examined.
 */
export function reviewContextNodeIds(boundaries: ReviewedBoundary[]): string[] {
  const wanted = (index: 0 | 1) =>
    boundaries
      .map((item) => item.candidate.participants[index]?.node_id)
      .filter((id): id is string => Boolean(id));
  // Every boundary before any implementation, because the route takes forty ids at a time and
  // a sweep large enough to reach that limit should still have all of its verdicts on the map.
  // The implementations then fill whatever room is left; the rest are a click away as
  // "implementations" from the boundary they sit behind.
  return [...new Set([...wanted(0), ...wanted(1)])].slice(0, 40).sort();
}

/**
 * Which node is selected is the page's business, not this component's: a finding above can
 * ask the map to show its boundary, so the two have to agree on one answer rather than each
 * keeping their own. `onOpenFinding` is the same arrangement in the other direction.
 */
export function ReviewAtlas({
  repositoryRoot,
  boundaries,
  selectedNodeId,
  onSelectNode,
  onOpenFinding,
}: {
  repositoryRoot: string;
  boundaries: ReviewedBoundary[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  /** Where the finding about a node is written, for the nodes a verdict was written about. */
  onOpenFinding?: (nodeId: string) => void;
}) {
  const client = useQueryClient();
  /* Which node a traced path runs from. Local, because it is a half-finished gesture rather
     than a fact about the review: the reader picks a start, then picks an end. */
  const [pathStartNodeId, setPathStartNodeId] = useState<string | null>(null);

  const nodeIds = useMemo(() => reviewContextNodeIds(boundaries), [boundaries]);

  // One request for the whole neighbourhood, which is what makes the map about this review.
  // It was one inspection per boundary, and their neighbourhoods overlap almost entirely —
  // the same packages and the same edges fetched once per finding, with one loading state
  // each. Missing ids are skipped by the route, so a since-reindexed repository draws what
  // survived rather than failing.
  const context = useQuery({
    queryKey: ["review-context", repositoryRoot, nodeIds],
    queryFn: () => api.reviewContext(repositoryRoot, nodeIds),
    enabled: nodeIds.length > 0,
  });

  /**
   * What the reader has explored from this map, kept as the requests that produced it.
   *
   * In the query cache rather than in component state, because state does not survive leaving
   * the page: the inspections stayed cached across a navigation while every path traced, cycle
   * surfaced and term searched was thrown away, so coming back to the map lost the reading and
   * kept the bill. Requests and not results — a request is small, comparable and replayable,
   * and holding the results is what the cache is for.
   */
  const exploredKey = useMemo(
    () => ["atlas-explored", repositoryRoot, nodeIds],
    [repositoryRoot, nodeIds],
  );
  const explored = useQuery({
    queryKey: exploredKey,
    // Never fetched. This query is somewhere to keep a list, and its answer before anyone has
    // explored anything is that nothing has been.
    queryFn: () => [] as AtlasExploreRequest[],
    initialData: [] as AtlasExploreRequest[],
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const explore = (request: AtlasExploreRequest) => {
    client.setQueryData<AtlasExploreRequest[]>(exploredKey, (current = []) => [
      // The same question asked twice replaces its earlier answer instead of standing beside
      // it: two identical explorations are one exploration.
      ...current.filter((item) => JSON.stringify(item) !== JSON.stringify(request)),
      request,
    ]);
  };
  const explorations = useQueries({
    queries: explored.data.map((request) => ({
      queryKey: ["repository-explore", request],
      queryFn: () => api.repositoryExplore(request),
      // The atlas this review pinned is immutable, so an exploration of it is answered once
      // and then kept — for as long as the list that names it is kept.
      staleTime: Infinity,
      gcTime: Infinity,
    })),
  });

  /* `useQueries` returns a new array on every render, so the map is memoised against the list
     of explorations and which of them have answered rather than against the array holding
     them — laying the graph out is the expensive part of this page, and doing it again on every
     keystroke in the map's own search box would show. */
  const answered = explorations.map((query) => (query.data ? "1" : "0")).join("");
  const results = useMemo(
    () => [
      ...(context.data ? [context.data] : []),
      ...explorations.flatMap((query) => (query.data ? [query.data] : [])),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [context.data, explored.data, answered],
  );
  const nodes = useMemo(() => reviewAtlasNodes(results, boundaries), [results, boundaries]);
  const edges = useMemo(() => reviewAtlasEdges(results, nodes), [results, nodes]);

  /**
   * The path the reader last asked for, as the two sets the map draws it with.
   *
   * What is drawn is read off the answer rather than tracked beside it: the route returns the
   * nodes and the relationships of the path it found, and a page keeping its own copy of that
   * would be able to disagree with the thing it is drawing. Which answer is the path is found
   * by the request instead — those are ours, so matching on one cannot drift the way matching
   * on the server's echo of it could.
   */
  const traced = useMemo(() => {
    const requests = explored.data;
    for (let index = requests.length - 1; index >= 0; index -= 1) {
      if (requests[index].operation === "shortest_path") return explorations[index]?.data;
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explored.data, answered]);
  const highlightedNodeIds = useMemo(() => traced?.node_ids || [], [traced]);
  const highlightedEdgeIds = useMemo(
    () => (traced?.relationships || []).map((edge) => edge.edge_id),
    [traced],
  );

  const failed = context.error || explorations.find((query) => query.error)?.error;
  const loading = context.isLoading || explorations.some((query) => query.isLoading);

  return (
    <section
      data-slot="review-atlas"
      className="mb-10"
      aria-label="Where these boundaries sit"
    >
      <h2 className="m-0 mb-1 flex items-center gap-2 border-b border-rule pb-3 text-sub tracking-[-.01em]">
        Where these boundaries sit
      </h2>
      <p className="m-0 mb-3 text-body text-ink-2">
        The same atlas the review was judged against, drawn around the boundaries it
        examined. Selecting one shows its verdict beside the map; the arrows are what the
        parser found, not what the model said.
      </p>
      {failed ? <ErrorPanel error={failed} /> : null}
      <RepositoryAtlas
        title={`${repositoryRoot.split("/").at(-1)} atlas`}
        description="Nodes carry this review's verdicts; everything else is the parser's own evidence."
        nodes={nodes}
        edges={edges}
        loading={loading}
        emptyMessage="This review's boundaries are no longer in the indexed atlas."
        // A review's neighbourhood is nearly all dependency edges — imports, calls, one class
        // implementing one interface — and the structural lens draws containment only, so
        // opening on it showed a scatter of unconnected nodes.
        initialLens="dependencies"
        legendLabels={VERDICT_LEGEND}
        onOpenFinding={onOpenFinding}
        selectedNodeId={selectedNodeId}
        // Selecting a node used to set the location hash, which threw the reader back up
        // the page to the finding — away from the map they had just started reading. The
        // verdict is already on the node and in the detail panel beside it, so a click can
        // simply answer where it was made.
        onSelectNode={onSelectNode}
        onExploreNode={(nodeId, operation, depth) =>
          explore({
            root_path: repositoryRoot,
            operation,
            node_id: nodeId,
            depth: depth ?? 1,
            limit: 60,
          })
        }
        onExploreAtlas={(operation) =>
          explore({ root_path: repositoryRoot, operation, limit: 60 })
        }
        pathStartNodeId={pathStartNodeId}
        onSetPathStart={setPathStartNodeId}
        onTracePath={(targetNodeId) => {
          if (!pathStartNodeId) return;
          explore({
            root_path: repositoryRoot,
            operation: "shortest_path",
            node_id: pathStartNodeId,
            target_id: targetNodeId,
            limit: 60,
          });
        }}
        highlightedNodeIds={highlightedNodeIds}
        highlightedEdgeIds={highlightedEdgeIds}
        onSearch={(term) =>
          explore({
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
