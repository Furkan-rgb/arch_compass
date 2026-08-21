import type { CSSProperties } from "react";

import type { Tone } from "../../lib/format";
import { Mark } from "../../ui/mark";
import { distance, edgeKindClass, edgePath, truncate } from "./geometry";
import type { AtlasEdgeView, AtlasNodeView } from "./graph";
import { NODE_HEIGHT, NODE_WIDTH, type AtlasLayout } from "./layout";
import { surfaceFor } from "./surface";
import type { AtlasPulse } from "./pulse";
import type { AtlasViewport } from "./viewport";
import type { VisibleGraph } from "./visible-graph";

/**
 * The map itself: the scrollable canvas, the cards and connectors drawn on it, and the minimap.
 *
 * Every colour here is a verdict or a hairline. A card a finding was made about wears the
 * finding's tone on its border and its mark; everything else is the same rule the rest of the
 * system separates with, because most of what is drawn here is the structure the shape was
 * found in and none of it is being graded.
 */

/**
 * The verdict hues, reached for on the cards that carry one.
 *
 * Indexed by the tone rather than written at the card: nothing here decides that a shape
 * should be red, it paints the tone a finding already has.
 */
const TONE_STROKE: Record<Tone, string> = {
  neutral: "var(--rule-strong)",
  marked: "var(--ink)",
  material: "var(--material)",
  held: "var(--held)",
  cleared: "var(--cleared)",
};

const TONE_MARK: Record<Tone, "alert" | "pause" | "check" | "hollow"> = {
  neutral: "hollow",
  marked: "hollow",
  material: "alert",
  held: "pause",
  cleared: "check",
};

export function AtlasCanvas({
  graph,
  layout,
  selected,
  onSelectNode,
  highlightedNodes,
  highlightedEdges,
  pulse,
  loading,
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
  emptyMessage: string;
  view: AtlasViewport;
  gridId: string;
  arrowId: string;
  instructionsId: string;
}) {
  const { positions } = layout;
  const { zoom } = view;

  /**
   * The drawn surface: the graph's own bounds, or the canvas, whichever is larger.
   *
   * The ground and the grid are painted at 100% of this, so a graph smaller than the panel
   * fills the panel rather than stopping at its own edge with bare background beyond it. The
   * origin stays at 0,0 and the scale stays `zoom`, so every camera sum in `viewport.ts` —
   * all of which map a world point to a scroll offset by multiplying — is untouched.
   */
  const {
    width: worldWidth,
    height: worldHeight,
    offsetX,
    offsetY,
  } = surfaceFor(layout, view.canvasSize, zoom);

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
        .map((edge) => (edge.sourceId === nodeId ? edge.targetId : edge.sourceId));
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
          return distance(current, leftPosition) - distance(current, rightPosition);
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
   * twice. That highlight is a different claim — it traces a route the reader asked for, and
   * the query service walks edges in both directions to find one, so a pulse following each
   * edge's own arrow would zigzag along a path that reads as a single journey.
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
   * SVG has no `z-index`: whatever is written last sits on top. On a dense graph that buries
   * the selected card under whichever neighbour happens to come later in `graph.nodes`, and
   * runs its connectors behind cards they ought to cross. So the selection paints last, its
   * neighbours just beneath it, and the edges joining them above the rest of the mesh. A
   * traced dependency path makes the same kind of claim on the reader's attention, so it
   * rides along in both tiers.
   *
   * With nothing selected and no path traced every test below is false, and the graph falls
   * back to its plain order: every edge, then every card.
   */
  const isRaisedEdge = (edge: AtlasEdgeView) =>
    edge.sourceId === selected?.id ||
    edge.targetId === selected?.id ||
    highlightedEdges.has(edge.id);
  const selectedNeighbours = new Set(
    selected
      ? graph.edges
          .filter((edge) => edge.sourceId === selected.id || edge.targetId === selected.id)
          .map((edge) => (edge.sourceId === selected.id ? edge.targetId : edge.sourceId))
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
        className={`atlas-edge ${connected ? "atlas-edge--active" : ""} atlas-edge--${edgeKindClass(edge.kind)} ${
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
    const stroke = node.tone ? TONE_STROKE[node.tone] : "var(--rule)";
    // The label starts where the mark leaves off, and a card with no verdict has no mark to
    // leave room for — a fixed indent on every card would open a column of nothing down the
    // side of a map that is mostly unjudged.
    const labelX = node.tone ? 40 : 18;
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
        aria-label={`${node.label}, ${node.kind.replaceAll("_", " ")}${
          node.tone ? ", judged" : ""
        }`}
        className={`atlas-node ${active ? "atlas-node--active" : ""} ${
          highlightedNodes.has(node.id) ? "atlas-node--path" : ""
        }`}
        transform={`translate(${position.x} ${position.y})`}
        onPointerDown={(event) => {
          // Keep card activation separate from the canvas pan gesture, which captures
          // pointers at the viewport.
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
        {/* The ring the selection wears. Outside the card rather than on it, so the border
            keeps saying what the verdict is while the ring says where the reader is. */}
        {active && (
          <rect
            className="atlas-node__ring"
            x={-5}
            y={-5}
            width={NODE_WIDTH + 10}
            height={NODE_HEIGHT + 10}
            rx={14}
          />
        )}
        <rect
          className="atlas-node__body"
          width={NODE_WIDTH}
          height={NODE_HEIGHT}
          rx={10}
          stroke={stroke}
          strokeWidth={node.tone ? 1.5 : 1}
        />
        {node.tone && (
          <g transform="translate(16 18)" color={stroke}>
            <Mark shape={TONE_MARK[node.tone]} width={15} height={15} />
          </g>
        )}
        <text className="atlas-node__label" x={labelX} y={31}>
          {truncate(node.label, node.tone ? 17 : 20)}
        </text>
        <text className="atlas-node__meta" x={18} y={59}>
          {truncate(node.kind.replaceAll("_", " "), 20)}
        </text>
        {/* A ternary rather than `&&`: a card carrying no signal has a count of zero, and
            `0 &&` renders the zero as the card's own caption. */}
        {node.signalCount ? (
          <text className="atlas-node__meta" x={NODE_WIDTH - 18} y={59} textAnchor="end">
            {node.signalCount} signals
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
            aria-label="The repository's structure, as this review read it"
            viewBox={`${-offsetX} ${-offsetY} ${worldWidth} ${worldHeight}`}
            width={worldWidth * zoom}
            height={worldHeight * zoom}
            style={{
              width: `${worldWidth * zoom}px`,
              height: `${worldHeight * zoom}px`,
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
            {/* Anchored on the viewBox rather than on world zero: `width="100%"` is the
                viewBox's width, but `x` defaults to world zero, which is `offsetX` to the
                right of the surface's left edge once the graph is centred. */}
            <rect
              className="atlas-canvas__background"
              x={-offsetX}
              y={-offsetY}
              width="100%"
              height="100%"
            />
            <rect
              fill={`url(#${gridId})`}
              x={-offsetX}
              y={-offsetY}
              width="100%"
              height="100%"
            />
            <g className="atlas-clusters" aria-hidden="true">
              {layout.clusters.map((cluster) => (
                <g key={cluster.id}>
                  <rect
                    x={cluster.x}
                    y={cluster.y}
                    width={cluster.width}
                    height={cluster.height}
                    rx="14"
                  />
                  <text x={cluster.x + 16} y={cluster.y + 22}>
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
            {/* The selected card's own connectors, lifted clear of the cards they cross. */}
            <g aria-hidden="true">{graph.edges.filter(isRaisedEdge).map(renderEdge)}</g>
            {/* Drawn over every edge and under every card, and never onto the edge itself:
                the dashed kinds already own `stroke-dasharray`, and a pulse written into
                `.atlas-edge` would quietly erase the distinction those dashes carry. */}
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
                    /* Normalised, so the dash means the same fraction of a long edge and a
                       short one and the whole neighbourhood pulses at one speed. */
                    pathLength={100}
                    style={{ "--atlas-pulse-rank": rank } as CSSProperties}
                  />
                );
              })}
            </g>
            {/* Neighbours over the crowd, and the selection itself over everything — the card
                the reader just asked about should never sit under another. */}
            {graph.nodes.filter(isRaisedNode).map(renderNode)}
            {graph.nodes.filter((node) => node.id === selected?.id).map(renderNode)}
          </svg>
        ) : (
          <p className="atlas-empty">{loading ? "Reading the atlas…" : emptyMessage}</p>
        )}
      </div>
      {view.showMinimap && graph.nodes.length > 1 && (
        <button
          type="button"
          className="atlas-minimap"
          aria-label="Graph minimap; click to recentre"
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
                  className={`atlas-minimap__card ${node.id === selected?.id ? "active" : ""}`}
                  x={position.x}
                  y={position.y}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="8"
                  style={node.tone ? { fill: TONE_STROKE[node.tone] } : undefined}
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
