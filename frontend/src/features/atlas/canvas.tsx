import { useMemo, useRef, type CSSProperties } from "react";

import { splitQualified, type Tone } from "../../lib/format";
import { Button } from "../../ui/button";
import { Mark } from "../../ui/mark";
import {
  CLUSTER_LABEL_SIZE,
  CLUSTER_LABEL_TRACKING,
  META_SIZE,
  META_TRACKING,
  distance,
  edgeKindClass,
  edgePath,
  fitCharacters,
  monoAdvance,
  truncate,
} from "./geometry";
import type { AtlasEdgeView, AtlasNodeView } from "./graph";
import { NODE_HEIGHT, NODE_WIDTH, type AtlasClusterRegion, type AtlasLayout } from "./layout";
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
 *
 * **The graphic tier, because everything this paints is a graphic.** Two of the three uses are
 * an SVG `stroke` — a card's border and a node's ring — and the third is the `fill` of a
 * minimap rect a few pixels tall, which is a mark rather than a ground. The design system splits
 * each signal on the WCAG line: the bare token is text and clears 4.5:1, the `-edge` token is
 * edges, glyphs, bars and dots and clears 3:1. This map held the text tier for a revision, which
 * drew the loudest thing on the surface in the quietest of the two values available to it.
 *
 * `neutral` and `marked` keep their tokens because neither is a verdict and neither has a signal
 * to spend. And the minimap rect is deliberately not read as a chromatic fill under the rule
 * that caps those at a badge: it is the same dot the map draws, shrunk, and its whole job is to
 * be a coloured mark on a neutral ground.
 *
 * These are `var()` strings rather than utility classes because they reach SVG attributes, and
 * that is worth knowing: `ui/verdict-hues.test.ts` scans class lists, so nothing in the suite can
 * see a tier mistake made here. The comment is the guard.
 */
const TONE_STROKE: Record<Tone, string> = {
  neutral: "var(--rule-strong)",
  marked: "var(--ink)",
  material: "var(--material-edge)",
  held: "var(--held-edge)",
  cleared: "var(--cleared-edge)",
};

const TONE_MARK: Record<Tone, "alert" | "pause" | "check" | "hollow"> = {
  neutral: "hollow",
  marked: "hollow",
  material: "alert",
  held: "pause",
  cleared: "check",
};

/** The card's own left and right margin, and the gap `dx` puts between the kind and the verdict. */
const CARD_INSET = 18;
const VERDICT_GAP = 7;

/** Where a cluster's label starts inside its enclosure, and therefore its margin on both sides. */
const CLUSTER_INSET = 16;

/**
 * A cluster's name and how many cards it holds, cut to the region it is drawn inside.
 *
 * The enclosure is sized from the cards in it and the label was cut to a fixed thirty-four
 * characters, which is a budget with no relationship to that width: a two-card column is 246
 * units across and a thirty-four character package name is about 350, so the name ran a
 * hundred units past the region it names, over whatever cards sat to the right. The count is
 * measured into the same budget rather than added after it, because the count is the part that
 * tells two same-named regions apart.
 */
function clusterCaption(cluster: AtlasClusterRegion) {
  const count = ` · ${cluster.nodeIds.length}`;
  const room = fitCharacters(
    cluster.width - CLUSTER_INSET * 2,
    CLUSTER_LABEL_SIZE,
    CLUSTER_LABEL_TRACKING,
  );
  return `${truncate(cluster.label, Math.max(4, room - count.length))}${count}`;
}

/**
 * Why the map is blank, and the way back.
 *
 * The canvas used to print the caller's `emptyMessage` whenever the node count was zero,
 * whatever had emptied it — so a reader who pressed "Public only" was told the review's
 * elements were no longer in the indexed atlas. That is a false statement of cause, and
 * telling an empty answer apart from a broken control is the thing the experience doc asks
 * this surface for by name. The reason is worked out where the lens and the filters are
 * known, which is not here, and arrives already knowing which of the three it is.
 */
export type AtlasEmptyAnswer = {
  sentence: string;
  /** Whatever undoes it: switch to a lens that draws something, clear the filters that bite. */
  action?: { label: string; onAction: () => void };
};

export function AtlasCanvas({
  graph,
  layout,
  selected,
  onSelectNode,
  highlightedNodes,
  highlightedEdges,
  matchedNodes,
  pulse,
  loading,
  empty,
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
  /** Every card the reader's search term matched, ringed so the count beside Find is checkable. */
  matchedNodes: Set<string>;
  pulse: AtlasPulse;
  loading: boolean;
  empty: AtlasEmptyAnswer;
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

  /**
   * Reading order: down the map, then across. `navigateNode` walks it, `Home` and `End` are
   * its two ends, and the first card in it is where the keyboard comes in.
   *
   * Memoised because a pan re-renders this component on every scroll frame and a full sort of
   * every card is not something to pay for when nothing about the cards has moved. It changes
   * only when the graph or its placement does.
   */
  const sorted = useMemo(
    () =>
      [...graph.nodes].sort((left, right) => {
        const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
        const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
        return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x;
      }),
    [graph, positions],
  );

  /** The drawn minimap, measured to map a click through its letterbox rather than round it. */
  const minimapRef = useRef<SVGSVGElement>(null);

  /**
   * Which region each card sits in, so the card can say so in its accessible name.
   *
   * The enclosures are `aria-hidden` on the canvas and correctly so — an SVG path is not
   * something to announce — but that left the layer saying which package or module a card
   * belongs to reachable only by looking at the picture, and the detail panel that calls
   * itself the map's only text equivalent never mentions a region either. The fact travels on
   * the card instead, which is the route a keyboard reader is already walking.
   */
  const clusterLabels = useMemo(() => {
    const byNode = new Map<string, string>();
    for (const cluster of layout.clusters) {
      for (const nodeId of cluster.nodeIds) byNode.set(nodeId, cluster.label);
    }
    return byNode;
  }, [layout.clusters]);

  /**
   * The card that holds the tab stop while nothing is selected.
   *
   * Every card was `tabIndex={-1}` until one was selected, and nothing is selected when the
   * surface opens — so the arrow-key walk below, which is the only way to read this map
   * without a pointer, could not be reached at all. One card takes the stop, the rest stay at
   * -1, and from there the arrows own the movement. That is the roving pattern the tabs and
   * the docket already use.
   */
  const keyboardEntry = selected ? undefined : sorted[0]?.id;

  const navigateNode = (
    nodeId: string,
    key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Home" | "End",
  ) => {
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
  // Memoised for the same reason `sorted` is: a pass over every edge on every scroll frame is
  // work that a pan cannot possibly have changed the answer to.
  const selectedNeighbours = useMemo(
    () =>
      new Set(
        selected
          ? graph.edges
              .filter((edge) => edge.sourceId === selected.id || edge.targetId === selected.id)
              .map((edge) => (edge.sourceId === selected.id ? edge.targetId : edge.sourceId))
          : [],
      ),
    [graph, selected],
  );
  const isRaisedNode = (node: AtlasNodeView) =>
    node.id !== selected?.id &&
    (selectedNeighbours.has(node.id) || highlightedNodes.has(node.id));

  const renderEdge = (edge: AtlasEdgeView) => {
    const source = positions.get(edge.sourceId);
    const target = positions.get(edge.targetId);
    if (!source || !target) return null;
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
    /**
     * An unjudged card's edge, one step up from the hairline the rest of the system separates
     * with.
     *
     * On the Structure lens almost every card is unjudged, so almost every card on screen was
     * a white box on a near-white ground behind a border a reader could not resolve — 1.14:1
     * in light — and the map read as floating labels rather than as objects. `--rule-strong`
     * does not reach 3:1 either, and the honest note beside that is that a card's real edge is
     * its fill interrupting the grid. It is still the right step: `design-system.md`'s own
     * line is that a rule separates and a border belongs to something you could pick up, and
     * this card is a `role="button"`. What it is not is `--ink-3` — on the Structure lens that
     * would outline every card at 5.86:1 and out-shout the toned cards the tone system exists
     * to make loud.
     */
    const stroke = node.tone ? TONE_STROKE[node.tone] : "var(--rule-strong)";
    // The label starts where the mark leaves off, and a card with no verdict has no mark to
    // leave room for — a fixed indent on every card would open a column of nothing down the
    // side of a map that is mostly unjudged.
    const labelX = node.tone ? 40 : CARD_INSET;
    const kind = node.kind.replaceAll("_", " ");
    const leaf = truncate(node.label, node.tone ? 17 : 20);
    /**
     * The segment that tells two cut labels apart, drawn only where one was cut.
     *
     * `PaymentGatewayAdapter` draws as `PaymentGatewayA…`, and so does every other class whose
     * first sixteen characters match — at which point the card names nothing. The namespace's
     * last segment is what is left to identify it by, and it costs a line the card has spare.
     * A leaf that fits is already an identifier and gets the card to itself.
     */
    const namespace =
      leaf === node.label ? "" : splitQualified(node.qualified).namespace.split(".").at(-1) || "";
    /**
     * How much of a meta row fits, measured against the room the card actually has.
     *
     * Three strings shared the lower baseline on fixed character budgets — the kind from the
     * left, the verdict after it, and a signal count anchored right — with nothing measuring
     * between them, so a judged card that had raised a signal drew the verdict word and the
     * count on top of one another. The count has gone to the detail panel, where it is
     * qualified by what each signal *is*; what is left is measured. The budget starts at the
     * indent rather than at the card's edge, so a toned card's row is cut for the mark beside
     * it instead of running under it.
     */
    const metaRoom = NODE_WIDTH - labelX - CARD_INSET;
    const verdictRoom = node.verdictLabel
      ? monoAdvance(META_SIZE, META_TRACKING) * node.verdictLabel.length + VERDICT_GAP
      : 0;
    /**
     * The region, phrased so that it survives both shapes of label a box can carry.
     *
     * `layout.ts` names an enclosure either for the element that really contains it —
     * `domain` — or, where its members share nothing but graph distance, for the element the
     * community grew around: `around Billing`. One "in" in front of both announced the second
     * as "in around Billing", and a reader hearing the card rather than seeing it has no way
     * to tell that the clumsy half is the layout's caption and not part of the card's name.
     */
    const region = clusterLabels.get(node.id);
    const regionPhrase = !region ? "" : region.startsWith("around ") ? region : `in ${region}`;
    return (
      <g
        key={node.id}
        ref={(element) => {
          if (element) view.nodeRefs.current.set(node.id, element);
          else view.nodeRefs.current.delete(node.id);
        }}
        data-atlas-node-id={node.id}
        role="button"
        tabIndex={active || node.id === keyboardEntry ? 0 : -1}
        aria-pressed={active}
        /* The whole qualified name, the region the map drew round it, and the verdict in the
           word rather than in the hue. This read `${node.label}, ${node.kind}, judged` — the
           leaf, already cut to seventeen characters, and one word that said the same thing for
           a material finding and a cleared one. `orders` is not an identity when three
           packages have one, and a colour never carries meaning alone.

           The region is here because the enclosures are `aria-hidden` and belong that way, so
           without it the whole grouping layer of the map was reachable only by looking at it. */
        aria-label={`${node.qualified}, ${kind}${regionPhrase ? `, ${regionPhrase}` : ""}${
          node.verdictLabel ? `, ${node.verdictLabel}` : ""
        }`}
        /* The kernel's placement arrives as a settling rather than as a swap.
           `placement.ts` paints the synchronous layout first and replaces it a few hundred
           milliseconds later with the kernel's, and every card was somewhere else at once,
           with the camera refitting under it — the reader's first impression of the surface
           was the map being pulled out from under them. A `transform` on a card changes only
           when the placement does: a pan moves the scroll offset and a zoom resizes the SVG,
           and neither touches this. The system's own curve, at the duration `--animate-expand`
           opens a row with, and the global reduced-motion block collapses it to nothing. */
        className={`atlas-node transition-transform duration-[240ms] ease-[cubic-bezier(0.22,0.7,0.3,1)] ${
          active ? "atlas-node--active" : ""
        } ${highlightedNodes.has(node.id) ? "atlas-node--path" : ""}`}
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
        {/* The whole name, on hover, for nothing: a native SVG tooltip is the one place the
            map can carry a string this long without covering the neighbours it was consulted
            about. First child because that is where the user agent looks for it. */}
        <title>{node.qualified}</title>
        {/* The ring a card wears when the reader's search term matched it. Every match, not
            one of them: a term with nine hits used to select an arbitrary card and leave the
            other eight unmarked. */}
        {matchedNodes.has(node.id) && (
          <rect
            className="atlas-node__match"
            x={-3}
            y={-3}
            width={NODE_WIDTH + 6}
            height={NODE_HEIGHT + 6}
            rx={12}
          />
        )}
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
        {namespace ? (
          <text className="atlas-node__meta" x={labelX} y={16}>
            {truncate(namespace, fitCharacters(metaRoom, META_SIZE, META_TRACKING))}
          </text>
        ) : null}
        <text className="atlas-node__label" x={labelX} y={31}>
          {leaf}
        </text>
        {/* The verdict beside the kind, on the whole width the card has now that the signal
            count is not competing for it. A card had a hue on its border and a mark inside it
            and nowhere at all did it say Material, Held or Cleared — the hue was carrying the
            meaning by itself, which is the one thing the charter says a hue may never do.

            `labelX`, not the card's own inset: this line used to start twenty-two units left
            of the two above it, so every card carrying a verdict — the ones the Judged lens
            exists to show — had two of its three rows on one left edge and the third hanging
            under the mark. */}
        <text className="atlas-node__meta" x={labelX} y={59}>
          {truncate(kind, fitCharacters(metaRoom - verdictRoom, META_SIZE, META_TRACKING))}
          {node.verdictLabel ? (
            <tspan className="atlas-node__verdict" dx={VERDICT_GAP}>
              {node.verdictLabel}
            </tspan>
          ) : null}
        </text>
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
        /* Coalesced to a frame: a drag writes the scroll offset directly, and a scroll event
           per pointermove is a render of every card, every edge and the minimap. */
        onScroll={view.scheduleViewportUpdate}
        onClick={view.deselectBackground}
      >
        {graph.nodes.length ? (
          <svg
            role="group"
            /* Not "the repository", and not "as this review read it" either. The first is the
               claim the surface's own header exists to deny — a map that let a reader believe
               it showed the repository as it stands now would be the more dangerous kind of
               wrong — and the second hardcodes a review into a component that knows nothing
               about reviews. What this draws is the graph its caller handed it. */
            aria-label="The structure this map was given"
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
              {/* Sized in world units rather than in multiples of the stroke that carries it.
                  A hairline is 1 unit wide, so `markerWidth="5"` was five units — 2.4 CSS
                  pixels once the map is framed, which is a smudge rather than an arrowhead,
                  on the one lens whose whole subject is direction. Which way it points is
                  said once, in the toolbar, rather than guessed at from a triangle. */}
              <marker
                id={arrowId}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerUnits="userSpaceOnUse"
                markerWidth="13"
                markerHeight="13"
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
                  <text x={cluster.x + CLUSTER_INSET} y={cluster.y + 22}>
                    {clusterCaption(cluster)}
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
          /* Why, and the way out of it. A blank map with one sentence that is not about what
             actually emptied it is worse than a blank map: the reader believes the sentence
             and stops looking for the control they just pressed. */
          <div className="atlas-empty">
            {/* The wait, drawn as what is coming rather than described.

                The review context read is the largest thing this surface fetches — a real one
                is a couple of megabytes — and it was answered by one centred grey line in an
                otherwise empty area up to 900px tall, under a full row of controls a reader
                could already operate over nothing. Cards at the card's own proportions, on the
                card's own ground, say what the shape of the answer will be. `--control` and
                not `--sunken`, because the canvas is `--sunken` now and a skeleton in the
                colour of the ground it sits on is not a skeleton. */}
            {loading ? (
              <div aria-hidden="true" className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                {Array.from({ length: 6 }, (_, index) => (
                  <div
                    key={index}
                    className="animate-shimmer rounded-[10px] border border-rule bg-control"
                    style={{
                      width: NODE_WIDTH / 2,
                      height: NODE_HEIGHT / 2,
                      // Staggered so the field reads as a map arriving rather than as one
                      // block pulsing. Reduced motion collapses every duration to nothing,
                      // which leaves six still cards — which is the point of them.
                      animationDelay: `${index * 90}ms`,
                    }}
                  />
                ))}
              </div>
            ) : null}
            <p>{loading ? "Reading the atlas…" : empty.sentence}</p>
            {!loading && empty.action ? (
              <Button variant="secondary" size="sm" onClick={empty.action.onAction}>
                {empty.action.label}
              </Button>
            ) : null}
          </div>
        )}
      </div>
      {view.showMinimap && graph.nodes.length > 1 && (
        /**
         * The whole surface in miniature, in the surface's own coordinates.
         *
         * It drew the *layout* box and mapped a click through it, while `surfaceFor` centres a
         * graph smaller than the canvas by shifting the world — so on exactly those graphs the
         * indicator sat off the region it claimed to mark and the recentre landed somewhere
         * else again. Everything here is `+ offset`, which is the same world the canvas above
         * is drawing and the same world `centreOn` scrolls to.
         */
        <button
          type="button"
          className="atlas-minimap"
          aria-label="Graph minimap; click to recentre"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            // A keyboard activation has no pointer behind it, and a click reported at the
            // origin used to jump the camera to the top-left corner. Enter on a control
            // labelled "recentre" means the middle of the map, which is what it now does.
            if (event.detail === 0) {
              view.centreOn(worldWidth / 2, worldHeight / 2);
              return;
            }
            /* Measured against the picture, not against the box holding it.

               The minimap is a fixed 3:2 button and the SVG inside it letterboxes to the
               world's own ratio under the default `xMidYMid meet` — for a layout floored at
               920x430 that is about fifteen dead pixels above and below the drawing, so a
               third of the vertical travel was mapped to the wrong world point on a control
               whose label promises to recentre. Reproducing `meet` here rather than setting
               `preserveAspectRatio="none"` keeps the locator the same shape as the map it is
               a locator for. The SVG rather than the button, because the button's rect
               includes the hairline border the drawing does not sit inside. */
            const drawing = minimapRef.current;
            if (!drawing) return;
            const bounds = drawing.getBoundingClientRect();
            const scale = Math.min(bounds.width / worldWidth, bounds.height / worldHeight);
            const left = bounds.left + (bounds.width - worldWidth * scale) / 2;
            const top = bounds.top + (bounds.height - worldHeight * scale) / 2;
            view.centreOn((event.clientX - left) / scale, (event.clientY - top) / scale);
          }}
        >
          <svg ref={minimapRef} viewBox={`0 0 ${worldWidth} ${worldHeight}`} aria-hidden="true">
            {graph.edges.map((edge) => {
              const source = positions.get(edge.sourceId);
              const target = positions.get(edge.targetId);
              if (!source || !target) return null;
              return (
                <line
                  key={edge.id}
                  x1={source.x + offsetX + NODE_WIDTH / 2}
                  y1={source.y + offsetY + NODE_HEIGHT / 2}
                  x2={target.x + offsetX + NODE_WIDTH / 2}
                  y2={target.y + offsetY + NODE_HEIGHT / 2}
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
                  x={position.x + offsetX}
                  y={position.y + offsetY}
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
              width={Math.min(worldWidth, view.viewport.width)}
              height={Math.min(worldHeight, view.viewport.height)}
            />
          </svg>
        </button>
      )}
    </div>
  );
}
