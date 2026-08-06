import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  CircleDot,
  GitBranch,
  Layers3,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  Route,
  Scan,
  Search,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  type CSSProperties,
  type FormEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  type AtlasLayout,
  layoutAtlas,
  layoutAtlasElk,
  NODE_HEIGHT,
  NODE_WIDTH,
} from "./atlas-layout";
import { humanizeLabel } from "./components";
import type {
  AtlasExploreOperation,
  AtlasMetricNature,
  AtlasMetricScope,
  AtlasSignal,
} from "./types";

/**
 * `cleared` exists for the review atlas: a boundary that was examined and found to be
 * earning its place. It is not the absence of a finding, which is what `normal` means, and
 * a map that drew the two the same way would say the advisor never looked.
 */
export type AtlasNodeState =
  | "normal"
  | "hotspot"
  | "contained"
  | "inference"
  | "cleared";

export interface AtlasMetricView {
  label: string;
  value: number | string;
  group?: string;
  nature?: AtlasMetricNature;
  scope?: AtlasMetricScope;
  definition?: string;
  limitations?: string;
}

export interface AtlasNodeView {
  id: string;
  label: string;
  path: string;
  kind: string;
  isPublic?: boolean | null;
  state: AtlasNodeState;
  description?: string;
  metrics: AtlasMetricView[];
  evidenceCount?: number;
  signalCount?: number;
  signals?: AtlasSignal[];
  /**
   * Whether a review judged this node, and so whether `onOpenFinding` has somewhere to go.
   *
   * On the node rather than in a set beside the graph: the caller that knows a node was judged
   * is the one that built the node, and a second collection to keep in step with the first is
   * a way for the map to offer a link to a finding that is not there.
   */
  hasFinding?: boolean;
}

export interface AtlasEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  kind: string;
  confidence?: number;
  risk?: boolean;
}

export interface RepositoryAtlasProps {
  title?: string;
  description?: string;
  mode?: "repository" | "greenfield";
  nodes: AtlasNodeView[];
  edges: AtlasEdgeView[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  loading?: boolean;
  emptyMessage?: string;
  /**
   * The lens the map opens on. `structure` for a repository, because containment is how a
   * codebase is read; a caller whose graph is nearly all dependency edges says so, rather
   * than opening on a lens that draws almost none of it.
   */
  initialLens?: AtlasLens;
  /**
   * What this caller calls each node state, where its own vocabulary is the one the reader
   * has already been given. Only the legend is renamed: the states themselves are the map's,
   * and a caller that could redefine them would be drawing a different map.
   */
  legendLabels?: Partial<Record<AtlasNodeState, string>>;
  /** Where the selected node's finding is written, for a node that carries one. */
  onOpenFinding?: (nodeId: string) => void;
  onExploreNode?: (
    nodeId: string,
    operation: Exclude<
      AtlasExploreOperation,
      "search" | "shortest_path" | "cycles" | "signals"
    >,
    depth?: number,
  ) => void;
  onExploreAtlas?: (
    operation: Extract<AtlasExploreOperation, "cycles" | "signals">,
  ) => void;
  onSearch?: (term: string) => void;
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  highlightedNodeIds?: string[];
  highlightedEdgeIds?: string[];
}

export type AtlasLens = "structure" | "dependencies" | "risk";

/**
 * The map's own name for each state, and the icon that stands for it wherever it is drawn.
 *
 * One table read by the legend and by the detail panel, so a state cannot be labelled in the
 * toolbar and left out of the panel — which is what happened to `cleared`, drawn on the canvas
 * and named nowhere. A caller may rename what these say through `legendLabels`; it may not add
 * a state, because the canvas draws these five and no others.
 */
const STATE_ICON: Record<AtlasNodeState, typeof CircleDot> = {
  normal: CircleDot,
  hotspot: AlertTriangle,
  contained: CheckCircle2,
  cleared: CheckCircle2,
  inference: Layers3,
};

const STATE_LABEL: Record<AtlasNodeState, string> = {
  normal: "Normal",
  hotspot: "Hotspot",
  contained: "Contained",
  cleared: "Cleared",
  inference: "Advisor inference",
};

/* Read in this order wherever the states are listed, coarsest first. */
const STATE_ORDER: AtlasNodeState[] = [
  "normal",
  "hotspot",
  "contained",
  "cleared",
  "inference",
];

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

const PULSES: { value: AtlasPulse; label: string }[] = [
  { value: "comet", label: "Comet" },
  { value: "travel", label: "Travel" },
  { value: "breathe", label: "Breathe" },
  { value: "ripple", label: "Ripple" },
  { value: "none", label: "Still" },
];

/**
 * Low enough that "fit to view" can actually fit a large graph. A map of a few hundred cards
 * is wider than any viewport, and a floor that stops short of it turns the fit control into a
 * control that shows the reader one corner and calls it the whole.
 */
const MIN_ZOOM = .15;
const MAX_ZOOM = 1.8;
const ZOOM_STEP = .15;

/* Where the map is placed now lives beside this file; it is still read from here. */
export { layoutAtlas } from "./atlas-layout";
export type { AtlasClusterRegion, AtlasLayout } from "./atlas-layout";

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
  const visibleGraph = useMemo(() => {
    const nodeAllowed = (node: AtlasNodeView) => {
      if (node.id === selected?.id) return true;
      if (hideTests && node.kind.includes("test")) return false;
      if (publicOnly && node.isPublic === false) return false;
      return true;
    };
    const allowedNodes = nodes.filter(nodeAllowed);
    const allowedIds = new Set(allowedNodes.map((node) => node.id));
    const byLens = edges.filter((edge) => {
      if (hiddenEdgeKinds.has(edge.kind)) return false;
      if (lens === "structure") return edge.kind === "contains";
      if (lens === "dependencies") return edge.kind !== "contains";
      const source = nodes.find((node) => node.id === edge.sourceId);
      const target = nodes.find((node) => node.id === edge.targetId);
      return edge.risk || source?.state === "hotspot" || target?.state === "hotspot";
    });
    const lensNodeIds = new Set(
      byLens.flatMap((edge) => [edge.sourceId, edge.targetId]),
    );
    if (lens === "risk") {
      nodes
        .filter((node) => node.state === "hotspot")
        .forEach((node) => lensNodeIds.add(node.id));
    }
    if (selected) lensNodeIds.add(selected.id);
    const shouldBoundNodes =
      lens === "risk" || (lens === "dependencies" && byLens.length > 0);
    const visibleNodes = allowedNodes.filter(
      (node) => !shouldBoundNodes || lensNodeIds.has(node.id),
    );
    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    return {
      nodes: visibleNodes,
      edges: byLens.filter(
        (edge) =>
          allowedIds.has(edge.sourceId) &&
          allowedIds.has(edge.targetId) &&
          visibleIds.has(edge.sourceId) &&
          visibleIds.has(edge.targetId),
      ),
    };
  }, [edges, hiddenEdgeKinds, hideTests, lens, nodes, publicOnly, selected]);
  /**
   * What this map is *of*, written down as one string.
   *
   * `visibleGraph` is a fresh object on every selection, because the filters above keep the
   * selected node visible even when `hideTests`, `publicOnly` or the lens would drop it — so
   * `selected` has to be a dependency, and object identity cannot answer "is this the same
   * graph?". Almost always it is: clicking a card that was already on screen changes nothing
   * about which cards are on screen. Keying the placement on identity therefore re-laid out
   * the whole graph on every click, and every one of those re-layouts moved the camera.
   *
   * So the question is asked of the content instead: the lens, and the sorted ids of the
   * visible nodes and edges. Kind and state ride along with each node id because both feed
   * the placement — `kindLevel` reads the kind, and the risk lens clusters around hotspots —
   * and a signature that ignored them would hold a stale map after a review re-judges a node.
   */
  const graphSignature = useMemo(
    () =>
      [
        lens,
        visibleGraph.nodes
          .map((node) => `${node.id}:${node.kind}:${node.state}`)
          .sort()
          .join(","),
        visibleGraph.edges.map((edge) => edge.id).sort().join(","),
      ].join("|"),
    [lens, visibleGraph],
  );
  /**
   * Where the cards go, in two stages.
   *
   * The hand-rolled placement runs synchronously so the map is on screen in the same frame
   * the graph is: a canvas that appears empty while a layout engine loads reads as a canvas
   * with nothing on it. The layout kernel then places the same graph properly — it untangles
   * dense graphs the relaxation pass leaves overlapping — and the map swaps to its answer
   * when it arrives. If it never arrives, the first placement is a real map, not a spinner.
   *
   * Both stages are keyed on the signature rather than on `visibleGraph` itself. The
   * synchronous pass is O(n²) in the relaxation and the collision sweeps, so a selection that
   * cannot change where anything goes should not pay for it — and, more to the point, should
   * not hand the viewport a new layout object to react to.
   */
  const initialLayout = useMemo(
    () => layoutAtlas(visibleGraph.nodes, visibleGraph.edges, lens),
    // The signature is what the placement is about; `visibleGraph` is a new object per click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphSignature],
  );
  const [placedLayout, setPlacedLayout] = useState<AtlasLayout | null>(null);
  useEffect(() => {
    let current = true;
    // The graph on screen is no longer the one the pending placement is about.
    setPlacedLayout(null);
    layoutAtlasElk(visibleGraph.nodes, visibleGraph.edges, lens)
      .then((next) => {
        if (current) setPlacedLayout(next);
      })
      .catch(reportLayoutFailure);
    return () => {
      current = false;
    };
    // Same reasoning as the synchronous pass above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphSignature]);
  const layout = placedLayout ?? initialLayout;
  const { positions } = layout;
  const highlightedNodes = new Set(highlightedNodeIds);
  const highlightedEdges = new Set(highlightedEdgeIds);
  const [pulse, setPulse] = useState<AtlasPulse>("comet");
  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [showMinimap, setShowMinimap] = useState(true);
  const [viewport, setViewport] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const canvasRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const nodeRefs = useRef(new Map<string, SVGGElement>());
  const drag = useRef<{
    pointerId: number;
    x: number;
    y: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  const activePointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{
    distance: number;
    zoom: number;
    worldX: number;
    worldY: number;
  } | null>(null);
  const suppressNodeClick = useRef(false);
  /** The node the last canvas click selected, so the centring effect can leave it alone. */
  const clickedNodeId = useRef<string | null>(null);
  /**
   * Whether the reader has placed the camera themselves since this graph appeared.
   *
   * Until they have, the map is still showing whatever the fit control chose, and re-fitting
   * when the kernel's placement lands is an improvement on it. Once they have panned, zoomed
   * or jumped through the minimap, the frame on screen is a decision, and re-fitting over it
   * would throw away the thing they were looking at. Cleared whenever the graph itself
   * changes, because a frame chosen for one graph says nothing about the next one.
   */
  const userMoved = useRef(false);
  /** The graph the camera was last fitted to, so a second fit is asked for deliberately. */
  const fittedSignature = useRef<string | null>(null);
  /** The world point under the middle of the viewport, kept so a re-placement can restore it. */
  const viewCentre = useRef<{ x: number; y: number } | null>(null);
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

  const setViewportZoom = (
    requested: number,
    anchor?: { clientX: number; clientY: number },
  ) => {
    const next = clamp(requested, MIN_ZOOM, MAX_ZOOM);
    const canvas = canvasRef.current;
    if (!canvas || next === zoom) return;
    const bounds = canvas.getBoundingClientRect();
    const anchorX = anchor ? anchor.clientX - bounds.left : canvas.clientWidth / 2;
    const anchorY = anchor ? anchor.clientY - bounds.top : canvas.clientHeight / 2;
    const worldX = (canvas.scrollLeft + anchorX) / zoom;
    const worldY = (canvas.scrollTop + anchorY) / zoom;
    userMoved.current = true;
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: worldX * next - anchorX,
        top: worldY * next - anchorY,
      });
    });
  };

  const updateViewport = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    viewCentre.current = {
      x: (canvas.scrollLeft + canvas.clientWidth / 2) / zoom,
      y: (canvas.scrollTop + canvas.clientHeight / 2) / zoom,
    };
    setViewport({
      x: canvas.scrollLeft / zoom,
      y: canvas.scrollTop / zoom,
      width: canvas.clientWidth / zoom,
      height: canvas.clientHeight / zoom,
    });
  };

  /**
   * Put the middle of the viewport back over the world point it was over.
   *
   * Used when the same graph is re-placed under a camera the reader has already set: the
   * cards move, so nothing can be truly preserved, but holding the centre still keeps the
   * region they were reading in front of them instead of snapping them back to the whole map.
   */
  const restoreViewCentre = () => {
    const canvas = canvasRef.current;
    const centre = viewCentre.current;
    if (!canvas || !centre || typeof canvas.scrollTo !== "function") return;
    canvas.scrollTo({
      left: Math.max(0, centre.x * zoom - canvas.clientWidth / 2),
      top: Math.max(0, centre.y * zoom - canvas.clientHeight / 2),
    });
  };

  const fitGraph = () => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.clientWidth || !canvas.clientHeight) return;
    const next = clamp(
      Math.min(
        (canvas.clientWidth - 24) / layout.width,
        (canvas.clientHeight - 24) / layout.height,
      ),
      MIN_ZOOM,
      1.15,
    );
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: Math.max(0, (layout.width * next - canvas.clientWidth) / 2),
        top: Math.max(0, (layout.height * next - canvas.clientHeight) / 2),
      });
    });
  };

  const toggleFullscreen = async () => {
    const panel = panelRef.current;
    if (!panel) return;
    if (fullscreen) {
      if (document.fullscreenElement === panel && document.exitFullscreen) {
        await document.exitFullscreen();
      }
      setFullscreen(false);
      return;
    }
    setFullscreen(true);
    if (panel.requestFullscreen) {
      try {
        await panel.requestFullscreen();
      } catch {
        // The fixed viewport fallback still provides a full-workspace canvas.
      }
    }
  };

  /**
   * When the camera is allowed to move on its own, and when it must not.
   *
   * A different graph is a different map, and the reader has no frame on it yet, so it is
   * fitted. The same graph re-placed — the kernel's answer arriving over the synchronous
   * first draft — is the same map drawn better, and fitting it again would yank the view out
   * from under someone mid-read. So that case refits only while the camera is still the one
   * the fit chose; after the reader has moved it, the centre is held instead.
   *
   * Selecting a node reaches none of this: it no longer produces a new placement at all.
   */
  useEffect(() => {
    if (fittedSignature.current !== graphSignature) {
      fittedSignature.current = graphSignature;
      userMoved.current = false;
      fitGraph();
      return;
    }
    if (userMoved.current) restoreViewCentre();
    else fitGraph();
    // Refit only when the graph changes, or when its placement lands with new bounds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphSignature, layout.height, layout.width]);

  useEffect(() => {
    if (highlightedEdgeIds.length) setLens("dependencies");
  }, [highlightedEdgeIds]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      if (document.fullscreenElement) {
        setFullscreen(document.fullscreenElement === panelRef.current);
      } else {
        setFullscreen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.fullscreenElement) {
        setFullscreen(false);
      }
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    if (!fullscreen) return;
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(fitGraph);
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
    // Refit after fullscreen CSS has consumed the viewport.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullscreen]);

  useEffect(() => {
    window.requestAnimationFrame(updateViewport);
    // Viewport dimensions depend on both zoom and graph bounds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.height, layout.width, zoom]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleAtlasWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        // Trackpad pinch gestures arrive as a modified wheel event. Scoping the
        // non-passive listener to the canvas prevents browser zoom only here.
        event.preventDefault();
        const next = zoom * Math.exp(-event.deltaY * .006);
        setViewportZoom(next, { clientX: event.clientX, clientY: event.clientY });
        return;
      }
      if (event.shiftKey && event.deltaY) {
        event.preventDefault();
        canvas.scrollLeft += event.deltaY;
      }
    };
    canvas.addEventListener("wheel", handleAtlasWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleAtlasWheel);
    // The listener needs the latest zoom as its gesture baseline.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  useEffect(() => {
    if (!selected) return;
    // A node clicked on the canvas is already under the pointer, so centring it would drag
    // the graph out from under the click that asked for it. Every other route to a
    // selection — search, keyboard, the detail panel, a link into the page — can land on a
    // node that is nowhere in view, and those still centre.
    if (clickedNodeId.current === selected.id) return;
    const canvas = canvasRef.current;
    const position = positions.get(selected.id);
    if (!canvas || !position || typeof canvas.scrollTo !== "function") return;
    canvas.scrollTo({
      left: Math.max(
        0,
        (position.x + NODE_WIDTH / 2) * zoom - canvas.clientWidth / 2,
      ),
      top: Math.max(
        0,
        (position.y + NODE_HEIGHT / 2) * zoom - canvas.clientHeight / 2,
      ),
      behavior: "smooth",
    });
  }, [positions, selected, zoom]);

  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    // Nodes stop this event, so reaching here means the canvas itself was grabbed. Once the
    // reader has moved the graph, the selected node is no longer where they left it, and
    // asking for it again should bring it back into view.
    clickedNodeId.current = null;
    userMoved.current = true;
    const canvas = event.currentTarget;
    activePointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    canvas.setPointerCapture?.(event.pointerId);
    if (activePointers.current.size === 2) {
      const [first, second] = [...activePointers.current.values()];
      const bounds = canvas.getBoundingClientRect();
      const centerX = (first.x + second.x) / 2 - bounds.left;
      const centerY = (first.y + second.y) / 2 - bounds.top;
      pinch.current = {
        distance: pointerDistance(first, second),
        zoom,
        worldX: (canvas.scrollLeft + centerX) / zoom,
        worldY: (canvas.scrollTop + centerY) / zoom,
      };
      drag.current = null;
      suppressNodeClick.current = true;
      setPanning(false);
      return;
    }
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    suppressNodeClick.current = false;
    setPanning(true);
  };

  const pan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (activePointers.current.has(event.pointerId)) {
      activePointers.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
    }
    if (pinch.current && activePointers.current.size >= 2) {
      event.preventDefault();
      const canvas = event.currentTarget;
      const [first, second] = [...activePointers.current.values()];
      const bounds = canvas.getBoundingClientRect();
      const centerX = (first.x + second.x) / 2 - bounds.left;
      const centerY = (first.y + second.y) / 2 - bounds.top;
      const next = clamp(
        pinch.current.zoom *
          (pointerDistance(first, second) / Math.max(1, pinch.current.distance)),
        MIN_ZOOM,
        MAX_ZOOM,
      );
      userMoved.current = true;
      setZoom(next);
      canvas.scrollLeft = pinch.current.worldX * next - centerX;
      canvas.scrollTop = pinch.current.worldY * next - centerY;
      suppressNodeClick.current = true;
      return;
    }
    const start = drag.current;
    if (!start || start.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) {
      suppressNodeClick.current = true;
    }
    event.currentTarget.scrollLeft = start.scrollLeft - deltaX;
    event.currentTarget.scrollTop = start.scrollTop - deltaY;
  };

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    activePointers.current.delete(event.pointerId);
    if (activePointers.current.size < 2) pinch.current = null;
    if (drag.current?.pointerId === event.pointerId) {
      drag.current = null;
      setPanning(false);
    }
  };

  const selectNode = (nodeId: string) => {
    if (suppressNodeClick.current) {
      suppressNodeClick.current = false;
      return;
    }
    clickedNodeId.current = nodeId;
    onSelectNode(nodeId);
  };

  const deselectBackground = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (suppressNodeClick.current) {
      suppressNodeClick.current = false;
      return;
    }
    const target = event.target;
    if (target instanceof Element && target.closest("[data-atlas-node-id]")) {
      return;
    }
    onSelectNode(null);
  };

  const navigateNode = (
    nodeId: string,
    key: "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Home" | "End",
  ) => {
    const sorted = [...visibleGraph.nodes].sort((left, right) => {
      const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
      const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
      return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x;
    });
    let next: AtlasNodeView | undefined;
    if (key === "Home") next = sorted[0];
    else if (key === "End") next = sorted.at(-1);
    else {
      const relatedIds = visibleGraph.edges
        .filter((edge) =>
          key === "ArrowDown" || key === "ArrowRight"
            ? edge.sourceId === nodeId
            : edge.targetId === nodeId,
        )
        .map((edge) =>
          edge.sourceId === nodeId ? edge.targetId : edge.sourceId,
        );
      const current = positions.get(nodeId) || { x: 0, y: 0 };
      next = sorted
        .filter((node) => node.id !== nodeId)
        .filter((node) => {
          const position = positions.get(node.id) || { x: 0, y: 0 };
          if (key === "ArrowDown") return position.y > current.y;
          if (key === "ArrowUp") return position.y < current.y;
          if (key === "ArrowRight") return position.x > current.x;
          return position.x < current.x;
        })
        .sort((left, right) => {
          const relatedDifference =
            Number(relatedIds.includes(right.id)) - Number(relatedIds.includes(left.id));
          if (relatedDifference) return relatedDifference;
          const leftPosition = positions.get(left.id) || { x: 0, y: 0 };
          const rightPosition = positions.get(right.id) || { x: 0, y: 0 };
          return (
            distance(current, leftPosition) - distance(current, rightPosition)
          );
        })[0];
    }
    if (!next) return;
    onSelectNode(next.id);
    window.requestAnimationFrame(() => nodeRefs.current.get(next!.id)?.focus());
  };

  /**
   * The relationships a pulse is drawn along: the selected node's own, and no others.
   *
   * An edge already carrying the dependency-path highlight is left out rather than drawn
   * twice. That highlight is a different claim — it traces a route the reader asked for,
   * and `query_service` walks edges in both directions to find one, so a pulse following
   * each edge's own arrow would zigzag along a path that reads as a single journey.
   */
  const pulseEdges =
    selected && pulse !== "none" && pulse !== "breathe"
      ? visibleGraph.edges.filter(
          (edge) =>
            edge.sourceId !== edge.targetId &&
            !highlightedEdges.has(edge.id) &&
            (edge.sourceId === selected.id || edge.targetId === selected.id),
        )
      : [];

  /**
   * What gets lifted out of the ordinary paint order, and why there is an order at all.
   *
   * SVG has no `z-index`: whatever is written last sits on top. On a dense graph that
   * buries the selected card under whichever neighbour happens to come later in
   * `visibleGraph.nodes`, and runs its connectors behind cards they ought to cross. So
   * the selection paints last, its neighbours just beneath it, and the edges joining
   * them above the rest of the mesh. A traced dependency path makes the same kind of
   * claim on the reader's attention, so it rides along in both tiers.
   *
   * With nothing selected and no path traced every test below is false, and the graph
   * falls back to its plain order: every edge, then every node.
   */
  const isRaisedEdge = (edge: AtlasEdgeView) =>
    edge.sourceId === selected?.id ||
    edge.targetId === selected?.id ||
    highlightedEdges.has(edge.id);
  const selectedNeighbours = new Set(
    selected
      ? visibleGraph.edges
          .filter(
            (edge) => edge.sourceId === selected.id || edge.targetId === selected.id,
          )
          .map((edge) =>
            edge.sourceId === selected.id ? edge.targetId : edge.sourceId,
          )
      : [],
  );
  const isRaisedNode = (node: AtlasNodeView) =>
    node.id !== selected?.id &&
    (selectedNeighbours.has(node.id) || highlightedNodes.has(node.id));

  const renderEdge = (edge: AtlasEdgeView) => {
    const source = positions.get(edge.sourceId);
    const target = positions.get(edge.targetId);
    if (!source || !target || edge.sourceId === edge.targetId) return null;
    const connected = edge.sourceId === selected?.id || edge.targetId === selected?.id;
    return (
      <path
        key={edge.id}
        className={`atlas-edge ${
          connected ? "atlas-edge--active" : "atlas-edge--muted"
        } ${edge.risk ? "atlas-edge--risk" : ""} ${
          (edge.confidence ?? 0) >= .9 ? "atlas-edge--strong" : ""
        } atlas-edge--kind-${edgeKindClass(edge.kind)} ${
          highlightedEdges.has(edge.id) ? "atlas-edge--path" : ""
        }`}
        d={edgePath(source, target)}
        markerEnd={`url(#${arrowId})`}
      />
    );
  };

  const renderNode = (node: AtlasNodeView) => {
    const position = positions.get(node.id);
    if (!position) return null;
    const active = node.id === selected?.id;
    return (
      <g
        key={node.id}
        ref={(element) => {
          if (element) nodeRefs.current.set(node.id, element);
          else nodeRefs.current.delete(node.id);
        }}
        data-atlas-node-id={node.id}
        role="button"
        tabIndex={active ? 0 : -1}
        aria-pressed={active}
        aria-label={`${node.label}, ${node.kind}, ${node.state}`}
        className={`atlas-node atlas-node--${node.state} ${active ? "atlas-node--active" : ""} ${
          highlightedNodes.has(node.id) ? "atlas-node--path" : ""
        }`}
        transform={`translate(${position.x} ${position.y})`}
        onPointerDown={(event) => {
          // Keep node activation separate from the canvas pan
          // gesture, which captures pointers at the viewport.
          event.stopPropagation();
          suppressNodeClick.current = false;
        }}
        onClick={(event) => {
          event.stopPropagation();
          selectNode(node.id);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelectNode(node.id);
          } else if (
            event.key === "ArrowUp" ||
            event.key === "ArrowDown" ||
            event.key === "ArrowLeft" ||
            event.key === "ArrowRight" ||
            event.key === "Home" ||
            event.key === "End"
          ) {
            event.preventDefault();
            navigateNode(node.id, event.key);
          }
        }}
      >
        <rect className="atlas-node__body" width={NODE_WIDTH} height={NODE_HEIGHT} rx="10" />
        {/* The ring ripple sends outward. Invisible in every other mode, and
            rendered only for the selected node so nothing else can ring. */}
        {active && (
          <rect
            className="atlas-node__halo"
            width={NODE_WIDTH}
            height={NODE_HEIGHT}
            rx="10"
          />
        )}
        <circle className="atlas-node__kind" cx="24" cy="25" r="10" />
        <text className="atlas-node__symbol" x="24" y="29" textAnchor="middle">
          {node.state === "hotspot"
            ? "!"
            : node.state === "contained" || node.state === "cleared"
              ? "✓"
              : "·"}
        </text>
        <text className="atlas-node__label" x="43" y="29">
          {truncate(node.label, 20)}
        </text>
        <text className="atlas-node__meta" x="18" y="59">
          {truncate(node.kind.replaceAll("_", " "), 20)}
        </text>
        {/* A ternary rather than `&&`: a node carrying no signal has a count of
            zero, and `0 &&` renders the zero as the node's own caption. */}
        {node.signalCount || node.evidenceCount ? (
          <text className="atlas-node__metric" x={NODE_WIDTH - 16} y="59" textAnchor="end">
            {node.signalCount ? `${node.signalCount} signals` : `${node.evidenceCount} refs`}
          </text>
        ) : null}
      </g>
    );
  };

  return (
    <section
      ref={panelRef}
      className={`atlas-panel ${fullscreen ? "atlas-panel--fullscreen" : ""}`}
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

      <div className="atlas-explorer" aria-label="Atlas exploration controls">
        <form className="atlas-search" role="search" onSubmit={submitSearch}>
          <Search size={14} />
          <input
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            placeholder="Find a module, class, or path"
            aria-label="Search repository atlas"
          />
          <button type="submit">Find</button>
        </form>
        <div className="atlas-lenses" role="group" aria-label="Graph lens">
          {(["structure", "dependencies", "risk"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={lens === value ? "active" : ""}
              aria-pressed={lens === value}
              onClick={() => setLens(value)}
            >
              {humanizeLabel(value)}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`atlas-filter-toggle ${hideTests ? "active" : ""}`}
          aria-pressed={hideTests}
          onClick={() => setHideTests((value) => !value)}
        >
          Hide tests
        </button>
        <button
          type="button"
          className={`atlas-filter-toggle ${publicOnly ? "active" : ""}`}
          aria-pressed={publicOnly}
          onClick={() => setPublicOnly((value) => !value)}
        >
          Public only
        </button>
        {/* A select rather than a fifth row of pill buttons. The lens changes which graph is
            on screen and earns its width; this only changes how the selected node's
            neighbourhood moves, and a control that is set once should not out-shout one that
            is pressed constantly. */}
        <label className="atlas-pulse-select">
          <span>Highlight</span>
          <select
            value={pulse}
            aria-label="Highlight motion for the selected node"
            onChange={(event) => setPulse(event.target.value as AtlasPulse)}
          >
            {PULSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {lens === "risk" && onExploreAtlas && (
          <>
            <button
              type="button"
              className="atlas-filter-toggle"
              disabled={loading}
              onClick={() => onExploreAtlas("signals")}
            >
              Surface signals
            </button>
            <button
              type="button"
              className="atlas-filter-toggle"
              disabled={loading}
              onClick={() => onExploreAtlas("cycles")}
            >
              Surface cycles
            </button>
          </>
        )}
      </div>

      <div className="atlas-toolbar">
        <div className="atlas-legend" aria-label="Atlas legend">
          {legend.map(({ state, label, Icon }) => (
            <span key={state} className={`atlas-legend__key atlas-legend__key--${state}`}>
              <Icon size={13} /> {label}
            </span>
          ))}
        </div>
        {availableEdgeKinds.length > 0 && (
          <div className="atlas-edge-filters" aria-label="Relationship filters">
            {availableEdgeKinds.map((kind) => (
              <button
                key={kind}
                type="button"
                className={hiddenEdgeKinds.has(kind) ? "" : "active"}
                aria-pressed={!hiddenEdgeKinds.has(kind)}
                onClick={() => toggleEdgeKind(kind)}
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
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setViewportZoom(zoom - ZOOM_STEP)}
          >
            <Minus size={14} />
          </button>
          <output aria-live="polite" aria-label="Current graph zoom">
            {Math.round(zoom * 100)}%
          </output>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setViewportZoom(zoom + ZOOM_STEP)}
          >
            <Plus size={14} />
          </button>
          <button type="button" aria-label="Fit graph to view" onClick={fitGraph}>
            <Scan size={14} />
          </button>
          <button
            type="button"
            aria-label={fullscreen ? "Exit full screen" : "Enter full screen"}
            aria-pressed={fullscreen}
            onClick={() => void toggleFullscreen()}
          >
            {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            type="button"
            aria-label={showMinimap ? "Hide graph minimap" : "Show graph minimap"}
            aria-pressed={showMinimap}
            onClick={() => setShowMinimap((value) => !value)}
          >
            <MapIcon size={14} />
          </button>
        </div>
      </div>

      <div className="atlas-layout">
        <div className="atlas-viewport">
          <div
            ref={canvasRef}
            className={`atlas-canvas ${panning ? "atlas-canvas--panning" : ""}`}
            role="region"
            tabIndex={0}
            aria-label="Scrollable graph viewport"
            aria-describedby={instructionsId}
            aria-busy={loading}
            onPointerDown={beginPan}
            onPointerMove={pan}
            onPointerUp={endPan}
            onPointerCancel={endPan}
            onScroll={updateViewport}
            onClick={deselectBackground}
          >
            {visibleGraph.nodes.length ? (
            <svg
              role="group"
              aria-label={mode === "repository" ? "Repository node graph" : "Greenfield architecture graph"}
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              width={layout.width * zoom}
              height={layout.height * zoom}
              style={{
                width: `${layout.width * zoom}px`,
                height: `${layout.height * zoom}px`,
              }}
              preserveAspectRatio="xMinYMin meet"
              data-pulse={pulse}
            >
              <defs>
                <pattern id={gridId} width="24" height="24" patternUnits="userSpaceOnUse">
                  <path className="atlas-grid-line" d="M 24 0 L 0 0 0 24" fill="none" />
                </pattern>
                <marker
                  id={arrowId}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path className="atlas-arrow" d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              <rect className="atlas-canvas__background" width="100%" height="100%" />
              <rect fill={`url(#${gridId})`} width="100%" height="100%" />
              <g className="atlas-clusters" aria-hidden="true">
                {layout.clusters.map((cluster) => (
                  <g key={cluster.id}>
                    <rect
                      x={cluster.x}
                      y={cluster.y}
                      width={cluster.width}
                      height={cluster.height}
                      rx="22"
                    />
                    <text x={cluster.x + 16} y={cluster.y + 21}>
                      {truncate(cluster.label, 34)} · {cluster.nodeIds.length}
                    </text>
                  </g>
                ))}
              </g>
              {/* The mesh the selection is not part of, under the cards it is not part of. */}
              <g aria-hidden="true">
                {visibleGraph.edges.filter((edge) => !isRaisedEdge(edge)).map(renderEdge)}
              </g>
              {visibleGraph.nodes
                .filter((node) => node.id !== selected?.id && !isRaisedNode(node))
                .map(renderNode)}
              {/* The selected node's own connectors, lifted clear of the cards they cross. */}
              <g aria-hidden="true">
                {visibleGraph.edges.filter(isRaisedEdge).map(renderEdge)}
              </g>
              {/* Drawn over every edge and under every node, and never onto the edge itself:
                  `--kind-tests`, `--kind-configures` and `--risk` already own
                  `stroke-dasharray`, and a pulse written into `.atlas-edge` would quietly
                  erase the distinction those dashes carry. */}
              <g aria-hidden="true">
                {pulseEdges.map((edge, rank) => {
                  const source = positions.get(edge.sourceId);
                  const target = positions.get(edge.targetId);
                  if (!source || !target) return null;
                  return (
                    <path
                      key={edge.id}
                      className={`atlas-pulse ${
                        edge.targetId === selected?.id ? "atlas-pulse--incoming" : ""
                      }`}
                      d={edgePath(source, target)}
                      /* Normalised, so the dash means the same fraction of a long edge and
                         a short one and the whole neighbourhood pulses at one speed. */
                      pathLength={100}
                      style={{ "--atlas-pulse-rank": rank } as CSSProperties}
                    />
                  );
                })}
              </g>
              {/* Neighbours over the crowd, and the selection itself over everything —
                  the card the reader just asked about should never sit under another. */}
              {visibleGraph.nodes.filter(isRaisedNode).map(renderNode)}
              {visibleGraph.nodes
                .filter((node) => node.id === selected?.id)
                .map(renderNode)}
            </svg>
            ) : (
              <div className="atlas-empty">
                <Boxes size={28} />
                <strong>{loading ? "Mapping bounded evidence…" : emptyMessage}</strong>
              </div>
            )}
          </div>
          {showMinimap && visibleGraph.nodes.length > 1 && (
            <button
              type="button"
              className="atlas-minimap"
              aria-label="Graph minimap; click to recenter"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                const canvas = canvasRef.current;
                if (!canvas) return;
                userMoved.current = true;
                const bounds = event.currentTarget.getBoundingClientRect();
                const worldX =
                  ((event.clientX - bounds.left) / bounds.width) * layout.width;
                const worldY =
                  ((event.clientY - bounds.top) / bounds.height) * layout.height;
                canvas.scrollTo({
                  left: Math.max(0, worldX * zoom - canvas.clientWidth / 2),
                  top: Math.max(0, worldY * zoom - canvas.clientHeight / 2),
                });
              }}
            >
              <svg viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
                {visibleGraph.edges.map((edge) => {
                  const source = positions.get(edge.sourceId);
                  const target = positions.get(edge.targetId);
                  if (!source || !target) return null;
                  return (
                    <line
                      key={edge.id}
                      x1={source.x + NODE_WIDTH / 2}
                      y1={source.y + NODE_HEIGHT / 2}
                      x2={target.x + NODE_WIDTH / 2}
                      y2={target.y + NODE_HEIGHT / 2}
                    />
                  );
                })}
                {visibleGraph.nodes.map((node) => {
                  const position = positions.get(node.id);
                  if (!position) return null;
                  return (
                    <rect
                      key={node.id}
                      className={node.id === selected?.id ? "active" : ""}
                      x={position.x}
                      y={position.y}
                      width={NODE_WIDTH}
                      height={NODE_HEIGHT}
                      rx="8"
                    />
                  );
                })}
                <rect
                  className="atlas-minimap__viewport"
                  x={viewport.x}
                  y={viewport.y}
                  width={Math.min(layout.width, viewport.width)}
                  height={Math.min(layout.height, viewport.height)}
                />
              </svg>
            </button>
          )}
        </div>

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

      {selected && (
        <div className="atlas-metric-strip" aria-label={`Metrics for ${selected.label}`}>
          {(selected.metrics.length
            ? selected.metrics.slice(0, 5)
            : [{ label: "Evidence references", value: selected.evidenceCount || 0 }]
          ).map((metric) => (
            <div key={`${metric.group}-${metric.label}`}>
              <span>{metric.group || "Metric"}</span>
              <strong>{metric.value}</strong>
              <small
                title={[
                  metric.definition,
                  metric.limitations,
                  metric.scope
                    ? `Scope: ${metric.scope.replaceAll("_", " ")}`
                    : "",
                ].filter(Boolean).join(" · ")}
              >
                {metric.label}
              </small>
            </div>
          ))}
        </div>
      )}
      <p className="atlas-visible-count" aria-live="polite">
        Showing {visibleGraph.nodes.length} of {nodes.length} surfaced nodes and{" "}
        {visibleGraph.edges.length} of {edges.length} relationships in the {lens} lens.
      </p>
    </section>
  );
}

function AtlasDetailPanel({
  node,
  edges,
  nodes,
  onSelectNode,
  onOpenFinding,
  onExploreNode,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  loading,
}: {
  node?: AtlasNodeView;
  edges: AtlasEdgeView[];
  nodes: AtlasNodeView[];
  onSelectNode: (nodeId: string) => void;
  onOpenFinding?: RepositoryAtlasProps["onOpenFinding"];
  onExploreNode?: RepositoryAtlasProps["onExploreNode"];
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  loading?: boolean;
}) {
  if (!node) {
    return (
      <aside className="atlas-detail">
        <p className="muted">Select a node to inspect its stored structure and metrics.</p>
      </aside>
    );
  }
  const relationships = edges.filter(
    (edge) => edge.sourceId === node.id || edge.targetId === node.id,
  );
  const outgoing = relationships.filter((edge) => edge.sourceId === node.id);
  const incoming = relationships.filter((edge) => edge.targetId === node.id);
  const byId = new Map(nodes.map((item) => [item.id, item]));
  const StateIcon = STATE_ICON[node.state];

  return (
    <aside className="atlas-detail" aria-live="polite">
      <div className="atlas-detail__title">
        <span className={`atlas-state atlas-state--${node.state}`}><StateIcon size={15} /></span>
        <div>
          <span className="eyebrow">Selected node</span>
          <h3>{node.label}</h3>
        </div>
      </div>
      <code className="mono-path">{node.path}</code>
      <div className="atlas-detail__tags">
        <Badge variant={node.state === "hotspot" ? "material" : "neutral"}>{node.kind}</Badge>
        <Badge
          variant={
            node.state === "contained" || node.state === "cleared" ? "cleared" : "neutral"
          }
        >
          {node.state}
        </Badge>
      </div>
      {node.description && <p>{node.description}</p>}
      {/* The other half of the link a finding already offers into the map. A reader who
          arrived here from the ledger can get back to the reasoning, and one who found the
          node on the canvas can reach the verdict that was written about it — the question and
          its answer in one reading (workspace-design §4). Only where a review judged this
          node: the map draws plenty that no finding is about. */}
      {onOpenFinding && node.hasFinding && (
        <div className="atlas-detail__section atlas-detail__finding">
          <button type="button" onClick={() => onOpenFinding(node.id)}>
            Go to finding
          </button>
        </div>
      )}
      {node.signals && node.signals.length > 0 && (
        <div className="atlas-detail__section">
          <strong><AlertTriangle size={13} /> Structural signals</strong>
          <ul className="evidence-list">
            {node.signals.map((signal, index) => (
              <li key={`${signal.code}-${index}`}>
                <code>{signal.code.replaceAll("-", " ")}</code>
                <p>{signal.message}</p>
                {signal.definition && <small>{signal.definition}</small>}
                <small>
                  {signal.nature === "structural_proxy"
                    ? "Structural proxy"
                    : "Objective signal"}
                  {signal.limitations ? ` · ${signal.limitations}` : ""}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
      {onExploreNode && (
        <div className="atlas-detail__section atlas-detail__actions">
          <strong><Layers3 size={13} /> Explore from here</strong>
          <div>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "children")}>
              Children
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "dependencies")}>
              Dependencies
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "dependants")}>
              Dependants
            </button>
            <button type="button" disabled={loading} onClick={() => onExploreNode(node.id, "forward_neighbourhood", 2)}>
              2-hop view
            </button>
          </div>
        </div>
      )}
      {onSetPathStart && onTracePath && (
        <div className="atlas-detail__section atlas-detail__path">
          <strong><Route size={13} /> Dependency path</strong>
          {pathStartNodeId && pathStartNodeId !== node.id ? (
            <button type="button" disabled={loading} onClick={() => onTracePath(node.id)}>
              Trace from {byId.get(pathStartNodeId)?.label || "start"} to this node
            </button>
          ) : (
            <button type="button" disabled={loading} onClick={() => onSetPathStart(node.id)}>
              {pathStartNodeId === node.id ? "Path starts here" : "Use as path start"}
            </button>
          )}
        </div>
      )}
      <div className="atlas-detail__section">
        <strong><GitBranch size={13} /> Relationships</strong>
        <RelationshipGroup
          title="Outgoing"
          relationships={outgoing}
          nodeId={node.id}
          byId={byId}
          onSelectNode={onSelectNode}
        />
        <RelationshipGroup
          title="Incoming"
          relationships={incoming}
          nodeId={node.id}
          byId={byId}
          onSelectNode={onSelectNode}
        />
        {!relationships.length && <small>No surfaced relationship in this bounded view.</small>}
      </div>
    </aside>
  );
}

function RelationshipGroup({
  title,
  relationships,
  nodeId,
  byId,
  onSelectNode,
}: {
  title: string;
  relationships: AtlasEdgeView[];
  nodeId: string;
  byId: Map<string, AtlasNodeView>;
  onSelectNode: (nodeId: string) => void;
}) {
  if (!relationships.length) return null;
  return (
    <div className="atlas-relationship-group">
      <small>{title} · {relationships.length}</small>
      {relationships.slice(0, 6).map((edge) => {
        const otherId = edge.sourceId === nodeId ? edge.targetId : edge.sourceId;
        const other = byId.get(otherId);
        return (
          <button
            key={edge.id}
            type="button"
            disabled={!other}
            onClick={() => other && onSelectNode(other.id)}
          >
            <span>{edge.sourceId === nodeId ? "→" : "←"} {edge.kind}</span>
            <b>{other?.label || truncate(otherId, 18)}</b>
          </button>
        );
      })}
      {relationships.length > 6 && <small>+{relationships.length - 6} more surfaced relationships</small>}
    </div>
  );
}

/**
 * Once, however many maps are on the page and however often the lens changes: a kernel that
 * cannot load fails the same way every time, and a console repeating it says nothing new.
 */
let reportedLayoutFailure = false;

function reportLayoutFailure(error: unknown) {
  if (reportedLayoutFailure) return;
  reportedLayoutFailure = true;
  console.warn("Atlas graph layout unavailable; keeping the built-in placement.", error);
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function edgeKindClass(kind: string) {
  return kind.replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "").toLocaleLowerCase();
}

function pointerDistance(
  first: { x: number; y: number },
  second: { x: number; y: number },
) {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function edgePath(
  source: { x: number; y: number },
  target: { x: number; y: number },
) {
  const sourceCenterX = source.x + NODE_WIDTH / 2;
  const sourceCenterY = source.y + NODE_HEIGHT / 2;
  const targetCenterX = target.x + NODE_WIDTH / 2;
  const targetCenterY = target.y + NODE_HEIGHT / 2;
  const vertical = Math.abs(targetCenterY - sourceCenterY) >= NODE_HEIGHT;
  if (vertical) {
    const downward = targetCenterY > sourceCenterY;
    const startY = source.y + (downward ? NODE_HEIGHT : 0);
    const endY = target.y + (downward ? 0 : NODE_HEIGHT);
    const middleY = (startY + endY) / 2;
    return `M ${sourceCenterX} ${startY} C ${sourceCenterX} ${middleY}, ${targetCenterX} ${middleY}, ${targetCenterX} ${endY}`;
  }
  const rightward = targetCenterX > sourceCenterX;
  const startX = source.x + (rightward ? NODE_WIDTH : 0);
  const endX = target.x + (rightward ? 0 : NODE_WIDTH);
  const middleX = (startX + endX) / 2;
  return `M ${startX} ${sourceCenterY} C ${middleX} ${sourceCenterY}, ${middleX} ${targetCenterY}, ${endX} ${targetCenterY}`;
}

function distance(
  left: { x: number; y: number },
  right: { x: number; y: number },
) {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}
