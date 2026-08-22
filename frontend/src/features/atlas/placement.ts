import { useEffect, useMemo, useState } from "react";

import type { AtlasLens } from "./graph";
import { type AtlasLayout, layoutAtlas, layoutAtlasElk } from "./layout";
import type { VisibleGraph } from "./visible-graph";

/** Where the cards go: the placement drawn immediately, and the better one that replaces it. */

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
 * The hand-rolled placement runs synchronously so the map is on screen in the same frame the
 * graph is: a canvas that appears empty while a layout engine loads reads as a canvas with
 * nothing on it. The layout kernel then places the same graph properly — it untangles dense
 * graphs the relaxation pass leaves overlapping — and the map swaps to its answer when it
 * arrives. If it never arrives, the first placement is a real map, not a spinner.
 *
 * **The first stage is for the first paint, and for nothing else.** It used to run on every
 * change: toggling one relationship chip dropped the kernel's placement, snapped the map to
 * the hand-rolled geometry — radial rings where there had been layered clusters — and then
 * snapped again a few hundred milliseconds later when the kernel answered. Two arrangements
 * and two camera moves for one press, on each of the four filters, both lens changes and
 * every exploration. So a kernel placement, once there is one, stays on screen until its
 * replacement resolves. The map the reader is looking at is always a map, and it changes
 * once.
 *
 * Both stages are keyed on the signature rather than on the graph itself. The synchronous pass
 * is O(n²) in the relaxation and the collision sweeps, so a selection that cannot change where
 * anything goes should not pay for it — and, more to the point, should not hand the viewport a
 * new layout object to react to.
 */
export function usePlacedLayout(
  graph: VisibleGraph,
  lens: AtlasLens,
  graphSignature: string,
): AtlasLayout {
  /**
   * The kernel's answer, and which graph it is an answer to.
   *
   * Held together in one piece of state because they are one fact. They are allowed to
   * disagree with `graphSignature`, and that disagreement is exactly the window in which the
   * previous map is still the one on screen.
   */
  const [placed, setPlaced] = useState<{ signature: string; layout: AtlasLayout } | null>(null);
  /** A graph the kernel refused, which is the one case where holding its last answer is wrong. */
  const [stalled, setStalled] = useState<string | null>(null);

  useEffect(() => {
    // An empty graph places to an empty box, and an empty box is not a map worth holding on
    // screen over the next one. The canvas draws its own answer for a graph with nothing in
    // it, and the placement has nothing to say about it either way.
    if (!graph.nodes.length) return;
    let current = true;
    layoutAtlasElk(graph.nodes, graph.edges, lens)
      .then((next) => {
        if (current) setPlaced({ signature: graphSignature, layout: next });
      })
      .catch((error) => {
        if (!current) return;
        setStalled(graphSignature);
        reportLayoutFailure(error);
      });
    return () => {
      current = false;
    };
    // The signature is what the placement is about; the graph is a new object per click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphSignature]);

  /**
   * Whether there is a kernel placement worth keeping on screen, which is any of them until
   * the kernel refuses this graph outright.
   */
  const holding = placed !== null && stalled !== graphSignature;

  /**
   * What the map is drawn from — and, just as much, what is not computed.
   *
   * One memo rather than two so the hand-rolled pass is skipped entirely in the case where its
   * answer would be discarded. It is O(n²) in the relaxation and the collision sweeps, which
   * is millions of pair evaluations at the size a real review produces, and paying that on
   * every filter toggle to throw the result away was the other half of the same defect.
   */
  return useMemo(
    () => (holding && placed ? placed.layout : layoutAtlas(graph.nodes, graph.edges, lens)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphSignature, holding, placed],
  );
}
