import type { AtlasEdge, ObscuritySignal } from "../../api";
import type { components } from "../../openapi.generated";
import type { Tone } from "../../lib/format";

/**
 * What the map is given to draw, and everything a caller may ask of it.
 *
 * The shapes here are the map's own, not the wire's. `features/review/atlas-surface.tsx`
 * turns a review and its atlas queries into these; nothing below this line knows what a
 * review is, which is what lets the same explorer be pointed at something else later.
 *
 * The one thing that carries meaning rather than data is `tone`. A node has one when a
 * finding was made about it, and it is the finding's tone — never chosen here. Everything
 * else on the map is the structure that made the shape a shape.
 */

export type AtlasNodeView = {
  /** The atlas node id. Every query on this map is keyed by it. */
  id: string;
  /** The last segment of the qualified name, which is what fits on a card. */
  label: string;
  qualified: string;
  /**
   * Where it is, and the line span where the atlas recorded one — as three fields, not one
   * string.
   *
   * `ui/meta.tsx`'s `PathRef` composes them itself, so that the button copies the `path:line`
   * an editor's go-to-file box accepts while the screen shows the readable range and the
   * editor link is built from a bare path. This carried `file.py:10-40` in `path` and defeated
   * all three at once.
   */
  path: string;
  line?: number | null;
  endLine?: number | null;
  kind: string;
  isPublic?: boolean | null;
  /**
   * The verdict written about this element, where one was.
   *
   * Absent is not "cleared". A review judges what its detectors surfaced and the map draws
   * the neighbourhood around it, so most of what is on screen was never looked at — and a
   * map that drew "examined and found sound" the same way as "never examined" would erase
   * the whole value of the sweep.
   */
  tone?: Tone;
  /**
   * The verdict in one word — `Material`, `Held`, `Cleared` — wherever `tone` is set.
   *
   * The charter: a colour never carries meaning alone, and every verdict has a glyph, a word
   * and a hue. The card had the glyph and the hue, and its accessible name said "judged" for
   * a material finding and for a cleared one — the two verdicts this whole surface exists to
   * tell apart. The word travels with the tone so the card can never carry one without the
   * other.
   */
  verdictLabel?: string;
  /** Which finding to open, on the element a finding was made about. */
  candidateId?: string;
  /** The verdict in words, and why — shown in the panel beside the map. */
  description?: string;
  metrics: AtlasMetricView[];
  signals?: ObscuritySignal[];
  signalCount?: number;
};

export type AtlasMetricView = {
  label: string;
  value: number | string;
  nature?: string;
  scope?: string;
  definition?: string;
  limitations?: string;
};

export type AtlasEdgeView = {
  id: string;
  sourceId: string;
  targetId: string;
  kind: AtlasEdge["edge_type"] | string;
  confidence?: number;
};

/**
 * Which relationships are the subject of the map.
 *
 * `judged` replaces what this used to call `risk`. The map has no opinion about risk — the
 * model wrote the verdicts and the parser drew the edges — so the third lens says what it
 * actually does: keep the elements a finding was made about, and whatever reaches them.
 */
export type AtlasLens = "structure" | "dependencies" | "judged";

export const LENSES: { value: AtlasLens; label: string; hint: string }[] = [
  { value: "structure", label: "Structure", hint: "What contains what" },
  { value: "dependencies", label: "Dependencies", hint: "What reaches what" },
  { value: "judged", label: "Judged", hint: "What a finding was made about" },
];

/**
 * Everything a reader can ask the atlas for.
 *
 * Taken from the generated client rather than written out, so a rename on the backend is a
 * build error here instead of a 422 at run time. The frontend kept a union of eight of the
 * backend's twelve, in a *third* spelling of those names — the route carried a dictionary
 * translating one to the other — and nothing connected the two lists.
 */
export type AtlasOperation = components["schemas"]["AtlasExploreRequest"]["operation"];

/** The subset that starts from an element: the buttons on a node's detail panel. */
export type ExploreOperation = Exclude<
  AtlasOperation,
  "search_nodes" | "shortest_dependency_path" | "cyclic_components" | "signals"
>;

/**
 * Something the reader added to the map, and the way to take it back off again.
 *
 * The map only ever grew: every exploration appended to a list nothing removed, so three
 * presses of "Two hops out" turned a ninety-card neighbourhood into a three-hundred-card mesh
 * for the rest of the session, with no way back but a reload. The requests were already
 * stored and already named; all that was missing was saying so and offering the reverse.
 */
export type AtlasExploration = {
  id: string;
  /** What was asked, in words: "Dependants of `Gateway`". */
  label: string;
  onDrop: () => void;
};

export type AtlasExplorerProps = {
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  loading?: boolean;
  /**
   * What to say when the caller handed the map nothing at all.
   *
   * Only that case. A map emptied by the reader's own lens or filter says which one did it,
   * and printing the caller's sentence there told a reader who had just pressed "Public only"
   * that the review's elements were gone from the atlas — a false statement of cause, which
   * is the exact failure the experience doc asks this surface to prevent.
   */
  emptyMessage?: string;
  /**
   * The lens the map opens on.
   *
   * A review's neighbourhood is nearly all dependency edges — imports, calls, one class
   * implementing one interface — and the structural lens draws containment only, so opening
   * a review's map on structure showed a scatter of unconnected cards.
   */
  initialLens?: AtlasLens;
  /** Where the finding about a node is written, for the nodes a verdict was written about. */
  onOpenFinding?: (candidateId: string) => void;
  onExploreNode?: (nodeId: string, operation: ExploreOperation, depth?: number) => void;
  onExploreAtlas?: (operation: "cyclic_components" | "signals") => void;
  onSearch?: (term: string) => void;
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  /** Nodes and relationships on a traced path, which paint above the rest of the mesh. */
  highlightedNodeIds?: string[];
  highlightedEdgeIds?: string[];
  /** A strip the caller owns, drawn above the controls. The review puts its legend there. */
  header?: React.ReactNode;
  /**
   * What the last exploration and the last trace came back with, in one sentence each.
   *
   * The caller owns these because the caller is what asked. Without them a request the atlas
   * answers with nothing — an element with no dependants, two elements with no path between
   * them — presses a button and changes the map not at all, which reads as broken rather than
   * as an answer. A bounded view has to be able to say "none", and only what made the request
   * knows what "none" was in response to.
   *
   * They are drawn in the strip above the canvas, not in the detail panel. In the panel they
   * sat inside a section that exists only while a card is selected, so a search that matched
   * nothing on the map answered into a block that was not rendered — and nothing selected is
   * the state the surface opens in.
   */
  exploreNote?: string;
  traceNote?: string;
  /** Elements the reader explicitly asked for, which no lens or filter may hide. */
  revealedNodeIds?: string[];
  /** What the reader has added to this map, each with a way to drop it, and all of them. */
  explorations?: AtlasExploration[];
  onResetExplorations?: () => void;
};
