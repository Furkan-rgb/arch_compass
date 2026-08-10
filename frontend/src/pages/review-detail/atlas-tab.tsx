/** The Atlas tab: the review's boundaries drawn on the map of the repository they are in. */

import { ReviewAtlas } from "../../review-atlas";
import type { ReviewedBoundary } from "../../types";

/**
 * Which finding a node on the map belongs to, by the reference the ledger files it under.
 *
 * Both participants, because both are on the map: the boundary carries the verdict and the
 * implementation behind it is drawn beside it, and a reader who selected either of them is
 * asking about the same finding. `null` for every other node the atlas returned — most of the
 * map is the neighbourhood, which no finding is about.
 */
export function findingForNode(
  nodeId: string,
  reviewed: ReviewedBoundary[],
): string | null {
  const found = reviewed.find((item) =>
    item.candidate.participants.some((participant) => participant.node_id === nodeId),
  );
  return found?.reference ?? null;
}

export function AtlasTab({
  repositoryRoot,
  reviewed,
  selectedNodeId,
  onSelectNode,
  onOpenFinding,
}: {
  repositoryRoot: string;
  reviewed: ReviewedBoundary[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  /** The journey back: a node on the map to the finding written about it. */
  onOpenFinding: (nodeId: string) => void;
}) {
  return (
    <ReviewAtlas
      repositoryRoot={repositoryRoot}
      boundaries={reviewed}
      selectedNodeId={selectedNodeId}
      onSelectNode={onSelectNode}
      onOpenFinding={onOpenFinding}
    />
  );
}
