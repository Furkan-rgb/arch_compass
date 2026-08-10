/** The map itself: the scrollable canvas, the cards and connectors drawn on it, and the minimap. */

import { Boxes } from "lucide-react";
import type { CSSProperties } from "react";

import { NODE_HEIGHT, NODE_WIDTH, type AtlasLayout } from "../atlas-layout";
import { distance, edgePath } from "./geometry";
import type { AtlasEdgeView, AtlasNodeView, RepositoryAtlasProps } from "./graph-model";
import { edgeKindClass, truncate } from "./labels";
import type { AtlasPulse } from "./pulse";
import type { AtlasViewport } from "./use-atlas-viewport";
import type { VisibleGraph } from "./visible-graph";

export function AtlasCanvas({
  graph,
  layout,
  selected,
  onSelectNode,
  highlightedNodes,
  highlightedEdges,
  pulse,
  loading,
  mode,
  emptyMessage,
  view,
  gridId,
  arrowId,
  instructionsId,
}: {
  graph: VisibleGraph;
  layout: AtlasLayout;
  selected: AtlasNodeView | undefined;
  onSelectNode: (nodeId: string | null) => void;
  /** Nodes and edges on a traced dependency path, which paint above the rest of the mesh. */
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  pulse: AtlasPulse;
  loading: boolean;
  mode: NonNullable<RepositoryAtlasProps["mode"]>;
  emptyMessage: string;
  view: AtlasViewport;
  gridId: string;
  arrowId: string;
  instructionsId: string;
}) {
  const { positions } = layout;
  const { zoom } = view;

  const navigateNode = (
    nodeId: string,
    key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Home" | "End",
  ) => {
    const sorted = [...graph.nodes].sort((left, right) => {
      const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
      const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
      return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x;
    });
    let next: AtlasNodeView | undefined;
    if (key === "Home") next = sorted[0];
    else if (key === "End") next = sorted.at(-1);
    else {
      const relatedIds = graph.edges
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
    window.requestAnimationFrame(() => view.nodeRefs.current.get(next!.id)?.focus());
  };

  /**
   * The relationships a pulse is drawn along: the selected node's own, and no others.
   *
   * An edge already carrying the dependency-path highlight is left out rather than drawn
   * twice. That highlight is a different claim — it traces a route the reader asked for,
   * and `query_service` walks edges in both directions to find one, so a pulse following
   * each edge's own arrow would zigzag along a path that reads as a single journey.
   */
  const pulseEdges =
    selected && pulse !== "none" && pulse !== "breathe"
      ? graph.edges.filter(
          (edge) =>
            edge.sourceId !== edge.targetId &&
            !highlightedEdges.has(edge.id) &&
            (edge.sourceId === selected.id || edge.targetId === selected.id),
        )
      : [];

  /**
   * What gets lifted out of the ordinary paint order, and why there is an order at all.
   *
   * SVG has no `z-index`: whatever is written last sits on top. On a dense graph that
   * buries the selected card under whichever neighbour happens to come later in
   * `graph.nodes`, and runs its connectors behind cards they ought to cross. So
   * the selection paints last, its neighbours just beneath it, and the edges joining
   * them above the rest of the mesh. A traced dependency path makes the same kind of
   * claim on the reader's attention, so it rides along in both tiers.
   *
   * With nothing selected and no path traced every test below is false, and the graph
   * falls back to its plain order: every edge, then every node.
   */
  const isRaisedEdge = (edge: AtlasEdgeView) =>
    edge.sourceId === selected?.id ||
    edge.targetId === selected?.id ||
    highlightedEdges.has(edge.id);
  const selectedNeighbours = new Set(
    selected
      ? graph.edges
          .filter(
            (edge) => edge.sourceId === selected.id || edge.targetId === selected.id,
          )
          .map((edge) =>
            edge.sourceId === selected.id ? edge.targetId : edge.sourceId,
          )
      : [],
  );
  const isRaisedNode = (node: AtlasNodeView) =>
    node.id !== selected?.id &&
    (selectedNeighbours.has(node.id) || highlightedNodes.has(node.id));

  const renderEdge = (edge: AtlasEdgeView) => {
    const source = positions.get(edge.sourceId);
    const target = positions.get(edge.targetId);
    if (!source || !target || edge.sourceId === edge.targetId) return null;
    const connected = edge.sourceId === selected?.id || edge.targetId === selected?.id;
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
  };

  const renderNode = (node: AtlasNodeView) => {
    const position = positions.get(node.id);
    if (!position) return null;
    const active = node.id === selected?.id;
    return (
      <g
        key={node.id}
        ref={(element) => {
          if (element) view.nodeRefs.current.set(node.id, element);
          else view.nodeRefs.current.delete(node.id);
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
          view.beginNodePress();
        }}
        onClick={(event) => {
          event.stopPropagation();
          view.selectNode(node.id);
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
        {/* The ring ripple sends outward. Invisible in every other mode, and
            rendered only for the selected node so nothing else can ring. */}
        {active && (
          <rect
            className="atlas-node__halo"
            width={NODE_WIDTH}
            height={NODE_HEIGHT}
            rx="10"
          />
        )}
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
        {/* A ternary rather than `&&`: a node carrying no signal has a count of
            zero, and `0 &&` renders the zero as the node's own caption. */}
        {node.signalCount || node.evidenceCount ? (
          <text className="atlas-node__metric" x={NODE_WIDTH - 16} y="59" textAnchor="end">
            {node.signalCount ? `${node.signalCount} signals` : `${node.evidenceCount} refs`}
          </text>
        ) : null}
      </g>
    );
  };

  return (
    <div className="atlas-viewport">
      <div
        ref={view.canvasRef}
        className={`atlas-canvas ${view.panning ? "atlas-canvas--panning" : ""}`}
        role="region"
        tabIndex={0}
        aria-label="Scrollable graph viewport"
        aria-describedby={instructionsId}
        aria-busy={loading}
        onPointerDown={view.beginPan}
        onPointerMove={view.pan}
        onPointerUp={view.endPan}
        onPointerCancel={view.endPan}
        onScroll={view.updateViewport}
        onClick={view.deselectBackground}
      >
        {graph.nodes.length ? (
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
          data-pulse={pulse}
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
          {/* The mesh the selection is not part of, under the cards it is not part of. */}
          <g aria-hidden="true">
            {graph.edges.filter((edge) => !isRaisedEdge(edge)).map(renderEdge)}
          </g>
          {graph.nodes
            .filter((node) => node.id !== selected?.id && !isRaisedNode(node))
            .map(renderNode)}
          {/* The selected node's own connectors, lifted clear of the cards they cross. */}
          <g aria-hidden="true">
            {graph.edges.filter(isRaisedEdge).map(renderEdge)}
          </g>
          {/* Drawn over every edge and under every node, and never onto the edge itself:
              `--kind-tests`, `--kind-configures` and `--risk` already own
              `stroke-dasharray`, and a pulse written into `.atlas-edge` would quietly
              erase the distinction those dashes carry. */}
          <g aria-hidden="true">
            {pulseEdges.map((edge, rank) => {
              const source = positions.get(edge.sourceId);
              const target = positions.get(edge.targetId);
              if (!source || !target) return null;
              return (
                <path
                  key={edge.id}
                  className={`atlas-pulse ${
                    edge.targetId === selected?.id ? "atlas-pulse--incoming" : ""
                  }`}
                  d={edgePath(source, target)}
                  /* Normalised, so the dash means the same fraction of a long edge and
                     a short one and the whole neighbourhood pulses at one speed. */
                  pathLength={100}
                  style={{ "--atlas-pulse-rank": rank } as CSSProperties}
                />
              );
            })}
          </g>
          {/* Neighbours over the crowd, and the selection itself over everything —
              the card the reader just asked about should never sit under another. */}
          {graph.nodes.filter(isRaisedNode).map(renderNode)}
          {graph.nodes
            .filter((node) => node.id === selected?.id)
            .map(renderNode)}
        </svg>
        ) : (
          <div className="atlas-empty">
            <Boxes size={28} />
            <strong>{loading ? "Mapping bounded evidence…" : emptyMessage}</strong>
          </div>
        )}
      </div>
      {view.showMinimap && graph.nodes.length > 1 && (
        <button
          type="button"
          className="atlas-minimap"
          aria-label="Graph minimap; click to recenter"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            view.centreOn(
              ((event.clientX - bounds.left) / bounds.width) * layout.width,
              ((event.clientY - bounds.top) / bounds.height) * layout.height,
            );
          }}
        >
          <svg viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
            {graph.edges.map((edge) => {
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
            {graph.nodes.map((node) => {
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
              x={view.viewport.x}
              y={view.viewport.y}
              width={Math.min(layout.width, view.viewport.width)}
              height={Math.min(layout.height, view.viewport.height)}
            />
          </svg>
        </button>
      )}
    </div>
  );
}
