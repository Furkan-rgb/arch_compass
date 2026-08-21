import { type FormEvent } from "react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "../../lib/cn";
import { useIsTabletUp } from "../../lib/media";
import { humanise } from "../../lib/format";
import { Button } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { Mono } from "../../ui/meta";
import { MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, edgeKindClass } from "./geometry";
import { LENSES, type AtlasExplorerProps, type AtlasLens } from "./graph";
import { PULSES, type AtlasPulse } from "./pulse";
import type { AtlasViewport } from "./viewport";

/**
 * The strips above the map: what it is of, what is drawn on it, and where the camera points.
 *
 * They are separate rows because they answer separate questions. The lens changes which
 * graph is on screen; the filters narrow what is already drawn; the camera only changes which
 * part of it you are looking at, and a control that is set once should not out-shout one that
 * is pressed constantly.
 *
 * Every switch here is a `ToggleGroup` — one component, two variants. One-of-many gets a
 * track, many-of-many does not, and the reader learns which kind of question a row is asking
 * from its shape rather than from trying it.
 */

/** The lens, which decides what the map is *of* and is never folded away. */
export function LensPicker({
  lens,
  onLens,
}: {
  lens: AtlasLens;
  onLens: (lens: AtlasLens) => void;
}) {
  return (
    <div className="flex items-center gap-3 overflow-x-auto border-b border-rule px-3 py-2 scrollbar-none">
      <Mono className="shrink-0 text-[10px] uppercase tracking-[0.13em] text-ink-3">Lens</Mono>
      <ToggleGroup
        type="single"
        value={lens}
        // Radix hands back "" when the pressed item is pressed again. A lens is not something
        // the map can be without, so the empty answer re-selects what was already selected.
        onValueChange={(value) => value && onLens(value as AtlasLens)}
        aria-label="Graph lens"
      >
        {LENSES.map(({ value, label, hint }) => (
          <ToggleGroupItem key={value} value={value} title={hint}>
            {label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

/** The row that narrows what is drawn: search, the filters, and the atlas-wide asks. */
export function LensControls({
  lens,
  searchValue,
  onSearchValue,
  onSubmitSearch,
  hideTests,
  onHideTests,
  publicOnly,
  onPublicOnly,
  pulse,
  onPulse,
  onExploreAtlas,
  edgeKinds,
  hiddenEdgeKinds,
  onToggleEdgeKind,
  loading,
}: {
  lens: AtlasLens;
  searchValue: string;
  onSearchValue: (value: string) => void;
  onSubmitSearch: (event: FormEvent) => void;
  hideTests: boolean;
  onHideTests: () => void;
  publicOnly: boolean;
  onPublicOnly: () => void;
  pulse: AtlasPulse;
  onPulse: (pulse: AtlasPulse) => void;
  onExploreAtlas?: AtlasExplorerProps["onExploreAtlas"];
  /** Every relationship kind this graph has, which is what there is to filter by. */
  edgeKinds: string[];
  hiddenEdgeKinds: Set<string>;
  onToggleEdgeKind: (kind: string) => void;
  loading: boolean;
}) {
  const roomy = useIsTabletUp();
  const drawnKinds = edgeKinds.filter((kind) => !hiddenEdgeKinds.has(kind));

  return (
    /**
     * Folded on a phone, laid out on a tablet and up.
     *
     * Seven rows of controls above a map is a surface whose subject is below the fold. The
     * lens is the one control that changes what the map is *of*, so it stays out; everything
     * else narrows what is already drawn and can wait to be asked for.
     *
     * `<details>` rather than a button and a piece of state, so the disclosure role, the
     * keyboard path and the expanded state announced to a screen reader are free and correct.
     * `open` is driven by the width rather than by CSS, because forcing a details element
     * open with a rule is fighting the user agent over an element it owns.
     */
    <details
      open={roomy}
      className="group border-b border-rule [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="flex min-h-11 list-none items-center gap-2 px-3 lg:hidden">
        <Mono className="text-[10px] uppercase tracking-[0.13em] text-ink-3">
          Search and filters
        </Mono>
        <span aria-hidden="true" className="ml-auto font-mono text-xs text-ink-3 group-open:hidden">
          +
        </span>
        <span
          aria-hidden="true"
          className="ml-auto hidden font-mono text-xs text-ink-3 group-open:inline"
        >
          −
        </span>
      </summary>

      <div className="space-y-2.5 border-t border-rule px-3 py-2.5 lg:border-t-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
          <form
            className="flex min-w-0 flex-1 basis-56 items-center gap-2"
            role="search"
            onSubmit={onSubmitSearch}
          >
            <SearchInput
              value={searchValue}
              onValueChange={onSearchValue}
              label="Search the repository atlas"
              placeholder="Find a module, class or path"
              className="flex-1"
            />
            <Button type="submit" variant="secondary" size="sm" disabled={!searchValue.trim()}>
              Find
            </Button>
          </form>

          {/* Two independent settings, so no track: either, both or neither can be on. */}
          <ToggleGroup
            type="multiple"
            variant="chips"
            value={[hideTests && "tests", publicOnly && "public"].filter(
              (value): value is string => Boolean(value),
            )}
            aria-label="Which elements to leave out"
          >
            <ToggleGroupItem value="tests" onClick={onHideTests}>
              Hide tests
            </ToggleGroupItem>
            <ToggleGroupItem value="public" onClick={onPublicOnly}>
              Public only
            </ToggleGroupItem>
          </ToggleGroup>

          {/* A menu rather than a fifth row of chips. The lens changes which graph is on
              screen and earns its width; this only changes how the selected card's
              neighbourhood moves. */}
          <div className="flex items-center gap-2">
            <Mono className="shrink-0 text-[10px] uppercase tracking-[0.13em] text-ink-3">
              Highlight
            </Mono>
            <Select value={pulse} onValueChange={(value) => onPulse(value as AtlasPulse)}>
              <SelectTrigger aria-label="Highlight motion for the selected element">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PULSES.map(({ value, label }) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {lens === "judged" && onExploreAtlas && (
            <div className="ml-auto inline-flex items-center gap-0.5">
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() => onExploreAtlas("signals")}
              >
                Surface signals
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() => onExploreAtlas("cycles")}
              >
                Surface cycles
              </Button>
            </div>
          )}
        </div>

        {edgeKinds.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule pt-2.5">
            <Mono className="shrink-0 text-[10px] uppercase tracking-[0.13em] text-ink-3">
              Relationships
            </Mono>
            <ToggleGroup
              type="multiple"
              variant="chips"
              value={drawnKinds}
              onValueChange={() => undefined}
              aria-label="Relationship filters"
            >
              {edgeKinds.map((kind) => (
                <ToggleGroupItem
                  key={kind}
                  value={kind}
                  onClick={() => onToggleEdgeKind(kind)}
                  title={`${humanise(kind)} relationships`}
                >
                  <i
                    aria-hidden="true"
                    className={`atlas-edge-swatch atlas-edge-swatch--${edgeKindClass(kind)}`}
                  />
                  {humanise(kind)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        )}
      </div>
    </details>
  );
}

/** The strip under the controls: where the camera is pointed. */
export function ViewportToolbar({
  instructionsId,
  view,
}: {
  instructionsId: string;
  view: AtlasViewport;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-surface-2 px-3 py-2">
      <Mono
        className="hidden text-[10px] uppercase tracking-[0.13em] text-ink-3 lg:inline"
        id={instructionsId}
      >
        Drag to pan · pinch or ⌘-scroll to zoom
      </Mono>
      <div
        className="ml-auto inline-flex items-center gap-2"
        role="group"
        aria-label="Graph viewport controls"
      >
        <div className="inline-flex items-center rounded-sm border border-rule bg-sunken/70 p-0.5">
          <CameraButton
            label="Zoom out"
            disabled={view.zoom <= MIN_ZOOM}
            onClick={() => view.setViewportZoom(view.zoom - ZOOM_STEP)}
          >
            −
          </CameraButton>
          <output
            aria-live="polite"
            aria-label="Current graph zoom"
            className="w-11 text-center font-mono text-[11px] tabular-nums text-ink-2"
          >
            {Math.round(view.zoom * 100)}%
          </output>
          <CameraButton
            label="Zoom in"
            disabled={view.zoom >= MAX_ZOOM}
            onClick={() => view.setViewportZoom(view.zoom + ZOOM_STEP)}
          >
            +
          </CameraButton>
        </div>
        <Button variant="ghost" size="sm" onClick={view.fitGraph}>
          Fit
        </Button>
        <ToggleGroup
          type="multiple"
          variant="chips"
          value={[view.fullscreen && "fullscreen", view.showMinimap && "minimap"].filter(
            (value): value is string => Boolean(value),
          )}
          aria-label="How the map is framed"
        >
          <ToggleGroupItem value="fullscreen" onClick={() => void view.toggleFullscreen()}>
            {view.fullscreen ? "Exit full screen" : "Full screen"}
          </ToggleGroupItem>
          <ToggleGroupItem value="minimap" onClick={() => view.setShowMinimap((v) => !v)}>
            Minimap
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>
  );
}

/**
 * A zoom step. `−` and `+` are the mathematical operators rather than icons on purpose: the
 * rule that a mark is drawn rather than typed is about the marks that carry *meaning* — a
 * verdict, a delta — and these two are the arithmetic they look like.
 */
function CameraButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex size-7 pointer-coarse:size-10 items-center justify-center rounded-[4px]",
        "font-mono text-sm text-ink-2 transition hover:bg-control hover:text-ink",
        "disabled:pointer-events-none disabled:opacity-40",
      )}
    >
      {children}
    </button>
  );
}
