import type { ElkNode } from "elkjs/lib/elk-api";

import type { AtlasEdgeView, AtlasLens, AtlasNodeView } from "./graph";

/**
 * Where the atlas decides what goes where.
 *
 * Two layouts live here and they answer the same question. `layoutAtlas` is synchronous and
 * hand-rolled: it is what paints the first frame, what the tests read, and what remains when
 * the graph engine cannot be loaded. `layoutAtlasElk` hands the same graph to the Eclipse
 * Layout Kernel, which places a dense graph without the card overlap the hand-rolled
 * relaxation could never quite squeeze out. Both return the same `AtlasLayout`, and both make
 * the *same* clustering decisions — `clusterGroups` below is the one place that reads a lens
 * and says which cards belong together, so the two layouts can never disagree about what the
 * enclosures mean.
 *
 * Neither is random. Every ordering here breaks its ties on the node's own name, so the same
 * graph places identically on every machine and in every test run — the charter's promise is
 * that the same commit gives the same map, and a placement that settled differently depending
 * on how many frames it got could not keep it.
 */

export const NODE_WIDTH = 190;
export const NODE_HEIGHT = 78;
export const MIN_CANVAS_WIDTH = 920;
export const MIN_CANVAS_HEIGHT = 430;
const PADDING_X = 44;
const PADDING_Y = 42;
const ISLAND_NODE_GAP = 52;
const ISLAND_LAYER_GAP = 70;

export type AtlasLayout = {
  positions: Map<string, { x: number; y: number }>;
  width: number;
  height: number;
  levels: Map<string, number>;
  clusters: AtlasClusterRegion[];
};

export type AtlasClusterRegion = {
  id: string;
  label: string;
  nodeIds: string[];
  x: number;
  y: number;
  width: number;
  height: number;
};

function nodeOrder(node: AtlasNodeView) {
  const kindOrder: Record<string, number> = {
    repository: 0,
    package: 1,
    module: 2,
    test_module: 3,
    configuration: 4,
    class: 5,
    interface: 6,
    function: 7,
    method: 8,
    test_function: 9,
  };
  return `${String(kindOrder[node.kind] ?? 20).padStart(2, "0")}:${node.path}:${node.label}`;
}

function kindLevel(kind: string) {
  const levels: Record<string, number> = {
    repository: 0,
    package: 1,
    module: 2,
    test_module: 2,
    configuration: 2,
    class: 3,
    interface: 3,
    function: 4,
    method: 4,
    test_function: 4,
  };
  return levels[kind] ?? 2;
}

const hierarchicalEdges = new Set(["contains"]);

function emptyLayout(): AtlasLayout {
  return {
    positions: new Map(),
    width: MIN_CANVAS_WIDTH,
    height: 360,
    levels: new Map(),
    clusters: [],
  };
}

/**
 * The reading of the graph both layouts start from: which nodes are joined to which, which
 * component each belongs to, and how deep in the hierarchy each one sits.
 */
function analyseGraph(nodes: AtlasNodeView[], edges: AtlasEdgeView[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const validEdges = edges.filter(
    (edge) =>
      edge.sourceId !== edge.targetId &&
      byId.has(edge.sourceId) &&
      byId.has(edge.targetId),
  );
  const neighbours = new Map(nodes.map((node) => [node.id, new Set<string>()]));
  validEdges.forEach((edge) => {
    neighbours.get(edge.sourceId)?.add(edge.targetId);
    neighbours.get(edge.targetId)?.add(edge.sourceId);
  });

  const components: string[][] = [];
  const visited = new Set<string>();
  for (const node of [...nodes].sort((a, b) => nodeOrder(a).localeCompare(nodeOrder(b)))) {
    if (visited.has(node.id)) continue;
    const component: string[] = [];
    const queue = [node.id];
    visited.add(node.id);
    while (queue.length) {
      const current = queue.shift()!;
      component.push(current);
      for (const neighbour of neighbours.get(current) || []) {
        if (!visited.has(neighbour)) {
          visited.add(neighbour);
          queue.push(neighbour);
        }
      }
    }
    components.push(component);
  }
  components.sort((left, right) => {
    if (left.length !== right.length) return right.length - left.length;
    return nodeOrder(byId.get(left[0])!).localeCompare(nodeOrder(byId.get(right[0])!));
  });
  const componentByNode = new Map<string, number>();
  components.forEach((component, index) =>
    component.forEach((nodeId) => componentByNode.set(nodeId, index)),
  );

  const levels = new Map(nodes.map((node) => [node.id, kindLevel(node.kind)]));
  for (let iteration = 0; iteration < nodes.length; iteration += 1) {
    let changed = false;
    for (const edge of validEdges) {
      if (!hierarchicalEdges.has(edge.kind)) continue;
      const next = Math.max(levels.get(edge.targetId) || 0, (levels.get(edge.sourceId) || 0) + 1);
      if (next !== levels.get(edge.targetId)) {
        levels.set(edge.targetId, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  // A homogeneous component has no type hierarchy to guide it. Use graph distance from its
  // most connected node so topology still determines placement.
  components.forEach((component) => {
    if (component.length < 2) return;
    const distinctLevels = new Set(component.map((nodeId) => levels.get(nodeId)));
    const hasHierarchy = validEdges.some(
      (edge) =>
        componentByNode.get(edge.sourceId) === componentByNode.get(component[0]) &&
        hierarchicalEdges.has(edge.kind),
    );
    if (distinctLevels.size > 1 || hasHierarchy) return;
    const root = [...component].sort((left, right) => {
      const degree = (neighbours.get(right)?.size || 0) - (neighbours.get(left)?.size || 0);
      return degree || nodeOrder(byId.get(left)!).localeCompare(nodeOrder(byId.get(right)!));
    })[0];
    const base = levels.get(root) || 0;
    const distance = new Map([[root, 0]]);
    const queue = [root];
    while (queue.length) {
      const current = queue.shift()!;
      for (const neighbour of neighbours.get(current) || []) {
        if (!distance.has(neighbour)) {
          distance.set(neighbour, (distance.get(current) || 0) + 1);
          queue.push(neighbour);
        }
      }
    }
    component.forEach((nodeId) => levels.set(nodeId, base + (distance.get(nodeId) || 0)));
  });

  return { byId, validEdges, neighbours, componentByNode, levels };
}

/**
 * Which cards belong together, and in what order the groups are read.
 *
 * Shared by both layouts so an enclosure means the same thing whichever placed the cards. A
 * repository is never in a group: it is the thing the groups hang beneath.
 */
function clusterGroups(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  byId: Map<string, AtlasNodeView>,
  lens: AtlasLens,
) {
  const roots = new Set(
    nodes.filter((node) => node.kind === "repository").map((node) => node.id),
  );
  const hasStructuralRelationships = edges.some((edge) => hierarchicalEdges.has(edge.kind));
  const clusterByNode =
    lens === "structure" && hasStructuralRelationships
      ? structuralClusters(nodes, edges, roots)
      : graphClusters(nodes, edges, roots, lens);
  const groups = new Map<string, AtlasNodeView[]>();
  nodes
    .filter((node) => !roots.has(node.id))
    .forEach((node) => {
      const clusterId = clusterByNode.get(node.id) || node.id;
      groups.set(clusterId, [...(groups.get(clusterId) || []), node]);
    });
  const orderedGroups = [...groups.entries()].sort(([leftId, left], [rightId, right]) => {
    return (
      right.length - left.length ||
      nodeOrder(byId.get(leftId) || left[0]).localeCompare(
        nodeOrder(byId.get(rightId) || right[0]),
      )
    );
  });
  return { roots, clusterByNode, orderedGroups };
}

/**
 * The order both layouts read the graph in, and the reason either is reproducible.
 *
 * Two passes below mutate as they walk — the collision sweep moves a card the moment it finds
 * an overlap, and ELK's `considerModelOrder` reads the order it is handed — so the order the
 * caller happened to build its array in would otherwise be visible in the finished map. It
 * was: the same graph with its nodes reversed placed differently, which is the one thing the
 * charter's "the same commit gives the same map" cannot survive.
 *
 * The order itself is the hierarchy, swept: nodes by level, and within a level the repeated
 * barycentric passes that pull a child towards its connected parents. Every tie in it breaks
 * on the node's own name, so the result is a function of the graph and nothing else.
 *
 * This work used to be done and discarded. The sweeps sorted arrays inside a `layers` map that
 * nothing downstream ever read, and the placement went on to use the caller's array — so the
 * crossing reduction these four passes exist for was not being applied at all.
 */
function canonicalOrder(
  nodes: AtlasNodeView[],
  neighbours: Map<string, Set<string>>,
  componentByNode: Map<string, number>,
  levels: Map<string, number>,
): AtlasNodeView[] {
  const layers = new Map<number, AtlasNodeView[]>();
  nodes.forEach((node) => {
    const level = levels.get(node.id) || 0;
    layers.set(level, [...(layers.get(level) || []), node]);
  });
  const orderedLevels = [...layers.keys()].sort((a, b) => a - b);
  orderedLevels.forEach((level) =>
    layers.get(level)!.sort((left, right) => {
      const componentDifference =
        (componentByNode.get(left.id) || 0) - (componentByNode.get(right.id) || 0);
      return componentDifference || nodeOrder(left).localeCompare(nodeOrder(right));
    }),
  );

  // Repeated barycentric sweeps pull children underneath their connected parents and reduce
  // edge crossings without a non-deterministic force layout.
  for (let pass = 0; pass < 4; pass += 1) {
    const sweep = pass % 2 === 0 ? orderedLevels : [...orderedLevels].reverse();
    const indexByNode = new Map<string, number>();
    layers.forEach((layer) => layer.forEach((node, index) => indexByNode.set(node.id, index)));
    for (const level of sweep) {
      layers.get(level)!.sort((left, right) => {
        const leftComponent = componentByNode.get(left.id) || 0;
        const rightComponent = componentByNode.get(right.id) || 0;
        if (leftComponent !== rightComponent) return leftComponent - rightComponent;
        const score = (node: AtlasNodeView) => {
          const connected = [...(neighbours.get(node.id) || [])].filter(
            (nodeId) => levels.get(nodeId) !== level,
          );
          if (!connected.length) return indexByNode.get(node.id) || 0;
          return (
            connected.reduce((sum, nodeId) => sum + (indexByNode.get(nodeId) || 0), 0) /
            connected.length
          );
        };
        const difference = score(left) - score(right);
        return difference || nodeOrder(left).localeCompare(nodeOrder(right));
      });
    }
  }

  return orderedLevels.flatMap((level) => layers.get(level)!);
}

/**
 * What an enclosure is called.
 *
 * Two cases, and the difference between them is whether the box is a container or a
 * neighbourhood.
 *
 * The structural lens builds a box from something that really does contain its members — a
 * package — and the box takes that thing's name. The test is the containment itself rather
 * than which lens asked: every member sits under the cluster node's own qualified name.
 *
 * The other two lenses build a community out of graph distance, and its members can share
 * nothing but the repository. Naming such a box after the deepest prefix they happen to share
 * put the repository's own name on three boxes at once, which says nothing three times; naming
 * it after the element the clustering grew from reads as a claim that the box holds that thing
 * and its parts. So it is named for what it actually is — the neighbourhood around that
 * element — and that element is inside the box, which is what makes the name findable rather
 * than merely true.
 */
function clusterLabel(
  group: AtlasNodeView[],
  byId: Map<string, AtlasNodeView>,
  clusterId: string,
): string {
  const container = byId.get(clusterId);
  const contains =
    container &&
    group.every(
      (node) =>
        node.id === clusterId || node.qualified.startsWith(`${container.qualified}.`),
    );
  if (contains) return container.label;
  return `around ${(container || group[0]).label}`;
}

export function layoutAtlas(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[] = [],
  lens: AtlasLens = "structure",
): AtlasLayout {
  if (!nodes.length) return emptyLayout();
  const { byId, validEdges, neighbours, componentByNode, levels } = analyseGraph(nodes, edges);
  const ordered = canonicalOrder(nodes, neighbours, componentByNode, levels);
  return clusterLayout(ordered, validEdges, levels, byId, lens);
}

function clusterLayout(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  levels: Map<string, number>,
  byId: Map<string, AtlasNodeView>,
  lens: AtlasLens,
): AtlasLayout {
  const { roots, clusterByNode, orderedGroups } = clusterGroups(nodes, edges, byId, lens);
  const columns = Math.max(1, Math.ceil(Math.sqrt(orderedGroups.length)));
  const cellWidth = 510;
  const cellHeight = 370;
  const rootBand = roots.size ? 170 : 30;
  // Only a width. The height the canvas ends up with is measured from where the cards
  // actually settled, several passes below — a starting guess at it was computed here and
  // never read, which is exactly the sort of number that later reads as authoritative.
  const initialWidth = Math.max(MIN_CANVAS_WIDTH, columns * cellWidth + PADDING_X * 2);
  const positions = new Map<string, { x: number; y: number }>();
  const clusterTargets = new Map<string, { x: number; y: number }>();
  [...roots].sort().forEach((nodeId, index, rootIds) => {
    positions.set(nodeId, {
      x:
        initialWidth / 2 +
        (index - (rootIds.length - 1) / 2) * (NODE_WIDTH + 34) -
        NODE_WIDTH / 2,
      y: PADDING_Y,
    });
  });
  orderedGroups.forEach(([clusterId, group], groupIndex) => {
    const column = groupIndex % columns;
    const row = Math.floor(groupIndex / columns);
    const center = {
      x: PADDING_X + column * cellWidth + cellWidth / 2,
      y: rootBand + PADDING_Y + row * cellHeight + cellHeight / 2,
    };
    clusterTargets.set(clusterId, center);
    positionIsland(group, edges, levels, center, positions, lens);
  });

  relaxClusters(nodes, edges, positions, clusterByNode, clusterTargets, roots, levels, lens);
  resolveNodeCollisions(nodes, positions, roots);
  separateClusterRegions(orderedGroups, positions, 86);
  resolveNodeCollisions(nodes, positions, roots);

  const minimumX = Math.min(...nodes.map((node) => positions.get(node.id)!.x));
  const minimumY = Math.min(...nodes.map((node) => positions.get(node.id)!.y));
  const shiftX = minimumX < PADDING_X ? PADDING_X - minimumX : 0;
  const shiftY = minimumY < PADDING_Y ? PADDING_Y - minimumY : 0;
  positions.forEach((position) => {
    position.x += shiftX;
    position.y += shiftY;
  });
  const maximumX = Math.max(...nodes.map((node) => positions.get(node.id)!.x + NODE_WIDTH));
  const maximumY = Math.max(...nodes.map((node) => positions.get(node.id)!.y + NODE_HEIGHT));
  const width = Math.max(MIN_CANVAS_WIDTH, maximumX + PADDING_X);
  const height = Math.max(MIN_CANVAS_HEIGHT, maximumY + PADDING_Y);
  const clusters: AtlasClusterRegion[] = orderedGroups
    .filter(([, group]) => group.length > 1)
    .map(([clusterId, group]) => {
      const groupPositions = group.map((node) => positions.get(node.id)!);
      const x = Math.min(...groupPositions.map((position) => position.x)) - 28;
      const y = Math.min(...groupPositions.map((position) => position.y)) - 35;
      const right = Math.max(...groupPositions.map((position) => position.x + NODE_WIDTH)) + 28;
      const bottom = Math.max(...groupPositions.map((position) => position.y + NODE_HEIGHT)) + 28;
      return {
        id: clusterId,
        label: clusterLabel(group, byId, clusterId),
        nodeIds: group.map((node) => node.id),
        x,
        y,
        width: right - x,
        height: bottom - y,
      };
    });
  return { positions, width, height, levels, clusters };
}

function positionIsland(
  group: AtlasNodeView[],
  edges: AtlasEdgeView[],
  levels: Map<string, number>,
  center: { x: number; y: number },
  positions: Map<string, { x: number; y: number }>,
  lens: AtlasLens,
) {
  if (lens === "structure") {
    positionLayeredIsland(group, edges, levels, center, positions);
    return;
  }
  positionTopologicalIsland(group, edges, center, positions, lens);
}

/**
 * Place a structural island as a compact Sugiyama-style hierarchy. Repeated barycentric
 * sweeps keep a child close to its connected parent and reduce crossings before the
 * constrained relaxation pass fine-tunes the result.
 */
function positionLayeredIsland(
  group: AtlasNodeView[],
  edges: AtlasEdgeView[],
  levels: Map<string, number>,
  center: { x: number; y: number },
  positions: Map<string, { x: number; y: number }>,
) {
  const groupIds = new Set(group.map((node) => node.id));
  const internalEdges = edges.filter(
    (edge) => groupIds.has(edge.sourceId) && groupIds.has(edge.targetId),
  );
  const neighbours = new Map(group.map((node) => [node.id, new Set<string>()]));
  internalEdges.forEach((edge) => {
    neighbours.get(edge.sourceId)?.add(edge.targetId);
    neighbours.get(edge.targetId)?.add(edge.sourceId);
  });
  const layers = new Map<number, AtlasNodeView[]>();
  group.forEach((node) => {
    const level = levels.get(node.id) || 0;
    layers.set(level, [...(layers.get(level) || []), node]);
  });
  const orderedLevels = [...layers.keys()].sort((left, right) => left - right);
  orderedLevels.forEach((level) =>
    layers.get(level)!.sort((left, right) => nodeOrder(left).localeCompare(nodeOrder(right))),
  );

  for (let pass = 0; pass < 8; pass += 1) {
    const levelOrder = pass % 2 === 0 ? orderedLevels : [...orderedLevels].reverse();
    const rank = new Map<string, number>();
    orderedLevels.forEach((level) => {
      const layer = layers.get(level)!;
      layer.forEach((node, index) => {
        rank.set(node.id, layer.length === 1 ? 0.5 : index / (layer.length - 1));
      });
    });
    levelOrder.forEach((level) => {
      const layer = layers.get(level)!;
      layer.sort((left, right) => {
        const barycenter = (node: AtlasNodeView) => {
          const connected = [...(neighbours.get(node.id) || [])].filter(
            (nodeId) => levels.get(nodeId) !== level,
          );
          if (!connected.length) return rank.get(node.id) || 0;
          return (
            connected.reduce((sum, nodeId) => sum + (rank.get(nodeId) ?? 0.5), 0) /
            connected.length
          );
        };
        return (
          barycenter(left) - barycenter(right) ||
          nodeOrder(left).localeCompare(nodeOrder(right))
        );
      });
    });
  }

  const layerStep = NODE_HEIGHT + ISLAND_LAYER_GAP;
  const top = center.y - ((orderedLevels.length - 1) * layerStep + NODE_HEIGHT) / 2;
  orderedLevels.forEach((level, levelIndex) => {
    const layer = layers.get(level)!;
    const nodeStep = NODE_WIDTH + ISLAND_NODE_GAP;
    const left = center.x - ((layer.length - 1) * nodeStep + NODE_WIDTH) / 2;
    layer.forEach((node, nodeIndex) => {
      positions.set(node.id, {
        x: left + nodeIndex * nodeStep,
        y: top + levelIndex * layerStep,
      });
    });
  });
}

/**
 * Dependency and judged islands use graph distance from a meaningful hub. This keeps
 * immediate neighbours visually close while preserving a less rigid, radial character than
 * the structural lens.
 */
function positionTopologicalIsland(
  group: AtlasNodeView[],
  edges: AtlasEdgeView[],
  center: { x: number; y: number },
  positions: Map<string, { x: number; y: number }>,
  lens: AtlasLens,
) {
  const groupIds = new Set(group.map((node) => node.id));
  const neighbours = new Map(group.map((node) => [node.id, new Set<string>()]));
  edges.forEach((edge) => {
    if (!groupIds.has(edge.sourceId) || !groupIds.has(edge.targetId)) return;
    neighbours.get(edge.sourceId)?.add(edge.targetId);
    neighbours.get(edge.targetId)?.add(edge.sourceId);
  });
  const hub = [...group].sort((left, right) => {
    // In the judged lens the element a finding was made about is the thing the island is
    // about, so it holds the middle and its neighbourhood rings out from it.
    if (lens === "judged" && Boolean(left.tone) !== Boolean(right.tone)) {
      return left.tone ? -1 : 1;
    }
    return (
      (neighbours.get(right.id)?.size || 0) - (neighbours.get(left.id)?.size || 0) ||
      nodeOrder(left).localeCompare(nodeOrder(right))
    );
  })[0];
  const distanceFromHub = new Map([[hub.id, 0]]);
  const queue = [hub.id];
  while (queue.length) {
    const current = queue.shift()!;
    for (const neighbour of neighbours.get(current) || []) {
      if (distanceFromHub.has(neighbour)) continue;
      distanceFromHub.set(neighbour, (distanceFromHub.get(current) || 0) + 1);
      queue.push(neighbour);
    }
  }
  const furthest = Math.max(0, ...distanceFromHub.values());
  const rings = new Map<number, AtlasNodeView[]>();
  group.forEach((node) => {
    const ring = distanceFromHub.get(node.id) ?? furthest + 1;
    rings.set(ring, [...(rings.get(ring) || []), node]);
  });
  rings.forEach((ringNodes, ring) => {
    ringNodes.sort((left, right) => {
      const degreeDifference =
        (neighbours.get(right.id)?.size || 0) - (neighbours.get(left.id)?.size || 0);
      return degreeDifference || nodeOrder(left).localeCompare(nodeOrder(right));
    });
    if (ring === 0) {
      positions.set(ringNodes[0].id, {
        x: center.x - NODE_WIDTH / 2,
        y: center.y - NODE_HEIGHT / 2,
      });
      return;
    }
    const circumferenceRadius =
      (ringNodes.length * (NODE_WIDTH + ISLAND_NODE_GAP)) / (2 * Math.PI);
    const radiusX = Math.max(165 * ring, circumferenceRadius);
    const radiusY = Math.max(110 * ring, radiusX * 0.62);
    ringNodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + index * ((2 * Math.PI) / ringNodes.length);
      positions.set(node.id, {
        x: center.x + Math.cos(angle) * radiusX - NODE_WIDTH / 2,
        y: center.y + Math.sin(angle) * radiusY - NODE_HEIGHT / 2,
      });
    });
  });
}

function separateClusterRegions(
  groups: Array<[string, AtlasNodeView[]]>,
  positions: Map<string, { x: number; y: number }>,
  gap: number,
) {
  const bounds = (group: AtlasNodeView[]) => {
    const groupPositions = group.map((node) => positions.get(node.id)!);
    return {
      left: Math.min(...groupPositions.map((position) => position.x)),
      top: Math.min(...groupPositions.map((position) => position.y)),
      right: Math.max(...groupPositions.map((position) => position.x + NODE_WIDTH)),
      bottom: Math.max(...groupPositions.map((position) => position.y + NODE_HEIGHT)),
    };
  };
  const translate = (group: AtlasNodeView[], x: number, y: number) => {
    group.forEach((node) => {
      const position = positions.get(node.id)!;
      position.x += x;
      position.y += y;
    });
  };
  for (let pass = 0; pass < 14; pass += 1) {
    let moved = false;
    for (let leftIndex = 0; leftIndex < groups.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < groups.length; rightIndex += 1) {
        const leftGroup = groups[leftIndex][1];
        const rightGroup = groups[rightIndex][1];
        const left = bounds(leftGroup);
        const right = bounds(rightGroup);
        const overlapX =
          Math.min(left.right + gap, right.right + gap) - Math.max(left.left, right.left);
        const overlapY =
          Math.min(left.bottom + gap, right.bottom + gap) - Math.max(left.top, right.top);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        const leftCenterX = (left.left + left.right) / 2;
        const rightCenterX = (right.left + right.right) / 2;
        const leftCenterY = (left.top + left.bottom) / 2;
        const rightCenterY = (right.top + right.bottom) / 2;
        if (overlapX < overlapY) {
          const direction = rightCenterX >= leftCenterX ? 1 : -1;
          translate(leftGroup, (-direction * overlapX) / 2, 0);
          translate(rightGroup, (direction * overlapX) / 2, 0);
        } else {
          const direction = rightCenterY >= leftCenterY ? 1 : -1;
          translate(leftGroup, 0, (-direction * overlapY) / 2);
          translate(rightGroup, 0, (direction * overlapY) / 2);
        }
      }
    }
    if (!moved) break;
  }
}

function structuralClusters(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  roots: Set<string>,
) {
  const parent = new Map(
    edges
      .filter((edge) => hierarchicalEdges.has(edge.kind))
      .map((edge) => [edge.targetId, edge.sourceId]),
  );
  const result = new Map<string, string>();
  nodes.forEach((node) => {
    if (roots.has(node.id)) {
      result.set(node.id, node.id);
      return;
    }
    let clusterId = node.id;
    let cursor = node.id;
    const seen = new Set<string>();
    while (parent.has(cursor) && !seen.has(cursor)) {
      seen.add(cursor);
      const next = parent.get(cursor)!;
      if (roots.has(next)) break;
      clusterId = next;
      cursor = next;
    }
    result.set(node.id, clusterId);
  });
  return result;
}

function graphClusters(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  roots: Set<string>,
  lens: AtlasLens,
) {
  const candidates = nodes.filter((node) => !roots.has(node.id));
  const neighbours = new Map(candidates.map((node) => [node.id, new Set<string>()]));
  edges.forEach((edge) => {
    neighbours.get(edge.sourceId)?.add(edge.targetId);
    neighbours.get(edge.targetId)?.add(edge.sourceId);
  });
  if (!candidates.length) return new Map<string, string>();
  const targetCount = Math.min(6, Math.max(1, Math.round(Math.sqrt(candidates.length / 4))));
  const ranked = [...candidates].sort((left, right) => {
    if (lens === "judged" && Boolean(left.tone) !== Boolean(right.tone)) {
      return left.tone ? -1 : 1;
    }
    return (
      (neighbours.get(right.id)?.size || 0) - (neighbours.get(left.id)?.size || 0) ||
      nodeOrder(left).localeCompare(nodeOrder(right))
    );
  });
  const seeds = [ranked[0].id];
  const distances = new Map<string, Map<string, number>>();
  const distanceFrom = (seed: string) => {
    if (distances.has(seed)) return distances.get(seed)!;
    const distance = new Map([[seed, 0]]);
    const queue = [seed];
    while (queue.length) {
      const current = queue.shift()!;
      for (const neighbour of neighbours.get(current) || []) {
        if (!distance.has(neighbour)) {
          distance.set(neighbour, (distance.get(current) || 0) + 1);
          queue.push(neighbour);
        }
      }
    }
    distances.set(seed, distance);
    return distance;
  };
  while (seeds.length < targetCount) {
    const next = candidates
      .filter((node) => !seeds.includes(node.id))
      .sort((left, right) => {
        const score = (nodeId: string) =>
          Math.min(...seeds.map((seed) => distanceFrom(seed).get(nodeId) ?? 1_000));
        return (
          score(right.id) - score(left.id) || nodeOrder(left).localeCompare(nodeOrder(right))
        );
      })[0];
    if (!next) break;
    seeds.push(next.id);
  }
  return new Map(
    candidates.map((node) => {
      const seed = [...seeds].sort((left, right) => {
        const difference =
          (distanceFrom(left).get(node.id) ?? 1_000) - (distanceFrom(right).get(node.id) ?? 1_000);
        return difference || left.localeCompare(right);
      })[0];
      return [node.id, seed];
    }),
  );
}

function relaxClusters(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  positions: Map<string, { x: number; y: number }>,
  clusterByNode: Map<string, string>,
  clusterTargets: Map<string, { x: number; y: number }>,
  roots: Set<string>,
  levels: Map<string, number>,
  lens: AtlasLens,
) {
  const velocity = new Map(nodes.map((node) => [node.id, { x: 0, y: 0 }]));
  const clusterMembers = new Map<string, AtlasNodeView[]>();
  nodes.forEach((node) => {
    const clusterId = clusterByNode.get(node.id) || node.id;
    clusterMembers.set(clusterId, [...(clusterMembers.get(clusterId) || []), node]);
  });
  const structuralTargetY = new Map<string, number>();
  if (lens === "structure") {
    clusterMembers.forEach((members, clusterId) => {
      const target = clusterTargets.get(clusterId);
      if (!target) return;
      const groupLevels = [...new Set(members.map((node) => levels.get(node.id) || 0))].sort(
        (left, right) => left - right,
      );
      members.forEach((node) => {
        const levelIndex = groupLevels.indexOf(levels.get(node.id) || 0);
        structuralTargetY.set(
          node.id,
          target.y +
            (levelIndex - (groupLevels.length - 1) / 2) * (NODE_HEIGHT + ISLAND_LAYER_GAP),
        );
      });
    });
  }
  for (let iteration = 0; iteration < 120; iteration += 1) {
    const cooling = 1 - iteration / 150;
    nodes.forEach((node) => {
      if (roots.has(node.id)) return;
      const position = positions.get(node.id)!;
      const target = clusterTargets.get(clusterByNode.get(node.id) || "");
      const movement = velocity.get(node.id)!;
      if (target) {
        movement.x += (target.x - (position.x + NODE_WIDTH / 2)) * 0.008;
        movement.y += (target.y - (position.y + NODE_HEIGHT / 2)) * 0.008;
        if (lens === "structure") {
          const targetY = structuralTargetY.get(node.id) || target.y;
          movement.y += (targetY - (position.y + NODE_HEIGHT / 2)) * 0.022;
        }
      }
    });
    edges.forEach((edge) => {
      if (clusterByNode.get(edge.sourceId) !== clusterByNode.get(edge.targetId)) return;
      const source = positions.get(edge.sourceId);
      const target = positions.get(edge.targetId);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const ideal = hierarchicalEdges.has(edge.kind) ? 135 : 190;
      const force = (distance - ideal) * 0.012;
      const x = (dx / distance) * force;
      const y = (dy / distance) * force;
      if (!roots.has(edge.sourceId)) {
        velocity.get(edge.sourceId)!.x += x;
        velocity.get(edge.sourceId)!.y += y;
      }
      if (!roots.has(edge.targetId)) {
        velocity.get(edge.targetId)!.x -= x;
        velocity.get(edge.targetId)!.y -= y;
      }
    });
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const left = nodes[leftIndex];
        const right = nodes[rightIndex];
        const leftPosition = positions.get(left.id)!;
        const rightPosition = positions.get(right.id)!;
        let dx = rightPosition.x - leftPosition.x;
        let dy = rightPosition.y - leftPosition.y;
        if (!dx && !dy) {
          dx = left.id.localeCompare(right.id) < 0 ? 1 : -1;
          dy = 1;
        }
        const distance = Math.max(1, Math.hypot(dx, dy));
        if (clusterByNode.get(left.id) !== clusterByNode.get(right.id)) continue;
        const minimum = 178;
        if (distance >= minimum) continue;
        const force = (minimum - distance) * 0.018;
        const x = (dx / distance) * force;
        const y = (dy / distance) * force;
        if (!roots.has(left.id)) {
          velocity.get(left.id)!.x -= x;
          velocity.get(left.id)!.y -= y;
        }
        if (!roots.has(right.id)) {
          velocity.get(right.id)!.x += x;
          velocity.get(right.id)!.y += y;
        }
      }
    }
    nodes.forEach((node) => {
      if (roots.has(node.id)) return;
      const movement = velocity.get(node.id)!;
      const magnitude = Math.max(1, Math.hypot(movement.x, movement.y));
      const limit = 12 * cooling;
      const position = positions.get(node.id)!;
      position.x += (movement.x / magnitude) * Math.min(magnitude, limit);
      position.y += (movement.y / magnitude) * Math.min(magnitude, limit);
      movement.x *= 0.68;
      movement.y *= 0.68;
    });
  }
}

function resolveNodeCollisions(
  nodes: AtlasNodeView[],
  positions: Map<string, { x: number; y: number }>,
  roots: Set<string>,
) {
  for (let pass = 0; pass < 12; pass += 1) {
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const left = nodes[leftIndex];
        const right = nodes[rightIndex];
        const leftPosition = positions.get(left.id)!;
        const rightPosition = positions.get(right.id)!;
        const dx = rightPosition.x - leftPosition.x;
        const dy = rightPosition.y - leftPosition.y;
        const overlapX = NODE_WIDTH + 24 - Math.abs(dx);
        const overlapY = NODE_HEIGHT + 24 - Math.abs(dy);
        if (overlapX <= 0 || overlapY <= 0) continue;
        const moveLeft = roots.has(left.id) ? 0 : 0.5;
        const moveRight = roots.has(right.id) ? 0 : 0.5;
        if (overlapX < overlapY) {
          const direction = dx >= 0 ? 1 : -1;
          leftPosition.x -= overlapX * moveLeft * direction;
          rightPosition.x += overlapX * moveRight * direction;
        } else {
          const direction = dy >= 0 ? 1 : -1;
          leftPosition.y -= overlapY * moveLeft * direction;
          rightPosition.y += overlapY * moveRight * direction;
        }
      }
    }
  }
}

/* --------------------------------------------------------------------------------------- *
 * The Eclipse Layout Kernel placement.
 * --------------------------------------------------------------------------------------- */

type ElkLayoutEngine = {
  layout(graph: ElkNode): Promise<ElkNode>;
};

/**
 * One engine for the page, loaded the first time a map asks for it.
 *
 * The kernel is large, and most of the workspace never draws a graph, so it is not part of the
 * initial chunk. The promise is cached rather than the instance: two lenses switched quickly
 * would otherwise each construct their own kernel.
 *
 * It runs in a worker. `elk-worker.min.js` ships in the same package as the bundled build and
 * was simply never reached for, so every placement on this surface ran on the thread that
 * draws it — and a placement is hundreds of milliseconds on the graph a real review produces,
 * during which nothing on the page moves. The bundled build stays as the answer for anywhere
 * without workers, which is chiefly the test environment; both expose the same `layout`.
 */
let engine: Promise<ElkLayoutEngine> | null = null;

function layoutEngine(): Promise<ElkLayoutEngine> {
  if (!engine) engine = startEngine();
  return engine;
}

async function startEngine(): Promise<ElkLayoutEngine> {
  if (typeof Worker === "function") {
    const [api, worker] = await Promise.all([
      import("elkjs/lib/elk-api.js"),
      import("elkjs/lib/elk-worker.min.js?worker"),
    ]);
    const Constructor = (api.default ?? api) as unknown as new (
      options?: unknown,
    ) => ElkLayoutEngine;
    return new Constructor({ workerFactory: () => new worker.default() });
  }
  const module = await import("elkjs/lib/elk.bundled.js");
  const Constructor = (module.default ?? module) as unknown as new (
    options?: unknown,
  ) => ElkLayoutEngine;
  return new Constructor();
}

/**
 * How the cards inside one cluster are laid out: downward, layered, the way a hierarchy
 * reads. `considerModelOrder` keeps it deterministic — the same graph in the same order lands
 * in the same place every time, which is what the rest of this file has always insisted on.
 * The top padding is room for the label row the canvas draws inside the enclosure.
 */
const CLUSTER_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.direction": "DOWN",
  "elk.aspectRatio": "1.7",
  "elk.spacing.nodeNode": "34",
  "elk.layered.spacing.nodeNodeBetweenLayers": "52",
  "elk.layered.spacing.edgeNodeBetweenLayers": "26",
  "elk.spacing.edgeNode": "22",
  "elk.spacing.componentComponent": "44",
  "elk.separateConnectedComponents": "true",
  "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
  "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
  "elk.layered.compaction.postCompaction.strategy": "LEFT",
  "elk.padding": "[top=44,left=28,bottom=28,right=28]",
};

/**
 * How the finished clusters are arranged on the canvas.
 *
 * Not `layered`: laying the clusters out hierarchically strings them into a single row,
 * because the edges *between* clusters are few and a layered pass with almost no edges to
 * satisfy has no reason to wrap. `rectpacking` ignores edges and packs the boxes into rows
 * towards a target aspect ratio, which is the right question to ask of a set of regions whose
 * connections are drawn as free curves anyway. Nothing is lost by it: `edgePath` draws every
 * inter-cluster edge from the two card positions, not from a route ELK computed.
 */
const PACKING_OPTIONS: Record<string, string> = {
  "elk.algorithm": "rectpacking",
  "elk.aspectRatio": "1.6",
  "elk.spacing.nodeNode": "56",
  "elk.padding": "[top=28,left=28,bottom=28,right=28]",
};

const CLUSTER_PREFIX = "cluster::";

/**
 * The same map, placed by the layout kernel, in two passes.
 *
 * Reads the graph exactly as `layoutAtlas` does — same components, same levels, same
 * clusters. Each cluster is then laid out on its own as a small hierarchy, and the finished
 * boxes are packed onto the canvas. Edge routes are discarded throughout: the canvas draws
 * its own curves between card borders, and a routed polyline would be a different drawing.
 */
export async function layoutAtlasElk(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[] = [],
  lens: AtlasLens = "structure",
): Promise<AtlasLayout> {
  if (!nodes.length) return emptyLayout();
  const { byId, validEdges, neighbours, componentByNode, levels } = analyseGraph(nodes, edges);
  const ordered = canonicalOrder(nodes, neighbours, componentByNode, levels);
  const { roots, orderedGroups } = clusterGroups(ordered, validEdges, byId, lens);
  const elk = await layoutEngine();

  const card = (node: AtlasNodeView): ElkNode => ({
    id: node.id,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  });
  /** A packed box, and where its cards sit relative to its own top-left corner. */
  const boxes: ElkNode[] = [];
  const interiors = new Map<string, Map<string, { x: number; y: number }>>();

  // Roots first, so a repository is packed at the top-left where the reading starts rather
  // than wherever a box of its size happened to fit.
  ordered.filter((node) => roots.has(node.id)).forEach((node) => boxes.push(card(node)));

  /**
   * Every cluster at once rather than one after another.
   *
   * The clusters are independent — each is laid out from its own members and its own internal
   * edges, and nothing about one can change another — so awaiting them in a loop was waiting
   * out the sum of a set of answers that could have cost the longest of them. `Promise.all`
   * preserves the order of `orderedGroups`, which is what the packing pass reads, so the
   * placement stays as deterministic as the rest of this file insists on being.
   */
  const placements = await Promise.all(
    orderedGroups.map(([clusterId, group]) => {
      if (group.length < 2) return Promise.resolve(null);
      const memberIds = new Set(group.map((node) => node.id));
      return elk.layout({
        id: `${CLUSTER_PREFIX}${clusterId}`,
        layoutOptions: CLUSTER_OPTIONS,
        children: group.map(card),
        edges: validEdges
          .filter((edge) => memberIds.has(edge.sourceId) && memberIds.has(edge.targetId))
          .map((edge) => ({
            id: edge.id,
            sources: [edge.sourceId],
            targets: [edge.targetId],
          })),
      });
    }),
  );

  placements.forEach((placed, index) => {
    if (!placed) {
      boxes.push(card(orderedGroups[index][1][0]));
      return;
    }
    interiors.set(
      placed.id,
      new Map(
        (placed.children || []).map((child) => [child.id, { x: child.x || 0, y: child.y || 0 }]),
      ),
    );
    boxes.push({
      id: placed.id,
      width: placed.width || NODE_WIDTH,
      height: placed.height || NODE_HEIGHT,
    });
  });

  const packed = await elk.layout({
    id: "atlas",
    layoutOptions: PACKING_OPTIONS,
    children: boxes,
  });

  const positions = new Map<string, { x: number; y: number }>();
  const containers = new Map<string, { x: number; y: number; width: number; height: number }>();
  for (const box of packed.children || []) {
    const x = box.x || 0;
    const y = box.y || 0;
    const interior = interiors.get(box.id);
    if (!interior) {
      positions.set(box.id, { x, y });
      continue;
    }
    containers.set(box.id, { x, y, width: box.width || 0, height: box.height || 0 });
    interior.forEach((offset, nodeId) =>
      positions.set(nodeId, { x: x + offset.x, y: y + offset.y }),
    );
  }

  // A card the kernel did not place would be drawn nowhere at all, so an incomplete result is
  // no result: the caller keeps the layout it already has.
  if (ordered.some((node) => !positions.has(node.id))) {
    throw new Error("Graph layout returned an incomplete placement");
  }

  const clusters: AtlasClusterRegion[] = orderedGroups
    .filter(([, group]) => group.length > 1)
    .flatMap(([clusterId, group]) => {
      const region = containers.get(`${CLUSTER_PREFIX}${clusterId}`);
      if (!region) return [];
      return [
        {
          id: clusterId,
          label: clusterLabel(group, byId, clusterId),
          nodeIds: group.map((node) => node.id),
          ...region,
        },
      ];
    });

  const lefts = [
    ...[...positions.values()].map((position) => position.x),
    ...clusters.map((cluster) => cluster.x),
  ];
  const tops = [
    ...[...positions.values()].map((position) => position.y),
    ...clusters.map((cluster) => cluster.y),
  ];
  const shiftX = Math.min(...lefts) < PADDING_X ? PADDING_X - Math.min(...lefts) : 0;
  const shiftY = Math.min(...tops) < PADDING_Y ? PADDING_Y - Math.min(...tops) : 0;
  positions.forEach((position) => {
    position.x += shiftX;
    position.y += shiftY;
  });
  clusters.forEach((cluster) => {
    cluster.x += shiftX;
    cluster.y += shiftY;
  });

  const right = Math.max(
    ...[...positions.values()].map((position) => position.x + NODE_WIDTH),
    ...clusters.map((cluster) => cluster.x + cluster.width),
  );
  const bottom = Math.max(
    ...[...positions.values()].map((position) => position.y + NODE_HEIGHT),
    ...clusters.map((cluster) => cluster.y + cluster.height),
  );
  return {
    positions,
    width: Math.max(MIN_CANVAS_WIDTH, right + PADDING_X),
    height: Math.max(MIN_CANVAS_HEIGHT, bottom + PADDING_Y),
    levels,
    clusters,
  };
}
