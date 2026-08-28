import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import type { Tone } from "../../lib/format";

/**
 * The atlas, drawn.
 *
 * Two places show a map of a repository and they get their coordinates from opposite
 * directions: the landing page's is a specimen composed by hand, so its emptiness can be put
 * where the callout lands, and a review's is computed from what that review actually
 * examined. What they must not do is *look* like two maps. The stroke weights, the module
 * enclosure, the bowed edge and the rule about which node is allowed a hue are the picture,
 * and they live here once.
 *
 * Everything below is placement-agnostic. This file never decides where a node goes; it
 * decides what a node looks like once something else has decided.
 *
 * There is no chroma here that is not a verdict. The modules and the edges are hairlines,
 * which is the same device the rest of the system separates with.
 */

export type MapModule = {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
};

export type MapNode = {
  id: string;
  x: number;
  y: number;
  label: string;
  /** Set only on the elements a finding was made about. */
  tone?: Tone;
};

export type MapEdge = { from: string; to: string };

/**
 * The verdict hues, reached for on the nodes that carry one.
 *
 * Indexed by the tone rather than written at the node, which is the same rule the badges
 * follow: nothing here decides that a shape should be red, it paints the tone a finding
 * already has.
 *
 * **The graphic tier, because a stroke is a graphic.** Every value here is painted onto an SVG
 * `stroke`, and the design system splits each signal in two on exactly that line: the bare token
 * is the text tier and clears 4.5:1, the `-edge` token is for edges, glyphs, bars and dots and
 * clears 3:1. This map held the text tier for a revision — `var(--material)` on a circle — which
 * is the same defect `ui/meta.tsx`'s left edges were moved off, spending a word's contrast on a
 * line nobody reads and leaving the drawn thing quieter than the system has to offer.
 *
 * `neutral` and `marked` keep their tokens because neither is a verdict and neither has a signal
 * to spend: `--rule-strong` is the boundary the whole map separates with, and `--ink` is the ink.
 * There is no `--rule-strong-edge` and there should not be.
 *
 * These are `var()` strings rather than utility classes because they reach an SVG attribute, and
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

/** One gentle bow per edge, so the map reads as drawn rather than as ruled. */
export function edgePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  const bow = 0.09 * length;
  const cx = (from.x + to.x) / 2 - (dy / length) * bow;
  const cy = (from.y + to.y) / 2 + (dx / length) * bow;
  return `M${from.x} ${from.y}Q${Math.round(cx)} ${Math.round(cy)} ${to.x} ${to.y}`;
}

export type AtlasMapProps = {
  viewBox: { width: number; height: number };
  modules: readonly MapModule[];
  nodes: readonly MapNode[];
  edges: readonly MapEdge[];
  /** The node the surface is currently about. Its edges come forward and its label is ink. */
  active?: string;
  /**
   * Where the label of a node that carries no verdict sits.
   *
   * `above` is for the landing specimen, whose lit nodes have a leader dropping out of them
   * and would otherwise strike through their own word.
   */
  verdictLabels?: "above" | "below";
  /**
   * Below `sm` a map drawn at half scale is a map of illegible labels, so `active` keeps only
   * the lit one and hides the rest until there is room. `all` never hides.
   */
  labels?: "all" | "active";
  onSelect?: (id: string) => void;
  /** Drawn in the map's own coordinates, over the edges and under the nodes. */
  overlay?: ReactNode;
  className?: string;
  title?: string;
};

export function AtlasMap({
  viewBox,
  modules,
  nodes,
  edges,
  active,
  verdictLabels = "below",
  labels = "all",
  onSelect,
  overlay,
  className,
  title,
}: AtlasMapProps) {
  const byId = new Map(nodes.map((node) => [node.id, node]));

  return (
    <svg
      viewBox={`0 0 ${viewBox.width} ${viewBox.height}`}
      fill="none"
      // Decorative unless something can be done with it. Where the map is a specimen the
      // callout beside it names the candidate in text, so announcing the labels would say it
      // twice; where a node opens a finding it is a control and has to be reachable.
      aria-hidden={onSelect ? undefined : "true"}
      role={onSelect ? "group" : undefined}
      aria-label={onSelect ? title : undefined}
      className={cn("size-full", className)}
    >
      {modules.map((module) => (
        <g key={module.label}>
          <rect
            x={module.x}
            y={module.y}
            width={module.width}
            height={module.height}
            rx={14}
            stroke="var(--rule)"
          />
          <text
            x={module.x + 14}
            y={module.y + 22}
            // Font size is in user units, so it shrinks with the map. The larger step is what
            // keeps a module legible once the figure is being drawn at about half scale.
            //
            // 15 rather than 12, and `--ink-2` rather than `--ink-3`. The hero draws the map at
            // roughly 0.65–0.9 of the viewBox, so twelve user units landed at a six-pixel cap
            // height — the smallest type on the page, in the tier below body ink, carrying the
            // hero's entire claim that the repository was parsed into a structure.
            //
            // `0.08em`, which is the scale's tracking for an uppercase label and which
            // `.atlas-clusters text` in `styles.css` — this figure's own sibling, drawn on the
            // same map — already moved to. It was `0.14em`, chosen beside the old `0.13em`
            // label recipe and for the same mistaken reason: letterspacing buys apparent width
            // rather than legibility, and past about `0.1em` it costs word shape. Two label
            // treatments a few hundred user units apart tracked differently is a difference a
            // reader reads as a fault. The sizes stay where they are, because they are user
            // units on a scaled figure and the paragraph above is what decides them.
            className="fill-[var(--ink-2)] font-mono text-[18px] font-semibold uppercase tracking-[0.08em] sm:text-[15px]"
          >
            {module.label}
          </text>
        </g>
      ))}

      {edges.map((edge) => {
        const from = byId.get(edge.from);
        const to = byId.get(edge.to);
        if (!from || !to) return null;
        // The edges into and out of the active element are the ones the surface is about, so
        // they come forward. Everything else is the hairline the rest of the system separates
        // with.
        const bears = edge.from === active || edge.to === active;
        return (
          <path
            key={`${edge.from}-${edge.to}`}
            d={edgePath(from, to)}
            stroke={bears ? "var(--ink-3)" : "var(--rule-strong)"}
            strokeWidth={bears ? 1.25 : 1}
          />
        );
      })}

      {overlay}

      {nodes.map((node) => {
        const stroke = node.tone ? TONE_STROKE[node.tone] : "var(--rule-strong)";
        const isActive = node.id === active;
        const label = (
          <text
            x={node.x}
            y={node.y + (node.tone && verdictLabels === "above" ? -22 : node.tone ? 32 : 24)}
            textAnchor="middle"
            // 15 user units, not 13: at the scale the figure is actually drawn, thirteen
            // rendered at eight or nine CSS pixels, under the floor the rest of the system
            // holds itself to. The specimen's coordinates leave room for the extra two.
            className={cn(
              "font-mono",
              isActive
                ? "fill-[var(--ink)] text-[20px] font-semibold sm:text-[15px]"
                : cn(
                    "fill-[var(--ink-3)] text-[15px]",
                    labels === "active" && "hidden sm:inline",
                  ),
            )}
          >
            {node.label}
          </text>
        );

        const drawing = (
          <>
            {node.tone ? (
              <circle
                cx={node.x}
                cy={node.y}
                r={15}
                stroke={stroke}
                strokeOpacity={isActive ? 0.75 : 0.3}
              />
            ) : null}
            <circle
              cx={node.x}
              cy={node.y}
              r={node.tone ? 8 : 5.5}
              fill="var(--surface)"
              stroke={stroke}
              strokeWidth={node.tone ? 1.75 : 1.25}
            />
            {label}
          </>
        );

        // Only an element a finding was made about is a control. Everything else on the map
        // is the context that made the shape a shape, and there is nothing to open on it —
        // announcing fifteen unactionable buttons to a screen reader would be worse than
        // announcing none.
        if (!onSelect || !node.tone) return <g key={node.id}>{drawing}</g>;
        return (
          <g
            key={node.id}
            role="button"
            tabIndex={0}
            aria-label={node.label}
            onClick={() => onSelect(node.id)}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              onSelect(node.id);
            }}
            className="cursor-pointer outline-offset-2"
          >
            {/* A 5.5px circle is not a target. This is the box a finger and a cursor
                actually hit, and it is invisible rather than absent because a `pointer-events`
                hole over a 44px area would swallow the node beside it. */}
            <circle cx={node.x} cy={node.y} r={22} fill="transparent" />
            {drawing}
          </g>
        );
      })}
    </svg>
  );
}
