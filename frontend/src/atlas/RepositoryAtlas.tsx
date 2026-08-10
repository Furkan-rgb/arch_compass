/**
 * The map of a repository, whole: heading, controls, canvas, detail panel and metric strip.
 *
 * This file is the assembly — which graph the lens and filters leave visible, and where each
 * part of the map goes. The canvas draws it, the camera lives in `use-atlas-viewport`, and the
 * placement is decided in `graph-placement`.
 */

import { type FormEvent, useEffect, useId, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";

import { AtlasCanvas } from "./atlas-canvas";
import { AtlasDetailPanel } from "./detail-panel";
import type { AtlasLens, RepositoryAtlasProps } from "./graph-model";
import { usePlacedLayout } from "./graph-placement";
import { LensControls } from "./lens-controls";
import { AtlasMetricStrip } from "./metric-strip";
import { STATE_ICON, STATE_LABEL, STATE_ORDER } from "./node-states";
import type { AtlasPulse } from "./pulse";
import { useAtlasViewport } from "./use-atlas-viewport";
import { ViewportToolbar } from "./viewport-toolbar";
import { graphSignatureOf, visibleGraphFor } from "./visible-graph";

export function RepositoryAtlas({
  title = "RepositoryAtlas",
  description,
  mode = "repository",
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  loading = false,
  emptyMessage = "No bounded atlas nodes are available yet.",
  initialLens = "structure",
  legendLabels,
  onOpenFinding,
  onExploreNode,
  onExploreAtlas,
  onSearch,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  highlightedNodeIds = [],
  highlightedEdgeIds = [],
}: RepositoryAtlasProps) {
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
  /**
   * The states this graph actually contains, in this caller's words for them.
   *
   * Only the ones present: a key naming five states over a map that draws two sends the reader
   * looking for the other three. Off the whole graph rather than the visible one, so switching
   * lens does not rewrite the key beside the canvas as well as the canvas.
   */
  const legend = useMemo(() => {
    const present = new Set(nodes.map((node) => node.state));
    return STATE_ORDER.filter((state) => present.has(state)).map((state) => ({
      state,
      label: legendLabels?.[state] ?? STATE_LABEL[state],
      Icon: STATE_ICON[state],
    }));
  }, [legendLabels, nodes]);
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
      }),
    [edges, hiddenEdgeKinds, hideTests, lens, nodes, publicOnly, selected],
  );
  const graphSignature = useMemo(
    () => graphSignatureOf(lens, visibleGraph),
    [lens, visibleGraph],
  );
  const layout = usePlacedLayout(visibleGraph, lens, graphSignature);
  const highlightedNodes = new Set(highlightedNodeIds);
  const highlightedEdges = new Set(highlightedEdgeIds);
  const view = useAtlasViewport({ layout, graphSignature, selected, onSelectNode });
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const term = searchValue.trim().toLocaleLowerCase();
    if (!term) return;
    const localMatch = nodes.find((node) =>
      `${node.label} ${node.path} ${node.kind}`.toLocaleLowerCase().includes(term),
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

  useEffect(() => {
    if (highlightedEdgeIds.length) setLens("dependencies");
  }, [highlightedEdgeIds]);

  return (
    <section
      ref={view.panelRef}
      className={`atlas-panel ${view.fullscreen ? "atlas-panel--fullscreen" : ""}`}
      aria-labelledby="atlas-heading"
    >
      <div className="atlas-panel__header">
        <div>
          <span className="eyebrow">
            {mode === "repository" ? "Bounded structural evidence" : "Proposed architecture"}
          </span>
          <h2 id="atlas-heading">{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <Badge variant={mode === "repository" ? "accent" : "neutral"}>
          {mode === "repository" ? `${nodes.length} surfaced nodes` : "Greenfield canvas"}
        </Badge>
      </div>

      <LensControls
        lens={lens}
        onLens={setLens}
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
        loading={loading}
      />

      <ViewportToolbar
        legend={legend}
        edgeKinds={availableEdgeKinds}
        hiddenEdgeKinds={hiddenEdgeKinds}
        onToggleEdgeKind={toggleEdgeKind}
        instructionsId={instructionsId}
        view={view}
      />

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
          mode={mode}
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
          loading={loading}
        />
      </div>

      {selected && <AtlasMetricStrip node={selected} />}
      <p className="atlas-visible-count" aria-live="polite">
        Showing {visibleGraph.nodes.length} of {nodes.length} surfaced nodes and{" "}
        {visibleGraph.edges.length} of {edges.length} relationships in the {lens} lens.
      </p>
    </section>
  );
}
