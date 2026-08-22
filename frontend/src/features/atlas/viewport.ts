/**
 * The camera over the map: where it is pointed, how far in, and every gesture that moves it.
 *
 * All of it in one place because it is one decision — a pan, a pinch, a fit, a fullscreen
 * swap and the centring that follows a selection all write to the same scroll position, and
 * separating them would mean two owners for one viewport.
 */

import {
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { prefersReducedMotion } from "../../lib/motion";
import { MAX_ZOOM, MIN_ZOOM, READABLE_ZOOM, clamp, pointerDistance } from "./geometry";
import type { AtlasNodeView } from "./graph";
import { NODE_HEIGHT, NODE_WIDTH, type AtlasLayout } from "./layout";

export function useAtlasViewport({
  layout,
  graphSignature,
  selected,
  onSelectNode,
}: {
  layout: AtlasLayout;
  /** What the map is of. A new signature is a new map, and gets a new camera. */
  graphSignature: string;
  selected: AtlasNodeView | undefined;
  onSelectNode: (nodeId: string | null) => void;
}) {
  const { positions } = layout;
  const [zoom, setZoom] = useState(1);
  const [panning, setPanning] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [showMinimap, setShowMinimap] = useState(true);
  const [viewport, setViewport] = useState({ x: 0, y: 0, width: 0, height: 0 });
  /**
   * Whether the last automatic fit stopped at the readable floor rather than framing the graph.
   *
   * A fit that cannot fit is a fit that did something else, and the reader is looking at a
   * corner of a map they asked to see whole. The camera knows which of the two happened and
   * nothing else can work it out, so it says.
   */
  const [fitFloored, setFitFloored] = useState(false);
  /**
   * How big the canvas is, in CSS pixels.
   *
   * Tracked because the drawn surface has to be at least this big. A graph smaller than the
   * canvas used to paint its ground and its grid over its own bounds only, which left a hard
   * edge partway across an otherwise empty panel — the map appearing to stop rather than the
   * canvas continuing. `viewport` cannot answer it: it is in world units and is what the
   * world size would be derived from, which is a loop.
   */
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
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
    setCanvasSize({ width: canvas.clientWidth, height: canvas.clientHeight });
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

  /**
   * Frame the graph — but never below the scale at which a card stops being a card.
   *
   * A fit that answers a large graph by zooming to fifteen percent shows the reader every
   * card and none of their labels: a grey mesh that is technically the whole map. So the
   * automatic fit stops at `READABLE_ZOOM` and shows part of the graph at a size that can be
   * read, with the minimap saying where that part is. The zoom control still reaches
   * `MIN_ZOOM`, because asking to see the whole shape at once is a real question — it is just
   * not the one to answer before the reader has asked it.
   */
  const fitGraph = () => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.clientWidth || !canvas.clientHeight) return;
    const whole = Math.min(
      (canvas.clientWidth - 24) / layout.width,
      (canvas.clientHeight - 24) / layout.height,
    );
    const next = clamp(whole, READABLE_ZOOM, 1.15);
    setFitFloored(whole < READABLE_ZOOM);
    setZoom(next);
    window.requestAnimationFrame(() => {
      if (typeof canvas.scrollTo !== "function") return;
      canvas.scrollTo({
        left: Math.max(0, (layout.width * next - canvas.clientWidth) / 2),
        top: Math.max(0, (layout.height * next - canvas.clientHeight) / 2),
      });
    });
  };

  /** Point the camera at a world coordinate, which is what the minimap asks for. */
  const centreOn = (worldX: number, worldY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    userMoved.current = true;
    canvas.scrollTo({
      left: Math.max(0, worldX * zoom - canvas.clientWidth / 2),
      top: Math.max(0, worldY * zoom - canvas.clientHeight / 2),
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

  /**
   * The canvas can change size without the graph or the camera changing at all — the window
   * is resized, the panel goes fullscreen, the detail column appears at a breakpoint. Scroll
   * events do not fire for any of those, so the surface has to be measured when it moves.
   */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => updateViewport());
    observer.observe(canvas);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleAtlasWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        // Trackpad pinch gestures arrive as a modified wheel event. Scoping the
        // non-passive listener to the canvas prevents browser zoom only here.
        event.preventDefault();
        const next = zoom * Math.exp(-event.deltaY * 0.006);
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
      // A preference asked for once and honoured everywhere. The stylesheet collapses every
      // duration under `prefers-reduced-motion`, and a scroll animated from JavaScript walks
      // straight past that — this one on every arrow key, because `navigateNode` selects as it
      // moves, so a reader who asked for stillness got the map gliding under each keystroke.
      behavior: prefersReducedMotion() ? "auto" : "smooth",
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

  /** A node press is not a canvas grab: the card takes the gesture and the camera stays put. */
  const beginNodePress = () => {
    suppressNodeClick.current = false;
  };

  return {
    canvasRef,
    panelRef,
    nodeRefs,
    zoom,
    panning,
    fullscreen,
    showMinimap,
    setShowMinimap,
    viewport,
    canvasSize,
    fitFloored,
    setViewportZoom,
    fitGraph,
    centreOn,
    toggleFullscreen,
    updateViewport,
    beginPan,
    pan,
    endPan,
    selectNode,
    deselectBackground,
    beginNodePress,
  };
}

export type AtlasViewport = ReturnType<typeof useAtlasViewport>;
