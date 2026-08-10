/** The strip under the controls: what the states mean, which relationships are drawn, and the camera buttons. */

import {
  CircleDot,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  Scan,
} from "lucide-react";

import { humanizeLabel } from "../components";
import { MAX_ZOOM, MIN_ZOOM, ZOOM_STEP } from "./geometry";
import type { AtlasNodeState } from "./graph-model";
import { edgeKindClass } from "./labels";
import type { AtlasViewport } from "./use-atlas-viewport";

/** One key of the legend: a state this graph contains, in this caller's word for it. */
export interface LegendKey {
  state: AtlasNodeState;
  label: string;
  Icon: typeof CircleDot;
}

export function ViewportToolbar({
  legend,
  edgeKinds,
  hiddenEdgeKinds,
  onToggleEdgeKind,
  instructionsId,
  view,
}: {
  legend: LegendKey[];
  /** Every relationship kind this graph has, which is what there is to filter by. */
  edgeKinds: string[];
  hiddenEdgeKinds: Set<string>;
  onToggleEdgeKind: (kind: string) => void;
  instructionsId: string;
  view: AtlasViewport;
}) {
  return (
    <div className="atlas-toolbar">
      <div className="atlas-legend" aria-label="Atlas legend">
        {legend.map(({ state, label, Icon }) => (
          <span key={state} className={`atlas-legend__key atlas-legend__key--${state}`}>
            <Icon size={13} /> {label}
          </span>
        ))}
      </div>
      {edgeKinds.length > 0 && (
        <div className="atlas-edge-filters" aria-label="Relationship filters">
          {edgeKinds.map((kind) => (
            <button
              key={kind}
              type="button"
              className={hiddenEdgeKinds.has(kind) ? "" : "active"}
              aria-pressed={!hiddenEdgeKinds.has(kind)}
              onClick={() => onToggleEdgeKind(kind)}
            >
              <i className={`atlas-edge-swatch atlas-edge-swatch--${edgeKindClass(kind)}`} />
              {humanizeLabel(kind)}
            </button>
          ))}
        </div>
      )}
      <span className="atlas-toolbar__hint" id={instructionsId}>
        Drag to pan · scroll to move · pinch or Ctrl/⌘ + scroll to zoom
      </span>
      <div className="atlas-controls" role="group" aria-label="Graph viewport controls">
        <button
          type="button"
          aria-label="Zoom out"
          disabled={view.zoom <= MIN_ZOOM}
          onClick={() => view.setViewportZoom(view.zoom - ZOOM_STEP)}
        >
          <Minus size={14} />
        </button>
        <output aria-live="polite" aria-label="Current graph zoom">
          {Math.round(view.zoom * 100)}%
        </output>
        <button
          type="button"
          aria-label="Zoom in"
          disabled={view.zoom >= MAX_ZOOM}
          onClick={() => view.setViewportZoom(view.zoom + ZOOM_STEP)}
        >
          <Plus size={14} />
        </button>
        <button type="button" aria-label="Fit graph to view" onClick={view.fitGraph}>
          <Scan size={14} />
        </button>
        <button
          type="button"
          aria-label={view.fullscreen ? "Exit full screen" : "Enter full screen"}
          aria-pressed={view.fullscreen}
          onClick={() => void view.toggleFullscreen()}
        >
          {view.fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
        <button
          type="button"
          aria-label={view.showMinimap ? "Hide graph minimap" : "Show graph minimap"}
          aria-pressed={view.showMinimap}
          onClick={() => view.setShowMinimap((value) => !value)}
        >
          <MapIcon size={14} />
        </button>
      </div>
    </div>
  );
}
