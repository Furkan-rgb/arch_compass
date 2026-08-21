import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { plural } from "../../lib/format";
import { Mono } from "../../ui/meta";
import { AtlasCanvas } from "./canvas";
import { LensControls, LensPicker, ViewportToolbar } from "./controls";
import { AtlasDetailPanel } from "./detail";
import type { AtlasExplorerProps, AtlasLens } from "./graph";
import { usePlacedLayout } from "./placement";
import type { AtlasPulse } from "./pulse";
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
}: AtlasExplorerProps) {
  const [lens, setLens] = useState<AtlasLens>(initialLens);
  const [searchValue, setSearchValue] = useState("");
  const [hiddenEdgeKinds, setHiddenEdgeKinds] = useState<Set<string>>(new Set());
  const [hideTests, setHideTests] = useState(false);
  const [publicOnly, setPublicOnly] = useState(false);
  const [pulse, setPulse] = useState<AtlasPulse>("comet");
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
  const view = useAtlasViewport({ layout, graphSignature, selected, onSelectNode });
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const term = searchValue.trim().toLocaleLowerCase();
    if (!term) return;
    // What is already on the map is found on the map. Only a term that matches nothing here
    // becomes a query, because a query brings back cards the reader did not ask to add.
    const localMatch = nodes.find((node) =>
      `${node.label} ${node.qualified} ${node.path} ${node.kind}`
        .toLocaleLowerCase()
        .includes(term),
    );
    if (localMatch) onSelectNode(localMatch.id);
    else onSearch?.(searchValue.trim());
  };

  const toggleEdgeKind = (kind: string) => {
    setHiddenEdgeKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

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
        lens={lens}
        searchValue={searchValue}
        onSearchValue={setSearchValue}
        onSubmitSearch={submitSearch}
        hideTests={hideTests}
        onHideTests={() => setHideTests((value) => !value)}
        publicOnly={publicOnly}
        onPublicOnly={() => setPublicOnly((value) => !value)}
        pulse={pulse}
        onPulse={setPulse}
        onExploreAtlas={onExploreAtlas}
        edgeKinds={availableEdgeKinds}
        hiddenEdgeKinds={hiddenEdgeKinds}
        onToggleEdgeKind={toggleEdgeKind}
        loading={loading}
      />

      <ViewportToolbar instructionsId={instructionsId} view={view} />

      <div className="atlas-layout">
        <AtlasCanvas
          graph={visibleGraph}
          layout={layout}
          selected={selected}
          onSelectNode={onSelectNode}
          highlightedNodes={highlightedNodes}
          highlightedEdges={highlightedEdges}
          pulse={pulse}
          loading={loading}
          emptyMessage={emptyMessage}
          view={view}
          gridId={gridId}
          arrowId={arrowId}
          instructionsId={instructionsId}
        />

        <AtlasDetailPanel
          node={selected}
          edges={edges}
          nodes={nodes}
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
