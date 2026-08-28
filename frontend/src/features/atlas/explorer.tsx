import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "../../lib/cn";
import { plural } from "../../lib/format";
import { isPlainShortcut } from "../../lib/keyboard";
import { useIsTabletUp } from "../../lib/media";
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
  /**
   * A term that found nothing on the map and was sent to the atlas instead.
   *
   * Kept so that when the answer arrives as new cards, the search can ring them and count
   * them — the local path gives the reader "3 of 9 match" and the `n` key, and a query-backed
   * search used to give neither, over cards it had just put on the map itself.
   */
  const [queriedTerm, setQueriedTerm] = useState("");
  /**
   * Whether the lens was moved out from under the reader to draw what they asked for.
   *
   * Forcing it is right — a path drawn on a lens with no dependency edges would be invisible —
   * but the surface's own rule is that every exploration writes back one sentence, and
   * replacing every verdict card on screen with a dependency mesh is a large thing to do
   * silently.
   */
  const [lensForced, setLensForced] = useState(false);
  const roomy = useIsTabletUp();
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
  const view = useAtlasViewport({
    layout,
    graphSignature,
    selected,
    onSelectNode,
    // The same breakpoint the layout uses, so a phone opens without an overlay sitting on its
    // cards and a desk opens with the overview. The chip still works either way.
    initialMinimap: roomy,
  });
  const definitionId = useId().replaceAll(":", "");
  const gridId = `atlas-grid-${definitionId}`;
  const arrowId = `atlas-arrow-${definitionId}`;
  const instructionsId = `atlas-instructions-${definitionId}`;

  const choosePulse = (next: AtlasPulse) => {
    setPulse(next);
    writePulse(next);
  };

  /** Every card on the map whose name, path or kind contains the term. */
  const findOnMap = (term: string) =>
    nodes.filter((node) =>
      `${node.label} ${node.qualified} ${node.path} ${node.kind}`
        .toLocaleLowerCase()
        .includes(term),
    );

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const term = searchValue.trim().toLocaleLowerCase();
    if (!term) return;
    // What is already on the map is found on the map. Only a term that matches nothing here
    // becomes a query, because a query brings back cards the reader did not ask to add.
    const found = findOnMap(term);
    setMatches({ ids: found.map((node) => node.id), index: 0 });
    if (found.length) {
      setQueriedTerm("");
      onSelectNode(found[0].id);
    } else {
      setQueriedTerm(term);
      onSearch?.(searchValue.trim());
    }
  };

  /**
   * The cards a query-backed search brought back, matched the moment they land.
   *
   * A term the map could not answer goes to the atlas, and the caller adds whatever comes back
   * as new nodes. Until this ran, that answer was a set of unringed cards with no counter and
   * no `n` key — a search that had done the work and then said nothing about it. Runs once per
   * term: the term is cleared as soon as it has matched, and editing the box clears it too.
   */
  useEffect(() => {
    if (!queriedTerm) return;
    const found = findOnMap(queriedTerm);
    if (!found.length) return;
    setQueriedTerm("");
    setMatches({ ids: found.map((node) => node.id), index: 0 });
    onSelectNode(found[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, queriedTerm]);

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

  /**
   * The one sentence the strip above the map says, composed from every part that has one.
   *
   * The caller owns what came back — it is what made the request — and the explorer owns the
   * fact that it moved the lens to draw it, because the explorer is what moved it.
   */
  const exploreAnswer = [
    exploreNote,
    traceNote,
    // Said only where it happened, and only until the reader chooses a lens of their own. A
    // path or a cycle can only be drawn along dependency edges, so asking for one moves the
    // map — and a reader who was on the Judged lens has just had every verdict card on screen
    // replaced by a dependency mesh.
    lensForced ? "Shown on the Dependencies lens, which is where those edges are drawn." : "",
  ]
    .filter(Boolean)
    .join(" ");

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
  // answer the request with an unchanged picture. Recorded when it actually moves the reader,
  // because the strip below has to say so — pressing "Surface cycles" while reading the Judged
  // lens replaces every verdict card on screen, and none of the notes mentioned it.
  useEffect(() => {
    if (!highlightedEdgeIds.length) {
      setLensForced(false);
      return;
    }
    if (lens === "dependencies") return;
    setLens("dependencies");
    setLensForced(true);
    // The highlight is what forces this; the lens is read, not reacted to, or choosing Judged
    // back again would be undone on the next render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      /* Not "the repository's structure". This component is handed a graph and knows nothing
         about where it came from — the caller's own header is where a claim about a repository
         or a review belongs, and `experience.md`'s hard rule for this surface is that a map
         must never let a reader believe it shows the repository as it stands now. */
      aria-label="The structure this map was given"
    >
      {header}

      <LensPicker
        lens={lens}
        onLens={(next) => {
          setLens(next);
          // A lens the reader picked is theirs; the note saying the map was moved for them is
          // about a lens they did not pick.
          setLensForced(false);
        }}
      />

      <LensControls
        searchValue={searchValue}
        onSearchValue={(value) => {
          setSearchValue(value);
          // The count belongs to the term that was submitted, so editing the box retires it —
          // and with it any query still waiting to answer the old term.
          if (matches.ids.length) setMatches({ ids: [], index: 0 });
          if (queriedTerm) setQueriedTerm("");
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

      {/**
       * What the last request came back with, above the map it was made about.
       *
       * These sentences lived inside the detail panel's "Explore from here" section, which
       * exists only while a card is selected — so a search that matched nothing on the map
       * answered into a block that was not rendered, and the state the surface opens in is the
       * state with nothing selected. The reader pressed Find and got nothing at all, which is
       * exactly the failure `experience.md` names: an empty answer is an answer, and every
       * exploration writes back one sentence, including "nothing came back".
       *
       * The per-card Explore buttons stay where they are; only the answer moved.
       *
       * Always in the document and parked out of the flow until there is something to say,
       * which is the same shape the fit notice in `ViewportToolbar` argues for: a live region
       * inserted at the moment its content appears is a live region most screen readers never
       * announce.
       */}
      <p
        aria-live="polite"
        className={cn(
          "border-b border-rule px-3 py-2 text-[12px] leading-5 text-ink",
          !exploreAnswer && "sr-only border-b-0",
        )}
      >
        {exploreAnswer}
      </p>

      <ViewportToolbar
        instructionsId={instructionsId}
        minimapAvailable={visibleGraph.nodes.length > 1}
        view={view}
      />

      {/**
       * The column beside the map, given back to the map while there is nothing to put in it.
       *
       * The detail panel's empty branch is one instruction paragraph in a fixed 20rem column,
       * so on arrival — which is every arrival, since nothing is selected — the surface spent
       * its second-largest region, and the brightest large shape on screen, telling the reader
       * to do something rather than helping them do it, beside a map already cutting cards off
       * both edges. That is 320px, or about 1.7 cards.
       *
       * Written here rather than as a modifier class in `styles.css` because the condition is a
       * piece of this component's state: a stylesheet cannot know whether a card is selected,
       * and a class that only exists to be toggled from here is the same decision in two files.
       */}
      <div
        className="atlas-layout"
        style={roomy && !selected ? { gridTemplateColumns: "minmax(0, 1fr)" } : undefined}
      >
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
          collapsed={roomy && !selected}
          loading={loading}
        />
      </div>

      {/* Never silently. A bounded view that does not say it is bounded reads as a complete
          one, and a reader would take "nothing else touches this" from a picture that is
          simply drawing one lens of it.

          Not a live region, though. The count changes on selection — the judged and dependency
          lenses add the selected card to the drawn set — so with `aria-live` an arrow-key walk
          produced two announcements per keystroke, against a panel that had deliberately
          narrowed its one polite region to the single sentence naming the card. This is
          orientation a reader can go and read. */}
      <Mono className="border-t border-rule bg-surface-2 px-3 py-2 text-[11px] uppercase tracking-[0.08em] text-ink-3">
        {visibleGraph.nodes.length} of {plural(nodes.length, "element")} ·{" "}
        {visibleGraph.edges.length} of {plural(edges.length, "relationship")} · {lens} lens
      </Mono>
    </section>
  );
}
