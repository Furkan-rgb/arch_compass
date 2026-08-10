/** The map of a repository, as the rest of the workspace sees it. */

export { RepositoryAtlas } from "./RepositoryAtlas";
export type {
  AtlasEdgeView,
  AtlasLens,
  AtlasMetricView,
  AtlasNodeState,
  AtlasNodeView,
  RepositoryAtlasProps,
} from "./graph-model";
export type { AtlasPulse } from "./pulse";

/* Where the map is placed lives beside this folder; it is still read from here. */
export { layoutAtlas } from "../atlas-layout";
export type { AtlasClusterRegion, AtlasLayout } from "../atlas-layout";
