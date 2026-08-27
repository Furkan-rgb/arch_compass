import { AtlasMap as Map, type MapEdge, type MapModule, type MapNode } from "../atlas/map";

/**
 * The atlas, as the hero draws it.
 *
 * The landing page's problem is that the deterministic half of this product is the half
 * nobody believes: "we parse your repository, we never run it" is a sentence, and a sentence
 * is what every tool says. The atlas is the artefact that sentence describes — nodes, edges,
 * modules, built before a model is asked anything — so the hero shows it instead.
 *
 * What is drawn here is a specimen, like the findings beside it, and it is composed by hand
 * rather than computed: the emptiness has to fall where the callout lands, which is a
 * decision no layout algorithm can be told to make. A review's Atlas surface draws the same
 * picture from real coordinates — see `features/review/atlas-layout.ts` — and both go through
 * `features/atlas/map.tsx`, so the two can never drift into two different-looking maps.
 *
 * Exactly three nodes carry a verdict because exactly three findings are on show. Every other
 * node is ink: a map where everything is lit is a map that has said nothing.
 */

/**
 * The drawing space. Nothing else in this file is in pixels: the figure is given an aspect
 * ratio that matches, so a percentage of the box and a fraction of the viewBox are the same
 * place, which is what lets the callout outside the SVG pin to a node inside it.
 */
export const ATLAS_VIEWBOX = { width: 900, height: 700 } as const;

/**
 * Where the callout's top-left corner sits, and therefore where every leader ends.
 *
 * The callout stays put and the line re-aims when the specimen changes. The other way round
 * — a callout that jumps to whichever node is active — moves the one block of text on the
 * figure that somebody is trying to read.
 */
export const ANCHOR = { x: 320, y: 330 } as const;

/**
 * How the leader reaches the callout from each node that can be active, authored rather than
 * computed.
 *
 * A generated elbow has to pick a direction it cannot know is free, and the three nodes that
 * need one sit in three different relations to the callout: two above it and one beside it.
 * Three short paths drawn on purpose beat one rule that is wrong a third of the time.
 */
const LEADERS: Record<string, string> = {
  gateway: "M330 195V330",
  invoice: "M665 145V330",
  orders: "M110 340H320",
};

/**
 * The graph occupies an arc across the top and down the left, and the lower right is left
 * clear. That emptiness is not a gap in the map — it is where the callout lands, and a map
 * drawn without room for it would have had the finding covering half its own evidence.
 */
const NODES: MapNode[] = [
  { id: "webhooks", x: 325, y: 100, label: "webhooks" },
  { id: "checkout", x: 465, y: 85, label: "checkout" },
  { id: "gateway", x: 330, y: 180, label: "gateway", tone: "material" },
  { id: "refunds", x: 480, y: 175, label: "refunds" },
  { id: "invoice", x: 665, y: 130, label: "invoice", tone: "cleared" },
  { id: "ledger", x: 795, y: 115, label: "ledger" },
  { id: "tax", x: 635, y: 245, label: "tax" },
  { id: "dunning", x: 795, y: 235, label: "dunning" },
  { id: "basket", x: 110, y: 255, label: "basket" },
  { id: "orders", x: 95, y: 340, label: "orders", tone: "held" },
  { id: "fulfil", x: 180, y: 390, label: "fulfil" },
  { id: "config", x: 105, y: 550, label: "config" },
  { id: "db", x: 215, y: 545, label: "db" },
  { id: "queue", x: 130, y: 620, label: "queue" },
  { id: "http", x: 290, y: 590, label: "http" },
];

/**
 * The four enclosures, and the one rule they all have to keep: none of them may reach
 * `ANCHOR.x`.
 *
 * A module box is the single mark that says the repository was parsed into modules, so a box
 * with a side missing is the claim failing quietly. `platform` was 300 wide from x=40, which
 * put its right edge at 340 — twenty units under the callout, which is opaque — and the box
 * simply had no right side at any width where the callout is pinned. At 275 it closes at 315,
 * five clear of the anchor, and `http` at x=290 still sits inside it with room for its label.
 */
const MODULES: MapModule[] = [
  { x: 250, y: 30, width: 300, height: 215, label: "payments" },
  { x: 585, y: 55, width: 285, height: 245, label: "billing" },
  { x: 30, y: 195, width: 215, height: 240, label: "orders" },
  { x: 40, y: 480, width: 275, height: 175, label: "platform" },
];

const EDGES: MapEdge[] = [
  { from: "webhooks", to: "gateway" },
  { from: "checkout", to: "gateway" },
  { from: "refunds", to: "gateway" },
  { from: "checkout", to: "refunds" },
  { from: "basket", to: "orders" },
  { from: "orders", to: "fulfil" },
  { from: "basket", to: "checkout" },
  { from: "orders", to: "gateway" },
  { from: "orders", to: "invoice" },
  { from: "invoice", to: "ledger" },
  { from: "invoice", to: "tax" },
  { from: "ledger", to: "dunning" },
  { from: "tax", to: "ledger" },
  { from: "gateway", to: "http" },
  { from: "gateway", to: "queue" },
  { from: "refunds", to: "queue" },
  { from: "orders", to: "db" },
  { from: "fulfil", to: "db" },
  { from: "invoice", to: "db" },
  { from: "ledger", to: "db" },
  { from: "config", to: "orders" },
  { from: "config", to: "db" },
  { from: "dunning", to: "queue" },
  { from: "fulfil", to: "queue" },
  { from: "invoice", to: "http" },
];

export function AtlasMap({ active, className }: { active: string; className?: string }) {
  const leader = LEADERS[active];

  return (
    <Map
      viewBox={ATLAS_VIEWBOX}
      modules={MODULES}
      nodes={NODES}
      edges={EDGES}
      active={active}
      // A leader drops out of a lit node, so those three wear their labels above rather than
      // being struck through by their own line.
      verdictLabels="above"
      labels="active"
      className={className}
      overlay={
        leader ? (
          // Dashed, because a solid hairline here is the same mark the edges are drawn with,
          // and the leader was disappearing into the very edges it runs beside. A dash reads
          // as annotation rather than as something the atlas contains.
          //
          // Only where the callout is actually pinned to the map; below `lg` it sits
          // underneath instead and a line to nowhere would be worse than none.
          //
          // `lg`, and it has to be the same `lg` the three switches in `landing-page.tsx`
          // take — the callout going absolute, the map filling the box, and the callout's
          // width. This said `xl` after those three moved down, so between 1024 and 1279 a
          // card floated over the graph with nothing joining it to the node it is about,
          // which is the one thing the hero exists to show.
          <path
            className="hidden lg:inline"
            d={leader}
            stroke="var(--ink-3)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        ) : null
      }
    />
  );
}
