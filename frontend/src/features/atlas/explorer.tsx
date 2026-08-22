import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { plural } from "../../lib/format";
import { isPlainShortcut } from "../../lib/keyboard";
import { Mono } from "../../ui/meta";
import { AtlasCanvas, type AtlasEmptyAnswer } from "./canvas";
import { ExplorationStrip, LensControls, LensPicker, ViewportToolbar } from "./controls";
import { AtlasDetailPanel } from "./detail";
import { LENSES, type AtlasExplorerProps, type AtlasLens } from "./graph";
import { usePlacedLayout } from "./placement";
import { readPulse, writePulse, type AtlasPulse } from "./pulse";
import { useAtlasViewport } from "./viewport";
import { graphSignatureOf, visibleGraphFor } from "./visible-graph";

/**
 * The map of a repository, whole: controls, canvas, detail panel, and the count of what is on
 * screen.
 *
 * This file is the assembly — which graph the lens and the filters leave visible, and where
 * each part goes. The canvas draws it, the camera lives in `viewport.ts`, and the placement is
 * decided in `layout.ts`. Nothing here knows what a review is: the caller hands it nodes and
 * edges and says what to do when a card is opened.
 */
export function AtlasExplorer({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  loading = false,
  emptyMessage = "Nothing in this atlas is drawn under the current lens.",
  initialLens = "structure",
  onOpenFinding,
  onExploreNode,
  onExploreAtlas,
  onSearch,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  highlightedNodeIds = [],
  highlightedEdgeIds = [],
  header,
  exploreNote,
  traceNote,
  revealedNodeIds = [],
  explorations = [],
  onResetExplorations,
}: AtlasExplorerProps) {
  const [lens, setLens] = useState<AtlasLens>(initialLens);
  const [searchValue, setSearchValue] = useState("");
  const [hiddenEdgeKinds, setHiddenEdgeKinds] = useState<Set<string>>(new Set());
  const [hideTests, setHideTests] = useState(false);
  const [publicOnly, setPublicOnly] = useState(false);
  const [pulse, setPulse] = useState<AtlasPulse>(readPulse);
  /**
   * Every card the last submitted term matched, and which of them the reader is standing on.
   *
   * A set rather than one card because a term with nine matches has nine answers. The search
   * used to take the first `find` and select it, which is a search that answered "is there
   * one" — a different and much less useful question than the one the box asks.
   */
  const [matches, setMatches] = useState<{ ids: string[]; index: number }>({ ids: [], index: 0 });
  const selected = selectedNodeId
    ? nodes.find((node) => node.id === selectedNodeId)
    : undefined;
  const availableEdgeKinds = useMemo(
    () => [...new Set(edges.map((edge) => edge.kind))].sort(),
    [edges],
  );
  const revealed = useMemo(() => new Set(revealedNodeIds), [revealedNodeIds]);
  const visibleGraph = useMemo(
    () =>
      visibleGraphFor({
        nodes,
        edges,
        lens,
        hiddenEdgeKinds,
        hideTests,
        publicOnly,
        selected,
        revealed,
      }),
    [edges, hiddenEdgeKinds, hideTests, lens, nodes, publicOnly, revealed, selected],
  );
  const graphSignature = useMemo(
    () => graphSignatureOf(lens, visibleGraph),
    [lens, visibleGraph],
  );
  const layout = usePlacedLayout(visibleGraph, lens, graphSignature);
  const highlightedNodes = useMemo(() => new Set(highlightedNodeIds), [highlightedNodeIds]);
  const highlightedEdges = useMemo(() => new Set(highlightedEdgeIds), [highlightedEdgeIds]);
  const drawnEdgeIds = useMemo(
    () => new Set(visibleGraph.edges.map((edge) => edge.id)),
    [visibleGraph],
  );
  /**
   * The matches that are still on the map, and where in them the reader is standing.
   *
   * Dropping an exploration takes its cards away, and a count of five over three rings is the
   * surface disagreeing with itself. Derived rather than pruned in place, because the source
   * of truth for what is on the map is what is on the map.
   */
  const matchIds = useMemo(() => {
    if (!matches.ids.length) return matches.ids;
    const present = new Set(nodes.map((node) => node.id));
    return matches.ids.filter((id) => present.has(id));
  }, [matches, nodes]);
  const matchIndex = matchIds.length ? Math.min(matches.index, matchIds.length - 1) : 0;
  const matchedNodes = useMemo(() => new Set(matchIds), [matchIds]);
  const view = useAtlasViewport({ layout, graphSignature, selected, onSelectNode });
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const choosePulse = (next: AtlasPulse) => {
    setPulse(next);
    writePulse(next);
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const term = searchValue.trim().toLocaleLowerCase();
    if (!term) return;
    // What is already on the map is found on the map. Only a term that matches nothing here
    // becomes a query, because a query brings back cards the reader did not ask to add.
    const found = nodes.filter((node) =>
      `${node.label} ${node.qualified} ${node.path} ${node.kind}`
        .toLocaleLowerCase()
        .includes(term),
    );
    setMatches({ ids: found.map((node) => node.id), index: 0 });
    if (found.length) onSelectNode(found[0].id);
    else onSearch?.(searchValue.trim());
  };

  /** Round the matches, forwards or back, selecting each one as it lands on it. */
  const stepMatch = (backwards = false) => {
    if (matchIds.length < 2) return;
    const next = (matchIndex + (backwards ? -1 : 1) + matchIds.length) % matchIds.length;
    setMatches({ ids: matchIds, index: next });
    onSelectNode(matchIds[next]);
  };

  /**
   * `n` and `Shift-n` walk the matches, behind the guards every document-bound key here carries.
   *
   * Bound only while there is something to walk, so the letter is the reader's own everywhere
   * else. `isPlainShortcut` is what keeps it out of the search box it was just typed into.
   */
  useEffect(() => {
    if (matchIds.length < 2) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "n" || !isPlainShortcut(event)) return;
      event.preventDefault();
      stepMatch(event.shiftKey);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchIds, matchIndex]);

  const toggleEdgeKind = (kind: string) => {
    setHiddenEdgeKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  const clearFilters = () => {
    setHiddenEdgeKinds(new Set());
    setHideTests(false);
    setPublicOnly(false);
  };

  /**
   * Why the canvas is blank, worked out where the answer is knowable.
   *
   * The canvas has the node count and nothing else, so it printed the caller's sentence
   * whatever had emptied it — telling a reader who pressed "Public only" that the review's
   * elements were gone from the indexed atlas. Three causes, and only the first is the
   * caller's: nothing was given, the lens draws nothing, or the filters take everything out.
   * Each of the other two is checked by asking what the graph would be without it, which is
   * the only way to be sure which one to name, and is only ever run on an empty map.
   */
  const empty = useMemo<AtlasEmptyAnswer>(() => {
    if (!nodes.length) return { sentence: emptyMessage };
    if (visibleGraph.nodes.length) return { sentence: emptyMessage };

    const named = [
      hideTests && "Hide tests",
      publicOnly && "Public only",
      hiddenEdgeKinds.size > 0 &&
        `${plural(hiddenEdgeKinds.size, "relationship filter")} switched off`,
    ].filter((value): value is string => Boolean(value));
    if (named.length) {
      const unfiltered = visibleGraphFor({
        nodes,
        edges,
        lens,
        hiddenEdgeKinds: new Set(),
        hideTests: false,
        publicOnly: false,
        selected,
        revealed,
      });
      if (unfiltered.nodes.length) {
        return {
          sentence: `${named.join(" and ")} leaves nothing to draw. Without ${
            named.length > 1 ? "them" : "it"
          } this lens draws ${plural(unfiltered.nodes.length, "element")}.`,
          action: { label: "Clear the filters", onAction: clearFilters },
        };
      }
    }

    for (const other of LENSES) {
      if (other.value === lens) continue;
      const drawn = visibleGraphFor({
        nodes,
        edges,
        lens: other.value,
        hiddenEdgeKinds,
        hideTests,
        publicOnly,
        selected,
        revealed,
      });
      if (!drawn.nodes.length) continue;
      return {
        sentence: `The ${lens} lens draws nothing here. The ${other.label.toLocaleLowerCase()} lens draws ${plural(
          drawn.nodes.length,
          "element",
        )}.`,
        action: {
          label: `Show the ${other.label.toLocaleLowerCase()} lens`,
          onAction: () => setLens(other.value),
        },
      };
    }

    return {
      sentence: `Nothing is drawn: the ${lens} lens and the filters that are on leave no element between them.`,
      ...(named.length
        ? { action: { label: "Clear the filters", onAction: clearFilters } }
        : {}),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emptyMessage, edges, hiddenEdgeKinds, hideTests, lens, nodes, publicOnly, visibleGraph]);

  // A traced path is drawn along dependency edges, so the lens that draws none of them would
  // answer the request with an unchanged picture.
  useEffect(() => {
    if (highlightedEdgeIds.length) setLens("dependencies");
  }, [highlightedEdgeIds]);

  /**
   * If the lens this opened on draws nothing, open on one that does.
   *
   * A caller picks the lens that answers the question its surface is about, and that lens can
   * legitimately be empty for a particular graph — a review whose elements are no longer in
   * the atlas has nothing judged to draw, and `judged` would greet the reader with "nothing is
   * drawn under the current lens" over a graph that is sitting right there. Once, and only
   * while the reader has not chosen a lens themselves: an empty lens they picked is an answer,
   * and moving them off it would be the surface arguing with them.
   */
  const settled = useRef(false);
  useEffect(() => {
    if (settled.current || !nodes.length) return;
    settled.current = true;
    if (visibleGraph.nodes.length) return;
    for (const fallback of ["dependencies", "structure"] as const) {
      if (fallback === lens) continue;
      const drawn = visibleGraphFor({
        nodes,
        edges,
        lens: fallback,
        hiddenEdgeKinds,
        hideTests,
        publicOnly,
        selected,
        revealed,
      });
      if (drawn.nodes.length) {
        setLens(fallback);
        return;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, visibleGraph.nodes.length]);

  return (
    <section
      ref={view.panelRef}
      className={`atlas-panel ${view.fullscreen ? "atlas-panel--fullscreen" : ""}`}
      aria-label="The repository's structure"
    >
      {header}

      <LensPicker lens={lens} onLens={setLens} />

      <LensControls
        searchValue={searchValue}
        onSearchValue={(value) => {
          setSearchValue(value);
          // The count belongs to the term that was submitted, so editing the box retires it.
          if (matches.ids.length) setMatches({ ids: [], index: 0 });
        }}
        onSubmitSearch={submitSearch}
        matches={{ count: matchIds.length, index: matchIndex }}
        onNextMatch={stepMatch}
        hideTests={hideTests}
        onHideTests={() => setHideTests((value) => !value)}
        publicOnly={publicOnly}
        onPublicOnly={() => setPublicOnly((value) => !value)}
        pulse={pulse}
        onPulse={choosePulse}
        onExploreAtlas={onExploreAtlas}
        edgeKinds={availableEdgeKinds}
        hiddenEdgeKinds={hiddenEdgeKinds}
        onToggleEdgeKind={toggleEdgeKind}
        loading={loading}
      />

      {onResetExplorations ? (
        <ExplorationStrip explorations={explorations} onReset={onResetExplorations} />
      ) : null}

      <ViewportToolbar instructionsId={instructionsId} view={view} />

      <div className="atlas-layout">
        <AtlasCanvas
          graph={visibleGraph}
          layout={layout}
          selected={selected}
          onSelectNode={onSelectNode}
          highlightedNodes={highlightedNodes}
          highlightedEdges={highlightedEdges}
          matchedNodes={matchedNodes}
          pulse={pulse}
          loading={loading}
          empty={empty}
          view={view}
          gridId={gridId}
          arrowId={arrowId}
          instructionsId={instructionsId}
        />

        <AtlasDetailPanel
          node={selected}
          edges={edges}
          nodes={nodes}
          drawnEdgeIds={drawnEdgeIds}
          onSelectNode={onSelectNode}
          onOpenFinding={onOpenFinding}
          onExploreNode={onExploreNode}
          pathStartNodeId={pathStartNodeId}
          onSetPathStart={onSetPathStart}
          onTracePath={onTracePath}
          exploreNote={exploreNote}
          traceNote={traceNote}
          loading={loading}
        />
      </div>

      {/* Never silently. A bounded view that does not say it is bounded reads as a complete
          one, and a reader would take "nothing else touches this" from a picture that is
          simply drawing one lens of it. */}
      <Mono
        className="border-t border-rule bg-surface-2 px-3 py-2 text-[10px] uppercase tracking-[0.13em] text-ink-3"
        aria-live="polite"
      >
        {visibleGraph.nodes.length} of {plural(nodes.length, "element")} ·{" "}
        {visibleGraph.edges.length} of {plural(edges.length, "relationship")} · {lens} lens
      </Mono>
    </section>
  );
}
