/** The name and the icon each node state wears, wherever on the map it is drawn. */

import { AlertTriangle, CheckCircle2, CircleDot, Layers3 } from "lucide-react";

import type { AtlasNodeState } from "./graph-model";

/**
 * The map's own name for each state, and the icon that stands for it wherever it is drawn.
 *
 * One table read by the legend and by the detail panel, so a state cannot be labelled in the
 * toolbar and left out of the panel — which is what happened to `cleared`, drawn on the canvas
 * and named nowhere. A caller may rename what these say through `legendLabels`; it may not add
 * a state, because the canvas draws these five and no others.
 */
export const STATE_ICON: Record<AtlasNodeState, typeof CircleDot> = {
  normal: CircleDot,
  hotspot: AlertTriangle,
  contained: CheckCircle2,
  cleared: CheckCircle2,
  inference: Layers3,
};

export const STATE_LABEL: Record<AtlasNodeState, string> = {
  normal: "Normal",
  hotspot: "Hotspot",
  contained: "Contained",
  cleared: "Cleared",
  inference: "Advisor inference",
};

/* Read in this order wherever the states are listed, coarsest first. */
export const STATE_ORDER: AtlasNodeState[] = [
  "normal",
  "hotspot",
  "contained",
  "cleared",
  "inference",
];
