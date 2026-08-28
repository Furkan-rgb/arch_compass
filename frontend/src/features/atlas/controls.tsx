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
import { useHasKeyboard } from "../../lib/media";
import { humanise } from "../../lib/format";
import { Button } from "../../ui/button";
import { SearchInput } from "../../ui/field";
import { ChevronDown } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { Tooltip } from "../../ui/tooltip";
import { MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, edgeKindClass } from "./geometry";
import { LENSES, type AtlasExploration, type AtlasExplorerProps, type AtlasLens } from "./graph";
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
  const chosen = LENSES.find((entry) => entry.value === lens);
  return (
    /* Wrapping rather than scrolling as one row: the switch keeps its own scroller for the
       three buttons, and the sentence beside it drops to a second line on a screen too narrow
       to hold both. A hint truncated to "What a finding was ma…" would be the tooltip's defect
       in a different shape. */
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-rule px-3 py-2">
      <Mono className="shrink-0 text-[11px] uppercase tracking-[0.08em] text-ink-3">Lens</Mono>
      <div className="flex min-w-0 items-center overflow-x-auto scrollbar-none">
        <ToggleGroup
          type="single"
          value={lens}
          // Radix hands back "" when the pressed item is pressed again. A lens is not something
          // the map can be without, so the empty answer re-selects what was already selected.
          onValueChange={(value) => value && onLens(value as AtlasLens)}
          aria-label="Graph lens"
        >
          {LENSES.map(({ value, label }) => (
            <ToggleGroupItem key={value} value={value}>
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      {/* What the chosen lens means, printed rather than hidden in a `title`.

          The surface opens on Judged, so the first map anybody sees is filtered by a concept
          nothing on screen defined. The three hints were written and are good — they were just
          delivered through a native tooltip, which needs a hover and a second of patience,
          never fires on touch and is unreachable from the keyboard. Printed here it changes
          with the lens and answers the question once instead of three times. */}
      {chosen ? <p className="text-[12px] leading-4 text-ink-2">{chosen.hint}</p> : null}
    </div>
  );
}

/** The row that narrows what is drawn: search, the filters, and the atlas-wide asks. */
export function LensControls({
  searchValue,
  onSearchValue,
  onSubmitSearch,
  matches,
  onNextMatch,
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
  searchValue: string;
  onSearchValue: (value: string) => void;
  onSubmitSearch: (event: FormEvent) => void;
  /** Every card the term matched, and which of them the reader is standing on. */
  matches: { count: number; index: number };
  onNextMatch: (backwards?: boolean) => void;
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
  const drawnKinds = edgeKinds.filter((kind) => !hiddenEdgeKinds.has(kind));

  return (
    /**
     * Folded at every width, and openable at every width.
     *
     * Four rows of controls and a paragraph above a map is a surface whose subject starts
     * three hundred pixels below the top of its own panel. The lens is the one control that
     * changes what the map is *of*, so it stays out; everything else narrows what is already
     * drawn and can wait to be asked for — and that argument does not stop being true on a
     * wide screen, where the map is the thing there is finally room for.
     *
     * This used to be `open={roomy}` over a summary that was `lg:hidden`, which is the worst
     * of both: above 1024px the fold was forced open by a width and there was no control on
     * screen to close it. Uncontrolled and closed, so the element the user agent owns is left
     * to the user agent, and the disclosure is a real one everywhere.
     *
     * `<details>` rather than a button and a piece of state, so the disclosure role, the
     * keyboard path and the expanded state announced to a screen reader are free and correct.
     */
    <details className="group border-b border-rule [&_summary::-webkit-details-marker]:hidden">
      {/* "Search and filters" was a promise the body did not keep: Surface signals and Surface
          cycles are requests that add cards to the map, and the Highlight menu is neither a
          search nor a filter. A reader looking for the atlas queries had no reason to open a
          disclosure that said it held filters. */}
      <summary className="flex min-h-11 list-none items-center gap-2 px-3">
        <Mono className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
          Search, filters and atlas queries
        </Mono>
        {/* A drawn mark rather than a typed `+` and `−`. Those two are the half of the
            drawn-mark rule no test can catch, and at `text-xs` a bare minus is a six-pixel
            dash standing between a phone reader and every filter on the surface. One element
            instead of two, and the rotation is a transform the reduced-motion block already
            collapses. The CameraButton's own `−` and `+` stay: there they are the arithmetic
            they look like. */}
        <ChevronDown
          aria-hidden="true"
          className="ml-auto size-3.5 text-ink-3 transition group-open:rotate-180"
        />
      </summary>

      <div className="space-y-2.5 border-t border-rule px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
          <form
            className="flex min-w-0 flex-1 basis-56 items-center gap-2"
            role="search"
            onSubmit={onSubmitSearch}
          >
            {/* Not "the repository": this box searches the atlas the caller handed the map,
                which is the same distinction the header paragraph beside the map makes in
                prose and the accessible names quietly contradicted. */}
            <SearchInput
              value={searchValue}
              onValueChange={onSearchValue}
              label="Search the atlas this map was given"
              placeholder="Find a module, class or path"
              className="flex-1"
            />
            <Button type="submit" variant="secondary" size="sm" disabled={!searchValue.trim()}>
              Find
            </Button>
            {/* Where the reader is in the matches, and the way to the next one. The search
                used to select one arbitrary card out of however many matched and say nothing
                at all about the rest, which is a search that has answered a different
                question from the one asked. */}
            {matches.count > 0 ? (
              <>
                <Mono className="shrink-0 text-[11px] tabular-nums text-ink-2">
                  {matches.index + 1} of {matches.count} match
                </Mono>
                {/* The keystrokes only where there are keys to make them. A tooltip opens on
                    hover and on focus, so on a touch device it never opens — and `n` and
                    `Shift-n` do not exist there anyway, so the hint was being shown only where
                    it was least needed. `useHasKeyboard` measures the input rather than the
                    width, which is what a key cap is really asking about, and is how the
                    shell, the docket and the decision bar already gate theirs. */}
                <WithKeyHint content="n for the next match, Shift-n for the one before.">
                  <Button variant="quiet" size="sm" onClick={() => onNextMatch()}>
                    Next
                  </Button>
                </WithKeyHint>
              </>
            ) : null}
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
            <Mono className="shrink-0 text-[11px] uppercase tracking-[0.08em] text-ink-3">
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

          {/* On every lens. These two ask the atlas a question about the whole repository —
              where the cycles are, where the signals are — and neither answer is about
              verdicts, so hiding them outside the judged lens took the cycle control away at
              exactly the moment a reader tracing a dependency path wanted it: tracing forces
              the lens to Dependencies. */}
          {onExploreAtlas && (
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
                onClick={() => onExploreAtlas("cyclic_components")}
              >
                Surface cycles
              </Button>
            </div>
          )}
        </div>

        {edgeKinds.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule pt-2.5">
            <Mono className="shrink-0 text-[11px] uppercase tracking-[0.08em] text-ink-3">
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

/**
 * What the reader has added to this map, and the way back to what it opened as.
 *
 * Drawn only once there is something to say, because a strip that is empty on every first
 * visit is a row of chrome above the surface it describes. The requests were already stored
 * and already named — every exploration is "Dependants of `Gateway`" in the note beside the
 * button that made it — so nothing here is new information. What was missing was that
 * nothing ever came *off* the map: three presses of "Two hops out" turned ninety cards into
 * three hundred for the rest of the session and the only way back was a reload.
 */
export function ExplorationStrip({
  explorations,
  onReset,
}: {
  explorations: AtlasExploration[];
  onReset: () => void;
}) {
  if (!explorations.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-rule px-3 py-2">
      <Mono className="shrink-0 text-[11px] uppercase tracking-[0.08em] text-ink-3">
        Added to the map
      </Mono>
      <ul className="flex min-w-0 flex-wrap items-center gap-1.5">
        {explorations.map((exploration) => (
          <li key={exploration.id}>
            {/* The word rather than a cross, because a cross that is not from the mark set
                is a typed glyph pretending to be an icon — and "Drop" is what pressing it
                does.

                The name is set explicitly because the visible order reads the wrong way round
                to anyone who cannot see the strip: "Dependants of Gateway Drop" is a subject
                followed by a verb, in the same chip shape the relationship filters two rows
                above use for a control that toggles rather than removes. */}
            <Button
              variant="quiet"
              size="sm"
              aria-label={`Drop ${exploration.label}`}
              onClick={exploration.onDrop}
            >
              {exploration.label}
              <span className="font-semibold uppercase tracking-[0.08em] text-[11px] text-ink-3">
                Drop
              </span>
            </Button>
          </li>
        ))}
      </ul>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onReset}>
        Reset the map
      </Button>
    </div>
  );
}

/** The strip under the controls: where the camera is pointed. */
export function ViewportToolbar({
  instructionsId,
  minimapAvailable,
  view,
}: {
  instructionsId: string;
  /** Whether there is a minimap to draw. A one-card graph has nothing to overview. */
  minimapAvailable: boolean;
  view: AtlasViewport;
}) {
  const hasKeyboard = useHasKeyboard();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-surface-2 px-3 py-2">
      {/* The whole instruction set, always in the document, and the canvas's `aria-describedby`
          points here.

          It pointed at the visible line below, which is `hidden` under 1024px — and
          `display: none` content is removed from the accessibility tree, so on every viewport
          a touch reader is likely to be using, the canvas's description resolved to nothing.
          Where it did resolve it described only pointer gestures, while the arrow keys, Home
          and End, Enter and `n` are all implemented and were named nowhere. The defect was
          what the sentence said, not whether it was displayed, so the fix is a sentence that
          says all of it rather than a different breakpoint on the old one. */}
      <span className="sr-only" id={instructionsId}>
        Drag or use the arrow keys to walk the cards. Home and End are its two ends, Enter
        selects the card you are on, and n steps through the elements a search matched. Pinch
        or hold the zoom modifier while scrolling to zoom. An arrow points from a dependent to
        what it depends on.
      </span>
      <Mono className="text-[11px] uppercase tracking-[0.08em] text-ink-3">
        {/* Which way an arrow points, said once, at every width. Every edge is stored from the
            dependent to the dependency and every arrowhead follows it, and a reader with no
            sentence to go on has to infer a convention from a triangle — which is a fact about
            the picture and does not stop being true on a phone.

            The gesture half is gated on the input rather than on the width, because a screen
            with no keyboard cannot make a ⌘-scroll and a screen with no touchscreen cannot
            pinch. It was the other way round: hidden below 1024px, so the pinch was taught
            only to the machines least likely to have a screen to pinch. */}
        {hasKeyboard ? "Drag to pan · ⌘-scroll to zoom · " : "Drag to pan · pinch to zoom · "}
        an arrow points from a dependent to what it depends on
      </Mono>
      {/* A fit that could not fit did it silently, and left the reader looking at a corner of
          a map they had asked to see whole.

          Always in the document, parked out of the flow until there is something to say: a
          live region inserted at the moment its content appears is a live region most screen
          readers never announce. */}
      <Mono
        aria-live="polite"
        className={cn("min-w-0 text-[11px] leading-4 text-ink-2", !view.fitFloored && "sr-only")}
      >
        {view.fitFloored
          ? "Fit stopped at the smallest readable card, so this is part of the map — the minimap says which part."
          : ""}
      </Mono>
      <div
        className="ml-auto inline-flex items-center gap-2"
        role="group"
        aria-label="Graph viewport controls"
      >
        <div className="inline-flex items-center rounded-sm border border-rule bg-sunken p-0.5">
          <CameraButton
            label="Zoom out"
            disabled={view.zoom <= MIN_ZOOM}
            onClick={() => view.setViewportZoom(view.zoom - ZOOM_STEP)}
          >
            −
          </CameraButton>
          {/* `aria-live="off"`, not a deleted attribute. `<output>` is `role="status"` and is a
              live region with no `aria-live` on it at all, so removing the attribute would
              leave the wheel-tick stream exactly where it was — and the panel already has one
              polite region, deliberately narrowed to the single sentence naming the card the
              reader is on. The element and its name stay: this is a readout to go and read. */}
          <output
            aria-live="off"
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
          {/* A one-card graph has no overview to draw, and the canvas already declines to
              draw one — which left the chip sitting in its raised, bordered on state over
              nothing at all. */}
          <ToggleGroupItem
            value="minimap"
            disabled={!minimapAvailable}
            title={minimapAvailable ? undefined : "A map of one element has nothing to overview"}
            onClick={() => view.setShowMinimap((v) => !v)}
          >
            Minimap
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>
  );
}

/**
 * A tooltip naming a keystroke, wrapped round a control only where a keyboard is in front of
 * the screen. Everywhere else the control is handed back bare rather than carrying a hint
 * nobody there can act on.
 */
function WithKeyHint({ content, children }: { content: string; children: React.ReactElement }) {
  const hasKeyboard = useHasKeyboard();
  if (!hasKeyboard) return children;
  return <Tooltip content={content}>{children}</Tooltip>;
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
        // 44px on a coarse pointer, which is the charter's fifth principle and what every
        // other control in the product answers the touch floor with — these two were the only
        // pair at 40, on the surface where pinch is the alternative and pinch competes with
        // the page scroll. `rounded-xs` is the documented 4px step rather than the same value
        // written out as an arbitrary one.
        "inline-flex size-7 pointer-coarse:size-11 items-center justify-center rounded-xs",
        "font-mono text-sm text-ink-2 transition hover:bg-control hover:text-ink",
        // Drawn rather than dimmed: at 40% the character a stepper *is* fell to about 3:1, and
        // the ink ramp's bottom step is measured against every ground it is painted on.
        "disabled:pointer-events-none disabled:text-ink-3",
      )}
    >
      {children}
    </button>
  );
}
