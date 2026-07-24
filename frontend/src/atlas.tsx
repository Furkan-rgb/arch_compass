import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  CircleDot,
  GitBranch,
  Layers3,
  Maximize2,
  Minus,
  Plus,
} from "lucide-react";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

import { Badge } from "./components";

export type AtlasNodeState = "normal" | "hotspot" | "contained" | "inference";

export interface AtlasMetricView {
  label: string;
  value: number | string;
  group?: string;
}

export interface AtlasNodeView {
  id: string;
  label: string;
  path: string;
  kind: string;
  state: AtlasNodeState;
  description?: string;
  metrics: AtlasMetricView[];
  evidenceCount?: number;
  signalCount?: number;
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
  onSelectNode: (nodeId: string) => void;
  loading?: boolean;
  emptyMessage?: string;
}

const NODE_WIDTH = 164;
const NODE_HEIGHT = 66;
const MIN_CANVAS_WIDTH = 920;
const X_GAP = 42;
const Y_GAP = 64;
const PADDING_X = 44;
const PADDING_Y = 42;
const MIN_ZOOM = .45;
const MAX_ZOOM = 1.8;
const ZOOM_STEP = .15;

export interface AtlasLayout {
  positions: Map<string, { x: number; y: number }>;
  width: number;
  height: number;
  levels: Map<string, number>;
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
): AtlasLayout {
  if (!nodes.length) {
    return {
      positions: new Map(),
      width: MIN_CANVAS_WIDTH,
      height: 360,
      levels: new Map(),
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

  const maximumLayerSize = Math.max(1, ...[...layers.values()].map((layer) => layer.length));
  const graphWidth =
    maximumLayerSize * NODE_WIDTH +
    Math.max(0, maximumLayerSize - 1) * X_GAP +
    PADDING_X * 2;
  const width = Math.max(MIN_CANVAS_WIDTH, graphWidth);
  const height = Math.max(
    360,
    orderedLevels.length * NODE_HEIGHT +
      Math.max(0, orderedLevels.length - 1) * Y_GAP +
      PADDING_Y * 2,
  );
  const positions = new Map<string, { x: number; y: number }>();
  orderedLevels.forEach((level, levelIndex) => {
    const layer = layers.get(level)!;
    const layerWidth =
      layer.length * NODE_WIDTH + Math.max(0, layer.length - 1) * X_GAP;
    const startX = (width - layerWidth) / 2;
    layer.forEach((node, index) =>
      positions.set(node.id, {
        x: startX + index * (NODE_WIDTH + X_GAP),
        y: PADDING_Y + levelIndex * (NODE_HEIGHT + Y_GAP),
      }),
    );
  });
  return { positions, width, height, levels };
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
}: RepositoryAtlasProps) {
  const layout = useMemo(() => layoutAtlas(nodes, edges), [edges, nodes]);
  const { positions } = layout;
  const selected = nodes.find((node) => node.id === selectedNodeId) || nodes[0];
  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef(new Map<string, SVGGElement>());
  const drag = useRef<{
    pointerId: number;
    x: number;
    y: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  const suppressNodeClick = useRef(false);
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const setViewportZoom = (requested: number) => {
    const next = clamp(requested, MIN_ZOOM, MAX_ZOOM);
    const canvas = canvasRef.current;
    if (!canvas || next === zoom) return;
    const worldX = (canvas.scrollLeft + canvas.clientWidth / 2) / zoom;
    const worldY = (canvas.scrollTop + canvas.clientHeight / 2) / zoom;
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: worldX * next - canvas.clientWidth / 2,
        top: worldY * next - canvas.clientHeight / 2,
      });
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

  useEffect(() => {
    fitGraph();
    // Refit only when topology changes its overall bounds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.height, layout.width]);

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
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    suppressNodeClick.current = false;
    canvas.setPointerCapture?.(event.pointerId);
    setPanning(true);
  };

  const pan = (event: ReactPointerEvent<HTMLDivElement>) => {
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
    if (drag.current?.pointerId !== event.pointerId) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    drag.current = null;
    setPanning(false);
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      setViewportZoom(zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
      return;
    }
    if (event.shiftKey && event.deltaY) {
      event.preventDefault();
      event.currentTarget.scrollLeft += event.deltaY;
    }
  };

  const selectNode = (nodeId: string) => {
    if (suppressNodeClick.current) {
      suppressNodeClick.current = false;
      return;
    }
    onSelectNode(nodeId);
  };

  const navigateNode = (
    nodeId: string,
    key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Home" | "End",
  ) => {
    const sorted = [...nodes].sort((left, right) => {
      const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
      const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
      return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x;
    });
    let next: AtlasNodeView | undefined;
    if (key === "Home") next = sorted[0];
    else if (key === "End") next = sorted.at(-1);
    else {
      const relatedIds = edges
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
    <section className="atlas-panel" aria-labelledby="atlas-heading">
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

      <div className="atlas-toolbar">
        <div className="atlas-legend" aria-label="Atlas legend">
          <span><CircleDot size={13} /> Normal</span>
          <span><AlertTriangle size={13} /> Hotspot</span>
          <span><CheckCircle2 size={13} /> Contained</span>
          {mode === "greenfield" && <span><Layers3 size={13} /> Advisor inference</span>}
        </div>
        <span className="atlas-toolbar__hint" id={instructionsId}>
          Drag to pan · scroll to move · Ctrl/⌘ + scroll to zoom
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
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div className="atlas-layout">
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
          onWheel={handleWheel}
        >
          {nodes.length ? (
            <svg
              role="tree"
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
              <g aria-hidden="true">
                {edges.map((edge) => {
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
                      }`}
                      d={edgePath(source, target)}
                      markerEnd={`url(#${arrowId})`}
                    />
                  );
                })}
              </g>
              {nodes.map((node) => {
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
                    role="treeitem"
                    tabIndex={0}
                    aria-selected={active}
                    aria-label={`${node.label}, ${node.kind}, ${node.state}`}
                    className={`atlas-node atlas-node--${node.state} ${active ? "atlas-node--active" : ""}`}
                    transform={`translate(${position.x} ${position.y})`}
                    onClick={() => selectNode(node.id)}
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
                    <rect className="atlas-node__body" width={NODE_WIDTH} height={NODE_HEIGHT} rx="9" />
                    <circle className="atlas-node__kind" cx="21" cy="22" r="9" />
                    <text className="atlas-node__symbol" x="21" y="26" textAnchor="middle">
                      {node.state === "hotspot" ? "!" : node.state === "contained" ? "✓" : "·"}
                    </text>
                    <text className="atlas-node__label" x="38" y="24">
                      {truncate(node.label, 19)}
                    </text>
                    <text className="atlas-node__meta" x="16" y="49">
                      {truncate(node.kind.replaceAll("_", " "), 18)}
                    </text>
                    {(node.evidenceCount || node.signalCount) && (
                      <text className="atlas-node__metric" x={NODE_WIDTH - 14} y="49" textAnchor="end">
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

        <AtlasDetailPanel
          node={selected}
          edges={edges}
          nodes={nodes}
          onSelectNode={onSelectNode}
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
              <small>{metric.label}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function AtlasDetailPanel({
  node,
  edges,
  nodes,
  onSelectNode,
}: {
  node?: AtlasNodeView;
  edges: AtlasEdgeView[];
  nodes: AtlasNodeView[];
  onSelectNode: (nodeId: string) => void;
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
  const byId = new Map(nodes.map((item) => [item.id, item]));
  const StateIcon =
    node.state === "hotspot"
      ? AlertTriangle
      : node.state === "contained"
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
        <Badge tone={node.state === "contained" ? "success" : "neutral"}>{node.state}</Badge>
      </div>
      {node.description && <p>{node.description}</p>}
      <div className="atlas-detail__section">
        <strong><GitBranch size={13} /> Relationships</strong>
        {relationships.slice(0, 8).map((edge) => {
          const otherId = edge.sourceId === node.id ? edge.targetId : edge.sourceId;
          const other = byId.get(otherId);
          return (
            <button key={edge.id} type="button" onClick={() => other && onSelectNode(other.id)}>
              <span>{edge.sourceId === node.id ? "→" : "←"} {edge.kind}</span>
              <b>{other?.label || truncate(otherId, 18)}</b>
            </button>
          );
        })}
        {!relationships.length && <small>No surfaced relationship in this bounded view.</small>}
      </div>
    </aside>
  );
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
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
