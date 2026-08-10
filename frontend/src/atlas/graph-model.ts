/** What the map is given to draw: nodes, relationships, and everything a caller may ask of it. */

import type {
  AtlasExploreOperation,
  AtlasMetricNature,
  AtlasMetricScope,
  AtlasSignal,
} from "../types";

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
  /**
   * Whether a review judged this node, and so whether `onOpenFinding` has somewhere to go.
   *
   * On the node rather than in a set beside the graph: the caller that knows a node was judged
   * is the one that built the node, and a second collection to keep in step with the first is
   * a way for the map to offer a link to a finding that is not there.
   */
  hasFinding?: boolean;
}

export interface AtlasEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  kind: string;
  confidence?: number;
  risk?: boolean;
}

export type AtlasLens = "structure" | "dependencies" | "risk";

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
  /**
   * The lens the map opens on. `structure` for a repository, because containment is how a
   * codebase is read; a caller whose graph is nearly all dependency edges says so, rather
   * than opening on a lens that draws almost none of it.
   */
  initialLens?: AtlasLens;
  /**
   * What this caller calls each node state, where its own vocabulary is the one the reader
   * has already been given. Only the legend is renamed: the states themselves are the map's,
   * and a caller that could redefine them would be drawing a different map.
   */
  legendLabels?: Partial<Record<AtlasNodeState, string>>;
  /** Where the selected node's finding is written, for a node that carries one. */
  onOpenFinding?: (nodeId: string) => void;
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
