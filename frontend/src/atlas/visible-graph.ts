/** Which nodes and relationships the current lens and filters leave on screen. */

import type { AtlasEdgeView, AtlasLens, AtlasNodeView } from "./graph-model";

export interface VisibleGraph {
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
}

/**
 * The graph the canvas actually draws.
 *
 * The lens decides which relationships are the subject — containment, dependency, or risk —
 * and the filters take out what the reader has asked not to see. The selected node survives
 * all of it: a filter that hid the card the reader just clicked would answer a question by
 * removing it.
 */
export function visibleGraphFor({
  nodes,
  edges,
  lens,
  hiddenEdgeKinds,
  hideTests,
  publicOnly,
  selected,
}: {
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
  lens: AtlasLens;
  hiddenEdgeKinds: Set<string>;
  hideTests: boolean;
  publicOnly: boolean;
  selected: AtlasNodeView | undefined;
}): VisibleGraph {
  const nodeAllowed = (node: AtlasNodeView) => {
    if (node.id === selected?.id) return true;
    if (hideTests && node.kind.includes("test")) return false;
    if (publicOnly && node.isPublic === false) return false;
    return true;
  };
  const allowedNodes = nodes.filter(nodeAllowed);
  const allowedIds = new Set(allowedNodes.map((node) => node.id));
  const byLens = edges.filter((edge) => {
    if (hiddenEdgeKinds.has(edge.kind)) return false;
    if (lens === "structure") return edge.kind === "contains";
    if (lens === "dependencies") return edge.kind !== "contains";
    const source = nodes.find((node) => node.id === edge.sourceId);
    const target = nodes.find((node) => node.id === edge.targetId);
    return edge.risk || source?.state === "hotspot" || target?.state === "hotspot";
  });
  const lensNodeIds = new Set(
    byLens.flatMap((edge) => [edge.sourceId, edge.targetId]),
  );
  if (lens === "risk") {
    nodes
      .filter((node) => node.state === "hotspot")
      .forEach((node) => lensNodeIds.add(node.id));
  }
  if (selected) lensNodeIds.add(selected.id);
  const shouldBoundNodes =
    lens === "risk" || (lens === "dependencies" && byLens.length > 0);
  const visibleNodes = allowedNodes.filter(
    (node) => !shouldBoundNodes || lensNodeIds.has(node.id),
  );
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  return {
    nodes: visibleNodes,
    edges: byLens.filter(
      (edge) =>
        allowedIds.has(edge.sourceId) &&
        allowedIds.has(edge.targetId) &&
        visibleIds.has(edge.sourceId) &&
        visibleIds.has(edge.targetId),
    ),
  };
}

/**
 * What this map is *of*, written down as one string.
 *
 * `visibleGraphFor` returns a fresh object on every selection, because the filters above keep
 * the selected node visible even when `hideTests`, `publicOnly` or the lens would drop it — so
 * `selected` has to be a dependency, and object identity cannot answer "is this the same
 * graph?". Almost always it is: clicking a card that was already on screen changes nothing
 * about which cards are on screen. Keying the placement on identity therefore re-laid out
 * the whole graph on every click, and every one of those re-layouts moved the camera.
 *
 * So the question is asked of the content instead: the lens, and the sorted ids of the
 * visible nodes and edges. Kind and state ride along with each node id because both feed
 * the placement — `kindLevel` reads the kind, and the risk lens clusters around hotspots —
 * and a signature that ignored them would hold a stale map after a review re-judges a node.
 */
export function graphSignatureOf(lens: AtlasLens, graph: VisibleGraph): string {
  return [
    lens,
    graph.nodes
      .map((node) => `${node.id}:${node.kind}:${node.state}`)
      .sort()
      .join(","),
    graph.edges.map((edge) => edge.id).sort().join(","),
  ].join("|");
}
