import type { AtlasEdgeView, AtlasLens, AtlasNodeView } from "./graph";

export type VisibleGraph = {
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
};

/**
 * The graph the canvas actually draws.
 *
 * The lens decides which relationships are the subject — containment, dependency, or what a
 * finding was made about — and the filters take out what the reader has asked not to see. The
 * selected node survives all of it: a filter that hid the card the reader just clicked would
 * answer a question by removing it.
 */
export function visibleGraphFor({
  nodes,
  edges,
  lens,
  hiddenEdgeKinds,
  hideTests,
  publicOnly,
  selected,
  revealed,
}: {
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
  lens: AtlasLens;
  hiddenEdgeKinds: Set<string>;
  hideTests: boolean;
  publicOnly: boolean;
  selected: AtlasNodeView | undefined;
  /**
   * Elements the reader explicitly asked the atlas for, which no lens or filter may hide.
   *
   * The same rule the selection gets, for the same reason: answering a request by not
   * drawing what came back is not an answer. Exploring "implementations" and watching the
   * map stay exactly as it was is how a working feature reads as a broken button.
   */
  revealed?: Set<string>;
}): VisibleGraph {
  const kept = (node: AtlasNodeView) => node.id === selected?.id || Boolean(revealed?.has(node.id));
  const nodeAllowed = (node: AtlasNodeView) => {
    if (kept(node)) return true;
    if (hideTests && node.kind.includes("test")) return false;
    if (publicOnly && node.isPublic === false) return false;
    return true;
  };
  const allowedNodes = nodes.filter(nodeAllowed);
  const allowedIds = new Set(allowedNodes.map((node) => node.id));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const byLens = edges.filter((edge) => {
    if (hiddenEdgeKinds.has(edge.kind)) return false;
    if (lens === "structure") return edge.kind === "contains";
    if (lens === "dependencies") return edge.kind !== "contains";
    return Boolean(byId.get(edge.sourceId)?.tone) || Boolean(byId.get(edge.targetId)?.tone);
  });
  const lensNodeIds = new Set(byLens.flatMap((edge) => [edge.sourceId, edge.targetId]));
  if (lens === "judged") {
    // A judged element with nothing drawn around it is still the point of this lens.
    nodes.filter((node) => node.tone).forEach((node) => lensNodeIds.add(node.id));
  }
  if (selected) lensNodeIds.add(selected.id);
  revealed?.forEach((id) => lensNodeIds.add(id));
  const shouldBoundNodes =
    lens === "judged" || (lens === "dependencies" && byLens.length > 0);
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
 * about which cards are on screen. Keying the placement on identity therefore re-laid out the
 * whole graph on every click, and every one of those re-layouts moved the camera.
 *
 * So the question is asked of the content instead: the lens, and the sorted ids of the visible
 * nodes and edges. Kind and tone ride along with each node id because both feed the
 * placement — `kindLevel` reads the kind, and the judged lens clusters around the elements a
 * finding was made about — and a signature that ignored them would hold a stale map after a
 * review re-judges a node.
 */
export function graphSignatureOf(lens: AtlasLens, graph: VisibleGraph): string {
  return [
    lens,
    graph.nodes
      .map((node) => `${node.id}:${node.kind}:${node.tone ?? ""}`)
      .sort()
      .join(","),
    graph.edges
      .map((edge) => edge.id)
      .sort()
      .join(","),
  ].join("|");
}
