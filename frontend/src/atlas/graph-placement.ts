/** Where the cards go: the placement drawn immediately, and the better one that replaces it. */

import { useEffect, useMemo, useState } from "react";

import { type AtlasLayout, layoutAtlas, layoutAtlasElk } from "../atlas-layout";
import type { AtlasLens } from "./graph-model";
import type { VisibleGraph } from "./visible-graph";

/**
 * Once, however many maps are on the page and however often the lens changes: a kernel that
 * cannot load fails the same way every time, and a console repeating it says nothing new.
 */
let reportedLayoutFailure = false;

function reportLayoutFailure(error: unknown) {
  if (reportedLayoutFailure) return;
  reportedLayoutFailure = true;
  console.warn("Atlas graph layout unavailable; keeping the built-in placement.", error);
}

/**
 * Where the cards go, in two stages.
 *
 * The hand-rolled placement runs synchronously so the map is on screen in the same frame
 * the graph is: a canvas that appears empty while a layout engine loads reads as a canvas
 * with nothing on it. The layout kernel then places the same graph properly — it untangles
 * dense graphs the relaxation pass leaves overlapping — and the map swaps to its answer
 * when it arrives. If it never arrives, the first placement is a real map, not a spinner.
 *
 * Both stages are keyed on the signature rather than on the graph itself. The synchronous
 * pass is O(n²) in the relaxation and the collision sweeps, so a selection that cannot change
 * where anything goes should not pay for it — and, more to the point, should not hand the
 * viewport a new layout object to react to.
 */
export function usePlacedLayout(
  graph: VisibleGraph,
  lens: AtlasLens,
  graphSignature: string,
): AtlasLayout {
  const initialLayout = useMemo(
    () => layoutAtlas(graph.nodes, graph.edges, lens),
    // The signature is what the placement is about; the graph is a new object per click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphSignature],
  );
  const [placedLayout, setPlacedLayout] = useState<AtlasLayout | null>(null);
  useEffect(() => {
    let current = true;
    // The graph on screen is no longer the one the pending placement is about.
    setPlacedLayout(null);
    layoutAtlasElk(graph.nodes, graph.edges, lens)
      .then((next) => {
        if (current) setPlacedLayout(next);
      })
      .catch(reportLayoutFailure);
    return () => {
      current = false;
    };
    // Same reasoning as the synchronous pass above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphSignature]);
  return placedLayout ?? initialLayout;
}
