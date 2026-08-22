/**
 * How the neighbourhood of a selected node is animated, and what the reader can pick from.
 *
 * A viewing preference and nothing more: the same nodes and the same relationships are drawn
 * whichever is chosen, and what changes is how hard the highlight argues for itself. The
 * static highlight stays available under `none`, because a map being read closely is a map
 * that should be allowed to hold still.
 *
 * Three of the four run along the edge in the direction it is stored — every edge is written
 * dependent → dependency, and `edgePath` starts its curve at the source, so a pulse travels
 * the way the arrowhead already points. `ripple` is the exception and pays for it: it sends
 * every pulse *out* of the node the reader clicked, which means the half of the neighbourhood
 * that points inward is played backwards. That trade is deliberate — ripple is about the
 * selection, the other three are about the relationship.
 *
 * **The default is stillness.** It was `comet`, which meant that selecting a card started an
 * infinite animation on every edge touching it and left it running until the reader found a
 * menu and changed it — the one surface in the workbench with a loop inside the work. A map
 * being read closely should be allowed to hold still, and a reader who wants the movement can
 * say so once: the choice is remembered.
 */
export type AtlasPulse = "comet" | "travel" | "breathe" | "ripple" | "none";

export const PULSES: { value: AtlasPulse; label: string }[] = [
  { value: "comet", label: "Comet" },
  { value: "travel", label: "Travel" },
  { value: "breathe", label: "Breathe" },
  { value: "ripple", label: "Ripple" },
  { value: "none", label: "Still" },
];

/** Where the choice is remembered, in the same shape and with the same guard `lib/theme.ts` uses. */
export const PULSE_STORAGE_KEY = "archcompass.atlas.pulse";

/**
 * Storage access, guarded. A browser in private mode, or an embedded webview with storage
 * switched off, throws on access rather than returning null — and a viewing preference is not
 * worth failing a map over.
 */
export function readPulse(): AtlasPulse {
  try {
    const saved = globalThis.localStorage?.getItem(PULSE_STORAGE_KEY);
    return PULSES.some((option) => option.value === saved) ? (saved as AtlasPulse) : "none";
  } catch {
    return "none";
  }
}

export function writePulse(pulse: AtlasPulse): void {
  try {
    globalThis.localStorage?.setItem(PULSE_STORAGE_KEY, pulse);
  } catch {
    // A preference that cannot be remembered still applies for this visit.
  }
}
