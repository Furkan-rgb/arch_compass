/** How the neighbourhood of the selected node is animated, and what the reader can pick from. */

/**
 * How the neighbourhood of a selected node is animated.
 *
 * A viewing preference and nothing more: the same nodes and the same relationships are
 * drawn whichever is chosen, and what changes is how hard the highlight argues for itself.
 * The static highlight stays available under `none`, because a map being read closely is a
 * map that should be allowed to hold still.
 *
 * Three of the four run along the edge in the direction it is stored — every edge is
 * written dependent → dependency, and `edgePath` starts its curve at the source, so a pulse
 * travels the way the arrowhead already points. `ripple` is the exception and pays for it:
 * it sends every pulse *out* of the node the reader clicked, which means the half of the
 * neighbourhood that points inward is played backwards. That trade is deliberate — ripple
 * is about the selection, the other three are about the relationship.
 */
export type AtlasPulse = "comet" | "travel" | "breathe" | "ripple" | "none";

export const PULSES: { value: AtlasPulse; label: string }[] = [
  { value: "comet", label: "Comet" },
  { value: "travel", label: "Travel" },
  { value: "breathe", label: "Breathe" },
  { value: "ripple", label: "Ripple" },
  { value: "none", label: "Still" },
];
