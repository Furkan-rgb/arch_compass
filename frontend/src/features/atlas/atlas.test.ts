import { afterEach, describe, expect, it } from "vitest";

import { LABEL_SIZE, META_SIZE, MIN_LABEL_SIZE, READABLE_ZOOM } from "./geometry";
import type { AtlasEdgeView, AtlasNodeView } from "./graph";
import { PULSE_STORAGE_KEY, readPulse, writePulse } from "./pulse";
import { NODE_HEIGHT, NODE_WIDTH, layoutAtlas } from "./layout";
import { drawnBounds, surfaceFor } from "./surface";
import { graphSignatureOf, visibleGraphFor } from "./visible-graph";

/**
 * A repository shaped the way a real one is: a root, three packages, modules inside them, and
 * dependency edges that cross package lines. Two elements carry a verdict.
 */
function graph(): { nodes: AtlasNodeView[]; edges: AtlasEdgeView[] } {
  const node = (
    id: string,
    kind: string,
    qualified: string,
    extra: Partial<AtlasNodeView> = {},
  ): AtlasNodeView => ({
    id,
    label: qualified.split(".").at(-1)!,
    qualified,
    path: `${qualified.replaceAll(".", "/")}.py`,
    kind,
    metrics: [],
    ...extra,
  });

  const nodes = [
    node("repo", "repository", "shop"),
    node("pkg-payments", "package", "shop.payments"),
    node("pkg-orders", "package", "shop.orders"),
    node("pkg-platform", "package", "shop.platform"),
    node("gateway", "class", "shop.payments.gateway.Gateway", {
      tone: "material",
      candidateId: "candidate-1",
    }),
    node("checkout", "class", "shop.payments.checkout.Checkout"),
    node("repository", "class", "shop.orders.repository.Repository", {
      tone: "held",
      candidateId: "candidate-2",
    }),
    node("basket", "class", "shop.orders.basket.Basket"),
    node("client", "class", "shop.platform.http.Client"),
    node("store", "class", "shop.platform.db.Store", { isPublic: false }),
    node("test_gateway", "test_module", "tests.test_gateway"),
  ];

  const contains = (from: string, to: string): AtlasEdgeView => ({
    id: `${from}>${to}`,
    sourceId: from,
    targetId: to,
    kind: "contains",
  });
  const imports = (from: string, to: string): AtlasEdgeView => ({
    id: `${from}->${to}`,
    sourceId: from,
    targetId: to,
    kind: "imports",
  });

  const edges = [
    contains("repo", "pkg-payments"),
    contains("repo", "pkg-orders"),
    contains("repo", "pkg-platform"),
    contains("pkg-payments", "gateway"),
    contains("pkg-payments", "checkout"),
    contains("pkg-orders", "repository"),
    contains("pkg-orders", "basket"),
    contains("pkg-platform", "client"),
    contains("pkg-platform", "store"),
    imports("checkout", "gateway"),
    imports("gateway", "client"),
    imports("repository", "store"),
    imports("basket", "repository"),
    imports("basket", "checkout"),
    { id: "t1", sourceId: "test_gateway", targetId: "gateway", kind: "tests" },
  ];

  return { nodes, edges };
}

const NO_FILTERS = {
  hiddenEdgeKinds: new Set<string>(),
  hideTests: false,
  publicOnly: false,
  selected: undefined,
};

describe("the atlas placement", () => {
  /**
   * The charter's promise is that the same commit gives the same map every time. Every
   * ordering in `layout.ts` breaks its ties on the element's own name for exactly this, and
   * nothing in a picture would show it had stopped doing so.
   */
  it("places the same graph identically every time, in every lens", () => {
    const { nodes, edges } = graph();
    for (const lens of ["structure", "dependencies", "judged"] as const) {
      const first = layoutAtlas(nodes, edges, lens);
      const second = layoutAtlas([...nodes].reverse(), edges, lens);
      expect([...first.positions.entries()].sort()).toEqual(
        [...second.positions.entries()].sort(),
      );
    }
  });

  it("places every element it was given, and nothing it was not", () => {
    const { nodes, edges } = graph();
    const layout = layoutAtlas(nodes, edges, "structure");
    expect([...layout.positions.keys()].sort()).toEqual(nodes.map((node) => node.id).sort());
  });

  /** Two cards on top of each other are one card the reader cannot read or click. */
  it("leaves no two cards overlapping", () => {
    const { nodes, edges } = graph();
    const layout = layoutAtlas(nodes, edges, "dependencies");
    for (const left of nodes) {
      for (const right of nodes) {
        if (left.id >= right.id) continue;
        const a = layout.positions.get(left.id)!;
        const b = layout.positions.get(right.id)!;
        const apart =
          Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT;
        expect(apart, `${left.id} overlaps ${right.id}`).toBe(true);
      }
    }
  });

  /** The canvas is sized from the placement, so a card outside it is a card nobody can reach. */
  it("sizes the canvas around everything it placed", () => {
    const { nodes, edges } = graph();
    const layout = layoutAtlas(nodes, edges, "structure");
    for (const node of nodes) {
      const position = layout.positions.get(node.id)!;
      expect(position.x).toBeGreaterThanOrEqual(0);
      expect(position.y).toBeGreaterThanOrEqual(0);
      expect(position.x + NODE_WIDTH).toBeLessThanOrEqual(layout.width);
      expect(position.y + NODE_HEIGHT).toBeLessThanOrEqual(layout.height);
    }
  });

  /**
   * An enclosure has to contain what it says it contains. Both layouts derive the region from
   * the cards' own bounds, so this is what catches one of them drifting from the other.
   */
  it("draws every enclosure around its own members", () => {
    const { nodes, edges } = graph();
    const layout = layoutAtlas(nodes, edges, "structure");
    expect(layout.clusters.length).toBeGreaterThan(0);
    for (const cluster of layout.clusters) {
      for (const nodeId of cluster.nodeIds) {
        const position = layout.positions.get(nodeId)!;
        expect(position.x).toBeGreaterThanOrEqual(cluster.x);
        expect(position.y).toBeGreaterThanOrEqual(cluster.y);
        expect(position.x + NODE_WIDTH).toBeLessThanOrEqual(cluster.x + cluster.width);
        expect(position.y + NODE_HEIGHT).toBeLessThanOrEqual(cluster.y + cluster.height);
      }
    }
  });

  /**
   * A label that every box on the map could wear is not a label. The structural lens has real
   * containers and names them; a graph community whose members share only the repository is
   * named for the element it grew around, which is a card the reader can actually find.
   */
  it("names an enclosure for what tells it apart from the others", () => {
    const { nodes, edges } = graph();
    const structural = layoutAtlas(nodes, edges, "structure");
    expect(structural.clusters.map((cluster) => cluster.label).sort()).toEqual([
      "orders",
      "payments",
      "platform",
    ]);

    const communities = layoutAtlas(nodes, edges, "dependencies");
    for (const cluster of communities.clusters) {
      // Never the repository's own name, which every card on the map shares.
      expect(cluster.label).not.toBe("shop");
      const named = cluster.label.startsWith("around ")
        ? cluster.label.slice("around ".length)
        : cluster.label;
      // Whatever it is named for, it is on the map — a box named after something nobody can
      // find is a box with a caption rather than a label.
      expect(nodes.some((node) => node.label === named || node.qualified.includes(named))).toBe(
        true,
      );
    }
  });

  it("has something to place, and says so, when handed nothing", () => {
    const layout = layoutAtlas([], []);
    expect(layout.positions.size).toBe(0);
    expect(layout.width).toBeGreaterThan(0);
  });
});

describe("the lenses", () => {
  it("draws containment and nothing else under structure", () => {
    const { nodes, edges } = graph();
    const visible = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "structure" });
    expect(visible.edges.every((edge) => edge.kind === "contains")).toBe(true);
  });

  it("draws everything except containment under dependencies", () => {
    const { nodes, edges } = graph();
    const visible = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "dependencies" });
    expect(visible.edges.some((edge) => edge.kind === "imports")).toBe(true);
    expect(visible.edges.every((edge) => edge.kind !== "contains")).toBe(true);
  });

  /**
   * The judged lens is the one that answers "where are the findings". It keeps every element a
   * verdict was written about even when nothing on the map reaches it — an isolated finding is
   * still the point of the lens, and dropping it would hide the very thing being looked for.
   */
  it("keeps every judged element under the judged lens, and what touches them", () => {
    const { nodes, edges } = graph();
    const visible = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "judged" });
    const drawn = new Set(visible.nodes.map((node) => node.id));
    expect(drawn.has("gateway")).toBe(true);
    expect(drawn.has("repository")).toBe(true);
    // The neighbours of a judged element are drawn; a package that touches neither is not.
    expect(drawn.has("client")).toBe(true);
    expect(drawn.has("pkg-platform")).toBe(false);
  });

  it("takes the tests out when asked, and puts them back", () => {
    const { nodes, edges } = graph();
    const shown = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "dependencies" });
    const hidden = visibleGraphFor({
      ...NO_FILTERS,
      nodes,
      edges,
      lens: "dependencies",
      hideTests: true,
    });
    expect(shown.nodes.some((node) => node.id === "test_gateway")).toBe(true);
    expect(hidden.nodes.some((node) => node.id === "test_gateway")).toBe(false);
  });

  /**
   * A filter that hid the card the reader just clicked would answer a question by removing it.
   */
  it("never filters away the card the reader has selected", () => {
    const { nodes, edges } = graph();
    const store = nodes.find((node) => node.id === "store")!;
    const visible = visibleGraphFor({
      ...NO_FILTERS,
      nodes,
      edges,
      lens: "dependencies",
      publicOnly: true,
      selected: store,
    });
    expect(visible.nodes.some((node) => node.id === "store")).toBe(true);
  });

  /**
   * `edgePath` cannot draw a curve from a card to itself, so the canvas never drew one — and
   * the footer counted it anyway, telling the reader about a line that is nowhere on the map.
   */
  it("does not count a relationship it cannot draw", () => {
    const { nodes, edges } = graph();
    const visible = visibleGraphFor({
      ...NO_FILTERS,
      nodes,
      edges: [...edges, { id: "self", sourceId: "gateway", targetId: "gateway", kind: "imports" }],
      lens: "dependencies",
    });
    expect(visible.edges.some((edge) => edge.id === "self")).toBe(false);
  });

  it("hides a relationship kind the reader switched off", () => {
    const { nodes, edges } = graph();
    const visible = visibleGraphFor({
      ...NO_FILTERS,
      nodes,
      edges,
      lens: "dependencies",
      hiddenEdgeKinds: new Set(["tests"]),
    });
    expect(visible.edges.every((edge) => edge.kind !== "tests")).toBe(true);
  });

  /**
   * The signature is what the placement and the camera are keyed on. Selecting a card that was
   * already on screen changes nothing about which cards are on screen, and if the signature
   * moved anyway the map would re-lay out and the camera would jump on every click.
   */
  it("does not change what the map is of when a card is merely selected", () => {
    const { nodes, edges } = graph();
    const before = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "dependencies" });
    const after = visibleGraphFor({
      ...NO_FILTERS,
      nodes,
      edges,
      lens: "dependencies",
      selected: nodes.find((node) => node.id === "gateway"),
    });
    expect(graphSignatureOf("dependencies", after)).toBe(
      graphSignatureOf("dependencies", before),
    );
  });

  /** A re-judged element is a different map, because the placement clusters around verdicts. */
  it("changes what the map is of when a verdict moves", () => {
    const { nodes, edges } = graph();
    const before = visibleGraphFor({ ...NO_FILTERS, nodes, edges, lens: "dependencies" });
    const rejudged = nodes.map((node) =>
      node.id === "gateway" ? { ...node, tone: "cleared" as const } : node,
    );
    const after = visibleGraphFor({
      ...NO_FILTERS,
      nodes: rejudged,
      edges,
      lens: "dependencies",
    });
    expect(graphSignatureOf("dependencies", after)).not.toBe(
      graphSignatureOf("dependencies", before),
    );
  });
});

describe("the drawn surface", () => {
  const layoutOf = () => {
    const { nodes, edges } = graph();
    return layoutAtlas(nodes, edges, "structure");
  };

  it("fills a canvas the graph is smaller than, and centres the graph in it", () => {
    const layout = layoutOf();
    const canvas = { width: layout.width * 2, height: layout.height * 2 };
    const surface = surfaceFor(layout, canvas, 1);

    expect(surface.width).toBe(canvas.width);
    expect(surface.height).toBe(canvas.height);
    // The room left over is the same on both sides of what is actually drawn.
    const drawn = drawnBounds(layout);
    const left = surface.offsetX + drawn.x;
    const right = surface.width - (surface.offsetX + drawn.x + drawn.width);
    expect(Math.abs(left - right)).toBeLessThan(1);
  });

  it("leaves a graph larger than the canvas exactly where the placement put it", () => {
    const layout = layoutOf();
    const surface = surfaceFor(layout, { width: 200, height: 200 }, 1);

    // Nothing may move on an axis that scrolls: the camera maps world to scroll by the zoom
    // alone, so an offset there would put every pan, fit and minimap jump off by that much.
    expect(surface.width).toBe(layout.width);
    expect(surface.height).toBe(layout.height);
    expect(surface.offsetX).toBe(0);
    expect(surface.offsetY).toBe(0);
  });

  it("measures what is drawn rather than the box the placement claimed", () => {
    const layout = layoutOf();
    const drawn = drawnBounds(layout);

    expect(drawn.width).toBeLessThanOrEqual(layout.width);
    expect(drawn.height).toBeLessThanOrEqual(layout.height);
    for (const position of layout.positions.values()) {
      expect(position.x).toBeGreaterThanOrEqual(drawn.x);
      expect(position.y).toBeGreaterThanOrEqual(drawn.y);
      expect(position.x + NODE_WIDTH).toBeLessThanOrEqual(drawn.x + drawn.width);
      expect(position.y + NODE_HEIGHT).toBeLessThanOrEqual(drawn.y + drawn.height);
    }
  });

  it("never shifts the layout box off the surface", () => {
    const layout = layoutOf();
    for (const zoom of [0.45, 1, 1.8]) {
      const surface = surfaceFor(layout, { width: 3000, height: 400 }, zoom);
      expect(surface.offsetX).toBeGreaterThanOrEqual(0);
      expect(surface.offsetX + layout.width).toBeLessThanOrEqual(surface.width + 0.001);
      expect(surface.offsetY).toBeGreaterThanOrEqual(0);
      expect(surface.offsetY + layout.height).toBeLessThanOrEqual(surface.height + 0.001);
    }
  });
});

/**
 * The floor on the automatic fit, which is the zoom a review's map opens at.
 *
 * `READABLE_ZOOM` was `0.45` under a comment naming seven pixels as the point a label stops
 * being one — and 13 × 0.45 is 5.85. A number that has drifted from the reason for it is the
 * kind of thing only arithmetic notices, so the arithmetic is here.
 *
 * It then drifted a second way, which is what the third assertion now catches. Dividing by
 * `LABEL_SIZE` held the *label* over eight pixels and said nothing about the meta row beneath
 * it — the row carrying the namespace and the word half of the verdict — so at 0.615 the one
 * thing on a card that says "Held" in words rendered at 6.2px while the border said it in a
 * hue. A colour never carries meaning alone, so the floor is measured against the smallest row
 * the card draws rather than the largest.
 */
describe("the readable floor", () => {
  it("never fits to a zoom the card's own label cannot survive", () => {
    expect(LABEL_SIZE * READABLE_ZOOM).toBeGreaterThanOrEqual(MIN_LABEL_SIZE);
  });

  it("never fits to a zoom the verdict word cannot survive either", () => {
    expect(META_SIZE * READABLE_ZOOM).toBeGreaterThanOrEqual(MIN_LABEL_SIZE);
  });

  it("is derived from the smallest row rather than asserted beside it", () => {
    // The two values it used to hold, kept as the things this test exists to refuse.
    expect(LABEL_SIZE * 0.45).toBeLessThan(MIN_LABEL_SIZE);
    expect(META_SIZE * (MIN_LABEL_SIZE / LABEL_SIZE)).toBeLessThan(MIN_LABEL_SIZE);
    expect(READABLE_ZOOM).toBeCloseTo(MIN_LABEL_SIZE / META_SIZE, 10);
  });
});

/**
 * The one loop that used to run inside the workbench.
 *
 * `pulse` defaulted to `comet`, so selecting a card started an infinite animation on every
 * edge touching it and left it running until the reader found a menu. A map being read
 * closely should be allowed to hold still, and a reader who wants the movement says so once.
 */
describe("the highlight preference", () => {
  afterEach(() => globalThis.localStorage.removeItem(PULSE_STORAGE_KEY));

  it("is stillness until somebody says otherwise, and is remembered when they do", () => {
    expect(readPulse()).toBe("none");
    writePulse("travel");
    expect(readPulse()).toBe("travel");
  });

  it("takes nothing from storage that is not one of the five", () => {
    globalThis.localStorage.setItem(PULSE_STORAGE_KEY, "sparkle");
    expect(readPulse()).toBe("none");
  });
});
