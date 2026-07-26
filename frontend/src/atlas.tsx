import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  CircleDot,
  GitBranch,
  Layers3,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  Route,
  Scan,
  Search,
} from "lucide-react";
import {
  type FormEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { Badge } from "./components";
import type {
  AtlasExploreOperation,
  AtlasMetricNature,
  AtlasMetricScope,
  AtlasSignal,
} from "./types";

/**
 * `cleared` exists for the review atlas: a boundary that was examined and found to be
 * earning its place. It is not the absence of a finding, which is what `normal` means, and
 * a map that drew the two the same way would say the advisor never looked.
 */
export type AtlasNodeState =
  | "normal"
  | "hotspot"
  | "contained"
  | "inference"
  | "cleared";

export interface AtlasMetricView {
  label: string;
  value: number | string;
  group?: string;
  nature?: AtlasMetricNature;
  scope?: AtlasMetricScope;
  definition?: string;
  limitations?: string;
}

export interface AtlasNodeView {
  id: string;
  label: string;
  path: string;
  kind: string;
  isPublic?: boolean | null;
  state: AtlasNodeState;
  description?: string;
  metrics: AtlasMetricView[];
  evidenceCount?: number;
  signalCount?: number;
  signals?: AtlasSignal[];
}

export interface AtlasEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  kind: string;
  confidence?: number;
  risk?: boolean;
}

export interface RepositoryAtlasProps {
  title?: string;
  description?: string;
  mode?: "repository" | "greenfield";
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  loading?: boolean;
  emptyMessage?: string;
  onExploreNode?: (
    nodeId: string,
    operation: Exclude<
      AtlasExploreOperation,
      "search" | "shortest_path" | "cycles" | "signals"
    >,
    depth?: number,
  ) => void;
  onExploreAtlas?: (
    operation: Extract<AtlasExploreOperation, "cycles" | "signals">,
  ) => void;
  onSearch?: (term: string) => void;
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  highlightedNodeIds?: string[];
  highlightedEdgeIds?: string[];
}

type AtlasLens = "structure" | "dependencies" | "risk";

const NODE_WIDTH = 190;
const NODE_HEIGHT = 78;
const MIN_CANVAS_WIDTH = 920;
const PADDING_X = 44;
const PADDING_Y = 42;
const MIN_ZOOM = .55;
const MAX_ZOOM = 1.8;
const ZOOM_STEP = .15;
const ISLAND_NODE_GAP = 52;
const ISLAND_LAYER_GAP = 70;

export interface AtlasLayout {
  positions: Map<string, { x: number; y: number }>;
  width: number;
  height: number;
  levels: Map<string, number>;
  clusters: AtlasClusterRegion[];
}

export interface AtlasClusterRegion {
  id: string;
  label: string;
  nodeIds: string[];
  x: number;
  y: number;
  width: number;
  height: number;
}

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
    decision: 0,
    responsibility: 1,
    boundary: 2,
    alternative: 3,
  };
  return `${String(kindOrder[node.kind] ?? 20).padStart(2, "0")}:${node.path}:${node.label}`;
}

function kindLevel(kind: string) {
  const levels: Record<string, number> = {
    repository: 0,
    decision: 0,
    package: 1,
    responsibility: 1,
    boundary: 1,
    module: 2,
    test_module: 2,
    configuration: 2,
    alternative: 2,
    class: 3,
    interface: 3,
    function: 4,
    method: 4,
    test_function: 4,
  };
  return levels[kind] ?? 2;
}

const hierarchicalEdges = new Set(["contains", "defines", "allocates"]);

export function layoutAtlas(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[] = [],
  lens: AtlasLens = "structure",
): AtlasLayout {
  if (!nodes.length) {
    return {
      positions: new Map(),
      width: MIN_CANVAS_WIDTH,
      height: 360,
      levels: new Map(),
      clusters: [],
    };
  }
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

  // A homogeneous component has no type hierarchy to guide it. Use graph
  // distance from its most connected node so topology still determines placement.
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

  // Repeated barycentric sweeps pull children underneath their connected
  // parents and reduce edge crossings without a non-deterministic force layout.
  for (let pass = 0; pass < 4; pass += 1) {
    const sweep = pass % 2 === 0 ? orderedLevels : [...orderedLevels].reverse();
    const indexByNode = new Map<string, number>();
    layers.forEach((layer) =>
      layer.forEach((node, index) => indexByNode.set(node.id, index)),
    );
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
          return connected.reduce(
            (sum, nodeId) => sum + (indexByNode.get(nodeId) || 0),
            0,
          ) / connected.length;
        };
        const difference = score(left) - score(right);
        return difference || nodeOrder(left).localeCompare(nodeOrder(right));
      });
    }
  }

  return clusterLayout(nodes, validEdges, levels, byId, lens);
}

function clusterLayout(
  nodes: AtlasNodeView[],
  edges: AtlasEdgeView[],
  levels: Map<string, number>,
  byId: Map<string, AtlasNodeView>,
  lens: AtlasLens,
): AtlasLayout {
  const roots = new Set(
    nodes
      .filter((node) => node.kind === "repository" || node.kind === "decision")
      .map((node) => node.id),
  );
  const hasStructuralRelationships = edges.some((edge) =>
    hierarchicalEdges.has(edge.kind),
  );
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
  const columns = Math.max(1, Math.ceil(Math.sqrt(orderedGroups.length)));
  const rows = Math.max(1, Math.ceil(orderedGroups.length / columns));
  const cellWidth = 510;
  const cellHeight = 370;
  const rootBand = roots.size ? 170 : 30;
  const initialWidth = Math.max(
    MIN_CANVAS_WIDTH,
    columns * cellWidth + PADDING_X * 2,
  );
  const initialHeight = Math.max(
    430,
    rootBand + rows * cellHeight + PADDING_Y * 2,
  );
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

  relaxClusters(
    nodes,
    edges,
    positions,
    clusterByNode,
    clusterTargets,
    roots,
    levels,
    lens,
  );
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
  const maximumX = Math.max(
    ...nodes.map((node) => positions.get(node.id)!.x + NODE_WIDTH),
  );
  const maximumY = Math.max(
    ...nodes.map((node) => positions.get(node.id)!.y + NODE_HEIGHT),
  );
  const width = Math.max(MIN_CANVAS_WIDTH, maximumX + PADDING_X);
  const height = Math.max(430, maximumY + PADDING_Y);
  const clusters: AtlasClusterRegion[] = orderedGroups
    .filter(([, group]) => group.length > 1)
    .map(([clusterId, group]) => {
      const groupPositions = group.map((node) => positions.get(node.id)!);
      const x = Math.min(...groupPositions.map((position) => position.x)) - 28;
      const y = Math.min(...groupPositions.map((position) => position.y)) - 35;
      const right =
        Math.max(...groupPositions.map((position) => position.x + NODE_WIDTH)) + 28;
      const bottom =
        Math.max(...groupPositions.map((position) => position.y + NODE_HEIGHT)) + 28;
      return {
        id: clusterId,
        label: (byId.get(clusterId) || group[0]).label,
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
 * Place a structural island as a compact Sugiyama-style hierarchy. Repeated
 * barycentric sweeps keep a child close to its connected parent and reduce
 * crossings before the constrained relaxation pass fine-tunes the result.
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
    const levelOrder = pass % 2 === 0
      ? orderedLevels
      : [...orderedLevels].reverse();
    const rank = new Map<string, number>();
    orderedLevels.forEach((level) => {
      const layer = layers.get(level)!;
      layer.forEach((node, index) => {
        rank.set(node.id, layer.length === 1 ? .5 : index / (layer.length - 1));
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
          return connected.reduce(
            (sum, nodeId) => sum + (rank.get(nodeId) ?? .5),
            0,
          ) / connected.length;
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
 * Dependency and risk islands use graph distance from a meaningful hub. This
 * keeps immediate neighbours visually close while preserving a less rigid,
 * radial character than the structural lens.
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
    if (lens === "risk" && left.state !== right.state) {
      return left.state === "hotspot" ? -1 : 1;
    }
    return (
      (neighbours.get(right.id)?.size || 0) -
        (neighbours.get(left.id)?.size || 0) ||
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
  rings.forEach((nodes, ring) => {
    nodes.sort((left, right) => {
      const degreeDifference =
        (neighbours.get(right.id)?.size || 0) - (neighbours.get(left.id)?.size || 0);
      return degreeDifference || nodeOrder(left).localeCompare(nodeOrder(right));
    });
    if (ring === 0) {
      positions.set(nodes[0].id, {
        x: center.x - NODE_WIDTH / 2,
        y: center.y - NODE_HEIGHT / 2,
      });
      return;
    }
    const circumferenceRadius =
      (nodes.length * (NODE_WIDTH + ISLAND_NODE_GAP)) / (2 * Math.PI);
    const radiusX = Math.max(165 * ring, circumferenceRadius);
    const radiusY = Math.max(110 * ring, radiusX * .62);
    nodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + index * (2 * Math.PI / nodes.length);
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
      right: Math.max(
        ...groupPositions.map((position) => position.x + NODE_WIDTH),
      ),
      bottom: Math.max(
        ...groupPositions.map((position) => position.y + NODE_HEIGHT),
      ),
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
          Math.min(left.right + gap, right.right + gap) -
          Math.max(left.left, right.left);
        const overlapY =
          Math.min(left.bottom + gap, right.bottom + gap) -
          Math.max(left.top, right.top);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        const leftCenterX = (left.left + left.right) / 2;
        const rightCenterX = (right.left + right.right) / 2;
        const leftCenterY = (left.top + left.bottom) / 2;
        const rightCenterY = (right.top + right.bottom) / 2;
        if (overlapX < overlapY) {
          const direction = rightCenterX >= leftCenterX ? 1 : -1;
          translate(leftGroup, -direction * overlapX / 2, 0);
          translate(rightGroup, direction * overlapX / 2, 0);
        } else {
          const direction = rightCenterY >= leftCenterY ? 1 : -1;
          translate(leftGroup, 0, -direction * overlapY / 2);
          translate(rightGroup, 0, direction * overlapY / 2);
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
  const targetCount = Math.min(
    6,
    Math.max(1, Math.round(Math.sqrt(candidates.length / 4))),
  );
  const ranked = [...candidates].sort((left, right) => {
    if (lens === "risk" && left.state !== right.state) {
      return left.state === "hotspot" ? -1 : 1;
    }
    return (
      (neighbours.get(right.id)?.size || 0) -
        (neighbours.get(left.id)?.size || 0) ||
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
          Math.min(
            ...seeds.map((seed) => distanceFrom(seed).get(nodeId) ?? 1_000),
          );
        return score(right.id) - score(left.id) || nodeOrder(left).localeCompare(nodeOrder(right));
      })[0];
    if (!next) break;
    seeds.push(next.id);
  }
  return new Map(
    candidates.map((node) => {
      const seed = [...seeds].sort((left, right) => {
        const difference =
          (distanceFrom(left).get(node.id) ?? 1_000) -
          (distanceFrom(right).get(node.id) ?? 1_000);
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
      const groupLevels = [...new Set(members.map((node) => levels.get(node.id) || 0))]
        .sort((left, right) => left - right);
      members.forEach((node) => {
        const levelIndex = groupLevels.indexOf(levels.get(node.id) || 0);
        structuralTargetY.set(
          node.id,
          target.y +
            (levelIndex - (groupLevels.length - 1) / 2) *
              (NODE_HEIGHT + ISLAND_LAYER_GAP),
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
        movement.x += (target.x - (position.x + NODE_WIDTH / 2)) * .008;
        movement.y += (target.y - (position.y + NODE_HEIGHT / 2)) * .008;
        if (lens === "structure") {
          const targetY = structuralTargetY.get(node.id) || target.y;
          movement.y += (targetY - (position.y + NODE_HEIGHT / 2)) * .022;
        }
      }
    });
    edges.forEach((edge) => {
      if (clusterByNode.get(edge.sourceId) !== clusterByNode.get(edge.targetId)) {
        return;
      }
      const source = positions.get(edge.sourceId);
      const target = positions.get(edge.targetId);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const ideal = hierarchicalEdges.has(edge.kind) ? 135 : 190;
      const force = (distance - ideal) * .012;
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
        const sameCluster = clusterByNode.get(left.id) === clusterByNode.get(right.id);
        if (!sameCluster) continue;
        const minimum = sameCluster ? 178 : 285;
        if (distance >= minimum) continue;
        const force = (minimum - distance) * (sameCluster ? .018 : .026);
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
      movement.x *= .68;
      movement.y *= .68;
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
        const moveLeft = roots.has(left.id) ? 0 : .5;
        const moveRight = roots.has(right.id) ? 0 : .5;
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

export function RepositoryAtlas({
  title = "RepositoryAtlas",
  description,
  mode = "repository",
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  loading = false,
  emptyMessage = "No bounded atlas nodes are available yet.",
  onExploreNode,
  onExploreAtlas,
  onSearch,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  highlightedNodeIds = [],
  highlightedEdgeIds = [],
}: RepositoryAtlasProps) {
  const [lens, setLens] = useState<AtlasLens>("structure");
  const [searchValue, setSearchValue] = useState("");
  const [hiddenEdgeKinds, setHiddenEdgeKinds] = useState<Set<string>>(new Set());
  const [hideTests, setHideTests] = useState(false);
  const [publicOnly, setPublicOnly] = useState(false);
  const selected = selectedNodeId
    ? nodes.find((node) => node.id === selectedNodeId)
    : undefined;
  const availableEdgeKinds = useMemo(
    () => [...new Set(edges.map((edge) => edge.kind))].sort(),
    [edges],
  );
  const visibleGraph = useMemo(() => {
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
  }, [edges, hiddenEdgeKinds, hideTests, lens, nodes, publicOnly, selected]);
  const layout = useMemo(
    () => layoutAtlas(visibleGraph.nodes, visibleGraph.edges, lens),
    [lens, visibleGraph],
  );
  const { positions } = layout;
  const highlightedNodes = new Set(highlightedNodeIds);
  const highlightedEdges = new Set(highlightedEdgeIds);
  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [showMinimap, setShowMinimap] = useState(true);
  const [viewport, setViewport] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const canvasRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const nodeRefs = useRef(new Map<string, SVGGElement>());
  const drag = useRef<{
    pointerId: number;
    x: number;
    y: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  const activePointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{
    distance: number;
    zoom: number;
    worldX: number;
    worldY: number;
  } | null>(null);
  const suppressNodeClick = useRef(false);
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const term = searchValue.trim().toLocaleLowerCase();
    if (!term) return;
    const localMatch = nodes.find((node) =>
      `${node.label} ${node.path} ${node.kind}`.toLocaleLowerCase().includes(term),
    );
    if (localMatch) onSelectNode(localMatch.id);
    else onSearch?.(searchValue.trim());
  };

  const toggleEdgeKind = (kind: string) => {
    setHiddenEdgeKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  const setViewportZoom = (
    requested: number,
    anchor?: { clientX: number; clientY: number },
  ) => {
    const next = clamp(requested, MIN_ZOOM, MAX_ZOOM);
    const canvas = canvasRef.current;
    if (!canvas || next === zoom) return;
    const bounds = canvas.getBoundingClientRect();
    const anchorX = anchor ? anchor.clientX - bounds.left : canvas.clientWidth / 2;
    const anchorY = anchor ? anchor.clientY - bounds.top : canvas.clientHeight / 2;
    const worldX = (canvas.scrollLeft + anchorX) / zoom;
    const worldY = (canvas.scrollTop + anchorY) / zoom;
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: worldX * next - anchorX,
        top: worldY * next - anchorY,
      });
    });
  };

  const updateViewport = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    setViewport({
      x: canvas.scrollLeft / zoom,
      y: canvas.scrollTop / zoom,
      width: canvas.clientWidth / zoom,
      height: canvas.clientHeight / zoom,
    });
  };

  const fitGraph = () => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.clientWidth || !canvas.clientHeight) return;
    const next = clamp(
      Math.min(
        (canvas.clientWidth - 24) / layout.width,
        (canvas.clientHeight - 24) / layout.height,
      ),
      MIN_ZOOM,
      1.15,
    );
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: Math.max(0, (layout.width * next - canvas.clientWidth) / 2),
        top: Math.max(0, (layout.height * next - canvas.clientHeight) / 2),
      });
    });
  };

  const toggleFullscreen = async () => {
    const panel = panelRef.current;
    if (!panel) return;
    if (fullscreen) {
      if (document.fullscreenElement === panel && document.exitFullscreen) {
        await document.exitFullscreen();
      }
      setFullscreen(false);
      return;
    }
    setFullscreen(true);
    if (panel.requestFullscreen) {
      try {
        await panel.requestFullscreen();
      } catch {
        // The fixed viewport fallback still provides a full-workspace canvas.
      }
    }
  };

  useEffect(() => {
    fitGraph();
    // Refit only when topology changes its overall bounds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.height, layout.width]);

  useEffect(() => {
    if (highlightedEdgeIds.length) setLens("dependencies");
  }, [highlightedEdgeIds]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      if (document.fullscreenElement) {
        setFullscreen(document.fullscreenElement === panelRef.current);
      } else {
        setFullscreen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.fullscreenElement) {
        setFullscreen(false);
      }
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    if (!fullscreen) return;
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(fitGraph);
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
    // Refit after fullscreen CSS has consumed the viewport.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullscreen]);

  useEffect(() => {
    window.requestAnimationFrame(updateViewport);
    // Viewport dimensions depend on both zoom and graph bounds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.height, layout.width, zoom]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleAtlasWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        // Trackpad pinch gestures arrive as a modified wheel event. Scoping the
        // non-passive listener to the canvas prevents browser zoom only here.
        event.preventDefault();
        const next = zoom * Math.exp(-event.deltaY * .006);
        setViewportZoom(next, { clientX: event.clientX, clientY: event.clientY });
        return;
      }
      if (event.shiftKey && event.deltaY) {
        event.preventDefault();
        canvas.scrollLeft += event.deltaY;
      }
    };
    canvas.addEventListener("wheel", handleAtlasWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleAtlasWheel);
    // The listener needs the latest zoom as its gesture baseline.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  useEffect(() => {
    if (!selected) return;
    const canvas = canvasRef.current;
    const position = positions.get(selected.id);
    if (!canvas || !position || typeof canvas.scrollTo !== "function") return;
    canvas.scrollTo({
      left: Math.max(
        0,
        (position.x + NODE_WIDTH / 2) * zoom - canvas.clientWidth / 2,
      ),
      top: Math.max(
        0,
        (position.y + NODE_HEIGHT / 2) * zoom - canvas.clientHeight / 2,
      ),
      behavior: "smooth",
    });
  }, [positions, selected, zoom]);

  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const canvas = event.currentTarget;
    activePointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    canvas.setPointerCapture?.(event.pointerId);
    if (activePointers.current.size === 2) {
      const [first, second] = [...activePointers.current.values()];
      const bounds = canvas.getBoundingClientRect();
      const centerX = (first.x + second.x) / 2 - bounds.left;
      const centerY = (first.y + second.y) / 2 - bounds.top;
      pinch.current = {
        distance: pointerDistance(first, second),
        zoom,
        worldX: (canvas.scrollLeft + centerX) / zoom,
        worldY: (canvas.scrollTop + centerY) / zoom,
      };
      drag.current = null;
      suppressNodeClick.current = true;
      setPanning(false);
      return;
    }
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    suppressNodeClick.current = false;
    setPanning(true);
  };

  const pan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (activePointers.current.has(event.pointerId)) {
      activePointers.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
    }
    if (pinch.current && activePointers.current.size >= 2) {
      event.preventDefault();
      const canvas = event.currentTarget;
      const [first, second] = [...activePointers.current.values()];
      const bounds = canvas.getBoundingClientRect();
      const centerX = (first.x + second.x) / 2 - bounds.left;
      const centerY = (first.y + second.y) / 2 - bounds.top;
      const next = clamp(
        pinch.current.zoom *
          (pointerDistance(first, second) / Math.max(1, pinch.current.distance)),
        MIN_ZOOM,
        MAX_ZOOM,
      );
      setZoom(next);
      canvas.scrollLeft = pinch.current.worldX * next - centerX;
      canvas.scrollTop = pinch.current.worldY * next - centerY;
      suppressNodeClick.current = true;
      return;
    }
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) {
      suppressNodeClick.current = true;
    }
    event.currentTarget.scrollLeft = start.scrollLeft - deltaX;
    event.currentTarget.scrollTop = start.scrollTop - deltaY;
  };

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    activePointers.current.delete(event.pointerId);
    if (activePointers.current.size < 2) pinch.current = null;
    if (drag.current?.pointerId === event.pointerId) {
      drag.current = null;
      setPanning(false);
    }
  };

  const selectNode = (nodeId: string) => {
    if (suppressNodeClick.current) {
      suppressNodeClick.current = false;
      return;
    }
    onSelectNode(nodeId);
  };

  const deselectBackground = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (suppressNodeClick.current) {
      suppressNodeClick.current = false;
      return;
    }
    const target = event.target;
    if (target instanceof Element && target.closest("[data-atlas-node-id]")) {
      return;
    }
    onSelectNode(null);
  };

  const navigateNode = (
    nodeId: string,
    key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Home" | "End",
  ) => {
    const sorted = [...visibleGraph.nodes].sort((left, right) => {
      const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
      const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
      return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x;
    });
    let next: AtlasNodeView | undefined;
    if (key === "Home") next = sorted[0];
    else if (key === "End") next = sorted.at(-1);
    else {
      const relatedIds = visibleGraph.edges
        .filter((edge) =>
          key === "ArrowDown" || key === "ArrowRight"
            ? edge.sourceId === nodeId
            : edge.targetId === nodeId,
        )
        .map((edge) =>
          edge.sourceId === nodeId ? edge.targetId : edge.sourceId,
        );
      const current = positions.get(nodeId) || { x: 0, y: 0 };
      next = sorted
        .filter((node) => node.id !== nodeId)
        .filter((node) => {
          const position = positions.get(node.id) || { x: 0, y: 0 };
          if (key === "ArrowDown") return position.y > current.y;
          if (key === "ArrowUp") return position.y < current.y;
          if (key === "ArrowRight") return position.x > current.x;
          return position.x < current.x;
        })
        .sort((left, right) => {
          const relatedDifference =
            Number(relatedIds.includes(right.id)) - Number(relatedIds.includes(left.id));
          if (relatedDifference) return relatedDifference;
          const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
          const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
          return (
            distance(current, leftPosition) - distance(current, rightPosition)
          );
        })[0];
    }
    if (!next) return;
    onSelectNode(next.id);
    window.requestAnimationFrame(() => nodeRefs.current.get(next!.id)?.focus());
  };

  return (
    <section
      ref={panelRef}
      className={`atlas-panel ${fullscreen ? "atlas-panel--fullscreen" : ""}`}
      aria-labelledby="atlas-heading"
    >
      <div className="atlas-panel__header">
        <div>
          <span className="eyebrow">
            {mode === "repository" ? "Bounded structural evidence" : "Proposed architecture"}
          </span>
          <h2 id="atlas-heading">{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <Badge tone={mode === "repository" ? "teal" : "neutral"}>
          {mode === "repository" ? `${nodes.length} surfaced nodes` : "Greenfield canvas"}
        </Badge>
      </div>

      <div className="atlas-explorer" aria-label="Atlas exploration controls">
        <form className="atlas-search" role="search" onSubmit={submitSearch}>
          <Search size={14} />
          <input
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            placeholder="Find a module, class, or path"
            aria-label="Search repository atlas"
          />
          <button type="submit">Find</button>
        </form>
        <div className="atlas-lenses" role="group" aria-label="Graph lens">
          {(["structure", "dependencies", "risk"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={lens === value ? "active" : ""}
              aria-pressed={lens === value}
              onClick={() => setLens(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`atlas-filter-toggle ${hideTests ? "active" : ""}`}
          aria-pressed={hideTests}
          onClick={() => setHideTests((value) => !value)}
        >
          Hide tests
        </button>
        <button
          type="button"
          className={`atlas-filter-toggle ${publicOnly ? "active" : ""}`}
          aria-pressed={publicOnly}
          onClick={() => setPublicOnly((value) => !value)}
        >
          Public only
        </button>
        {lens === "risk" && onExploreAtlas && (
          <>
            <button
              type="button"
              className="atlas-filter-toggle"
              disabled={loading}
              onClick={() => onExploreAtlas("signals")}
            >
              Surface signals
            </button>
            <button
              type="button"
              className="atlas-filter-toggle"
              disabled={loading}
              onClick={() => onExploreAtlas("cycles")}
            >
              Surface cycles
            </button>
          </>
        )}
      </div>

      <div className="atlas-toolbar">
        <div className="atlas-legend" aria-label="Atlas legend">
          <span><CircleDot size={13} /> Normal</span>
          <span><AlertTriangle size={13} /> Hotspot</span>
          <span><CheckCircle2 size={13} /> Contained</span>
          {mode === "greenfield" && <span><Layers3 size={13} /> Advisor inference</span>}
        </div>
        {availableEdgeKinds.length > 0 && (
          <div className="atlas-edge-filters" aria-label="Relationship filters">
            {availableEdgeKinds.map((kind) => (
              <button
                key={kind}
                type="button"
                className={hiddenEdgeKinds.has(kind) ? "" : "active"}
                aria-pressed={!hiddenEdgeKinds.has(kind)}
                onClick={() => toggleEdgeKind(kind)}
              >
                <i className={`atlas-edge-swatch atlas-edge-swatch--${edgeKindClass(kind)}`} />
                {kind}
              </button>
            ))}
          </div>
        )}
        <span className="atlas-toolbar__hint" id={instructionsId}>
          Drag to pan · scroll to move · pinch or Ctrl/⌘ + scroll to zoom
        </span>
        <div className="atlas-controls" role="group" aria-label="Graph viewport controls">
          <button
            type="button"
            aria-label="Zoom out"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setViewportZoom(zoom - ZOOM_STEP)}
          >
            <Minus size={14} />
          </button>
          <output aria-live="polite" aria-label="Current graph zoom">
            {Math.round(zoom * 100)}%
          </output>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setViewportZoom(zoom + ZOOM_STEP)}
          >
            <Plus size={14} />
          </button>
          <button type="button" aria-label="Fit graph to view" onClick={fitGraph}>
            <Scan size={14} />
          </button>
          <button
            type="button"
            aria-label={fullscreen ? "Exit full screen" : "Enter full screen"}
            aria-pressed={fullscreen}
            onClick={() => void toggleFullscreen()}
          >
            {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            type="button"
            aria-label={showMinimap ? "Hide graph minimap" : "Show graph minimap"}
            aria-pressed={showMinimap}
            onClick={() => setShowMinimap((value) => !value)}
          >
            <MapIcon size={14} />
          </button>
        </div>
      </div>

      <div className="atlas-layout">
        <div className="atlas-viewport">
          <div
            ref={canvasRef}
            className={`atlas-canvas ${panning ? "atlas-canvas--panning" : ""}`}
            role="region"
            tabIndex={0}
            aria-label="Scrollable graph viewport"
            aria-describedby={instructionsId}
            aria-busy={loading}
            onPointerDown={beginPan}
            onPointerMove={pan}
            onPointerUp={endPan}
            onPointerCancel={endPan}
            onScroll={updateViewport}
            onClick={deselectBackground}
          >
            {visibleGraph.nodes.length ? (
            <svg
              role="group"
              aria-label={mode === "repository" ? "Repository node graph" : "Greenfield architecture graph"}
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              width={layout.width * zoom}
              height={layout.height * zoom}
              style={{
                width: `${layout.width * zoom}px`,
                height: `${layout.height * zoom}px`,
              }}
              preserveAspectRatio="xMinYMin meet"
            >
              <defs>
                <pattern id={gridId} width="24" height="24" patternUnits="userSpaceOnUse">
                  <path className="atlas-grid-line" d="M 24 0 L 0 0 0 24" fill="none" />
                </pattern>
                <marker
                  id={arrowId}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path className="atlas-arrow" d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              <rect className="atlas-canvas__background" width="100%" height="100%" />
              <rect fill={`url(#${gridId})`} width="100%" height="100%" />
              <g className="atlas-clusters" aria-hidden="true">
                {layout.clusters.map((cluster) => (
                  <g key={cluster.id}>
                    <rect
                      x={cluster.x}
                      y={cluster.y}
                      width={cluster.width}
                      height={cluster.height}
                      rx="22"
                    />
                    <text x={cluster.x + 16} y={cluster.y + 21}>
                      {truncate(cluster.label, 34)} · {cluster.nodeIds.length}
                    </text>
                  </g>
                ))}
              </g>
              <g aria-hidden="true">
                {visibleGraph.edges.map((edge) => {
                  const source = positions.get(edge.sourceId);
                  const target = positions.get(edge.targetId);
                  if (!source || !target || edge.sourceId === edge.targetId) return null;
                  const connected =
                    edge.sourceId === selected?.id || edge.targetId === selected?.id;
                  return (
                    <path
                      key={edge.id}
                      className={`atlas-edge ${
                        connected ? "atlas-edge--active" : "atlas-edge--muted"
                      } ${edge.risk ? "atlas-edge--risk" : ""} ${
                        (edge.confidence ?? 0) >= .9 ? "atlas-edge--strong" : ""
                      } atlas-edge--kind-${edgeKindClass(edge.kind)} ${
                        highlightedEdges.has(edge.id) ? "atlas-edge--path" : ""
                      }`}
                      d={edgePath(source, target)}
                      markerEnd={`url(#${arrowId})`}
                    />
                  );
                })}
              </g>
              {visibleGraph.nodes.map((node) => {
                const position = positions.get(node.id);
                if (!position) return null;
                const active = node.id === selected?.id;
                return (
                  <g
                    key={node.id}
                    ref={(element) => {
                      if (element) nodeRefs.current.set(node.id, element);
                      else nodeRefs.current.delete(node.id);
                    }}
                    data-atlas-node-id={node.id}
                    role="button"
                    tabIndex={active ? 0 : -1}
                    aria-pressed={active}
                    aria-label={`${node.label}, ${node.kind}, ${node.state}`}
                    className={`atlas-node atlas-node--${node.state} ${active ? "atlas-node--active" : ""} ${
                      highlightedNodes.has(node.id) ? "atlas-node--path" : ""
                    }`}
                    transform={`translate(${position.x} ${position.y})`}
                    onPointerDown={(event) => {
                      // Keep node activation separate from the canvas pan
                      // gesture, which captures pointers at the viewport.
                      event.stopPropagation();
                      suppressNodeClick.current = false;
                    }}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectNode(node.id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectNode(node.id);
                      } else if (
                        event.key === "ArrowUp" ||
                        event.key === "ArrowDown" ||
                        event.key === "ArrowLeft" ||
                        event.key === "ArrowRight" ||
                        event.key === "Home" ||
                        event.key === "End"
                      ) {
                        event.preventDefault();
                        navigateNode(node.id, event.key);
                      }
                    }}
                  >
                    <rect className="atlas-node__body" width={NODE_WIDTH} height={NODE_HEIGHT} rx="10" />
                    <circle className="atlas-node__kind" cx="24" cy="25" r="10" />
                    <text className="atlas-node__symbol" x="24" y="29" textAnchor="middle">
                      {node.state === "hotspot"
                        ? "!"
                        : node.state === "contained" || node.state === "cleared"
                          ? "✓"
                          : "·"}
                    </text>
                    <text className="atlas-node__label" x="43" y="29">
                      {truncate(node.label, 20)}
                    </text>
                    <text className="atlas-node__meta" x="18" y="59">
                      {truncate(node.kind.replaceAll("_", " "), 20)}
                    </text>
                    {(node.evidenceCount || node.signalCount) && (
                      <text className="atlas-node__metric" x={NODE_WIDTH - 16} y="59" textAnchor="end">
                        {node.signalCount ? `${node.signalCount} signals` : `${node.evidenceCount} refs`}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
            ) : (
              <div className="atlas-empty">
                <Boxes size={28} />
                <strong>{loading ? "Mapping bounded evidence…" : emptyMessage}</strong>
              </div>
            )}
          </div>
          {showMinimap && visibleGraph.nodes.length > 1 && (
            <button
              type="button"
              className="atlas-minimap"
              aria-label="Graph minimap; click to recenter"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                const canvas = canvasRef.current;
                if (!canvas) return;
                const bounds = event.currentTarget.getBoundingClientRect();
                const worldX =
                  ((event.clientX - bounds.left) / bounds.width) * layout.width;
                const worldY =
                  ((event.clientY - bounds.top) / bounds.height) * layout.height;
                canvas.scrollTo({
                  left: Math.max(0, worldX * zoom - canvas.clientWidth / 2),
                  top: Math.max(0, worldY * zoom - canvas.clientHeight / 2),
                });
              }}
            >
              <svg viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
                {visibleGraph.edges.map((edge) => {
                  const source = positions.get(edge.sourceId);
                  const target = positions.get(edge.targetId);
                  if (!source || !target) return null;
                  return (
                    <line
                      key={edge.id}
                      x1={source.x + NODE_WIDTH / 2}
                      y1={source.y + NODE_HEIGHT / 2}
                      x2={target.x + NODE_WIDTH / 2}
                      y2={target.y + NODE_HEIGHT / 2}
                    />
                  );
                })}
                {visibleGraph.nodes.map((node) => {
                  const position = positions.get(node.id);
                  if (!position) return null;
                  return (
                    <rect
                      key={node.id}
                      className={node.id === selected?.id ? "active" : ""}
                      x={position.x}
                      y={position.y}
                      width={NODE_WIDTH}
                      height={NODE_HEIGHT}
                      rx="8"
                    />
                  );
                })}
                <rect
                  className="atlas-minimap__viewport"
                  x={viewport.x}
                  y={viewport.y}
                  width={Math.min(layout.width, viewport.width)}
                  height={Math.min(layout.height, viewport.height)}
                />
              </svg>
            </button>
          )}
        </div>

        <AtlasDetailPanel
          node={selected}
          edges={edges}
          nodes={nodes}
          onSelectNode={onSelectNode}
          onExploreNode={onExploreNode}
          pathStartNodeId={pathStartNodeId}
          onSetPathStart={onSetPathStart}
          onTracePath={onTracePath}
          loading={loading}
        />
      </div>

      {selected && (
        <div className="atlas-metric-strip" aria-label={`Metrics for ${selected.label}`}>
          {(selected.metrics.length
            ? selected.metrics.slice(0, 5)
            : [{ label: "Evidence references", value: selected.evidenceCount || 0 }]
          ).map((metric) => (
            <div key={`${metric.group}-${metric.label}`}>
              <span>{metric.group || "Metric"}</span>
              <strong>{metric.value}</strong>
              <small
                title={[
                  metric.definition,
                  metric.limitations,
                  metric.scope
                    ? `Scope: ${metric.scope.replaceAll("_", " ")}`
                    : "",
                ].filter(Boolean).join(" · ")}
              >
                {metric.label}
              </small>
            </div>
          ))}
        </div>
      )}
      <p className="atlas-visible-count" aria-live="polite">
        Showing {visibleGraph.nodes.length} of {nodes.length} surfaced nodes and{" "}
        {visibleGraph.edges.length} of {edges.length} relationships in the {lens} lens.
      </p>
    </section>
  );
}

function AtlasDetailPanel({
  node,
  edges,
  nodes,
  onSelectNode,
  onExploreNode,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  loading,
}: {
  node?: AtlasNodeView;
  edges: AtlasEdgeView[];
  nodes: AtlasNodeView[];
  onSelectNode: (nodeId: string) => void;
  onExploreNode?: RepositoryAtlasProps["onExploreNode"];
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  loading?: boolean;
}) {
  if (!node) {
    return (
      <aside className="atlas-detail">
        <p className="muted">Select a node to inspect its stored structure and metrics.</p>
      </aside>
    );
  }
  const relationships = edges.filter(
    (edge) => edge.sourceId === node.id || edge.targetId === node.id,
  );
  const outgoing = relationships.filter((edge) => edge.sourceId === node.id);
  const incoming = relationships.filter((edge) => edge.targetId === node.id);
  const byId = new Map(nodes.map((item) => [item.id, item]));
  const StateIcon =
    node.state === "hotspot"
      ? AlertTriangle
      : node.state === "contained" || node.state === "cleared"
        ? CheckCircle2
        : node.state === "inference"
          ? Layers3
          : CircleDot;

  return (
    <aside className="atlas-detail" aria-live="polite">
      <div className="atlas-detail__title">
        <span className={`atlas-state atlas-state--${node.state}`}><StateIcon size={15} /></span>
        <div>
          <span className="eyebrow">Selected node</span>
          <h3>{node.label}</h3>
        </div>
      </div>
      <code className="mono-path">{node.path}</code>
      <div className="atlas-detail__tags">
        <Badge tone={node.state === "hotspot" ? "warning" : "neutral"}>{node.kind}</Badge>
        <Badge
          tone={
            node.state === "contained" || node.state === "cleared" ? "success" : "neutral"
          }
        >
          {node.state}
        </Badge>
      </div>
      {node.description && <p>{node.description}</p>}
      {node.signals && node.signals.length > 0 && (
        <div className="atlas-detail__section">
          <strong><AlertTriangle size={13} /> Structural signals</strong>
          <ul className="evidence-list">
            {node.signals.map((signal, index) => (
              <li key={`${signal.code}-${index}`}>
                <code>{signal.code.replaceAll("-", " ")}</code>
                <p>{signal.message}</p>
                {signal.definition && <small>{signal.definition}</small>}
                <small>
                  {signal.nature === "structural_proxy"
                    ? "Structural proxy"
                    : "Objective signal"}
                  {signal.limitations ? ` · ${signal.limitations}` : ""}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
      {onExploreNode && (
        <div className="atlas-detail__section atlas-detail__actions">
          <strong><Layers3 size={13} /> Explore from here</strong>
          <div>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "children")}>
              Children
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "dependencies")}>
              Dependencies
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "dependants")}>
              Dependants
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "forward_neighbourhood", 2)}>
              2-hop view
            </button>
          </div>
        </div>
      )}
      {onSetPathStart && onTracePath && (
        <div className="atlas-detail__section atlas-detail__path">
          <strong><Route size={13} /> Dependency path</strong>
          {pathStartNodeId && pathStartNodeId !== node.id ? (
            <button type="button" disabled={loading} onClick={() => onTracePath(node.id)}>
              Trace from {byId.get(pathStartNodeId)?.label || "start"} to this node
            </button>
          ) : (
            <button type="button" disabled={loading} onClick={() => onSetPathStart(node.id)}>
              {pathStartNodeId === node.id ? "Path starts here" : "Use as path start"}
            </button>
          )}
        </div>
      )}
      <div className="atlas-detail__section">
        <strong><GitBranch size={13} /> Relationships</strong>
        <RelationshipGroup
          title="Outgoing"
          relationships={outgoing}
          nodeId={node.id}
          byId={byId}
          onSelectNode={onSelectNode}
        />
        <RelationshipGroup
          title="Incoming"
          relationships={incoming}
          nodeId={node.id}
          byId={byId}
          onSelectNode={onSelectNode}
        />
        {!relationships.length && <small>No surfaced relationship in this bounded view.</small>}
      </div>
    </aside>
  );
}

function RelationshipGroup({
  title,
  relationships,
  nodeId,
  byId,
  onSelectNode,
}: {
  title: string;
  relationships: AtlasEdgeView[];
  nodeId: string;
  byId: Map<string, AtlasNodeView>;
  onSelectNode: (nodeId: string) => void;
}) {
  if (!relationships.length) return null;
  return (
    <div className="atlas-relationship-group">
      <small>{title} · {relationships.length}</small>
      {relationships.slice(0, 6).map((edge) => {
        const otherId = edge.sourceId === nodeId ? edge.targetId : edge.sourceId;
        const other = byId.get(otherId);
        return (
          <button
            key={edge.id}
            type="button"
            disabled={!other}
            onClick={() => other && onSelectNode(other.id)}
          >
            <span>{edge.sourceId === nodeId ? "→" : "←"} {edge.kind}</span>
            <b>{other?.label || truncate(otherId, 18)}</b>
          </button>
        );
      })}
      {relationships.length > 6 && <small>+{relationships.length - 6} more surfaced relationships</small>}
    </div>
  );
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function edgeKindClass(kind: string) {
  return kind.replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "").toLocaleLowerCase();
}

function pointerDistance(
  first: { x: number; y: number },
  second: { x: number; y: number },
) {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function edgePath(
  source: { x: number; y: number },
  target: { x: number; y: number },
) {
  const sourceCenterX = source.x + NODE_WIDTH / 2;
  const sourceCenterY = source.y + NODE_HEIGHT / 2;
  const targetCenterX = target.x + NODE_WIDTH / 2;
  const targetCenterY = target.y + NODE_HEIGHT / 2;
  const vertical = Math.abs(targetCenterY - sourceCenterY) >= NODE_HEIGHT;
  if (vertical) {
    const downward = targetCenterY > sourceCenterY;
    const startY = source.y + (downward ? NODE_HEIGHT : 0);
    const endY = target.y + (downward ? 0 : NODE_HEIGHT);
    const middleY = (startY + endY) / 2;
    return `M ${sourceCenterX} ${startY} C ${sourceCenterX} ${middleY}, ${targetCenterX} ${middleY}, ${targetCenterX} ${endY}`;
  }
  const rightward = targetCenterX > sourceCenterX;
  const startX = source.x + (rightward ? NODE_WIDTH : 0);
  const endX = target.x + (rightward ? 0 : NODE_WIDTH);
  const middleX = (startX + endX) / 2;
  return `M ${startX} ${sourceCenterY} C ${middleX} ${sourceCenterY}, ${middleX} ${targetCenterY}, ${endX} ${targetCenterY}`;
}

function distance(
  left: { x: number; y: number },
  right: { x: number; y: number },
) {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}
