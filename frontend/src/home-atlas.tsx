/**
 * The repository the front door's replay is judging, drawn as a map.
 *
 * Hand-laid rather than laid out: the workbench's atlas takes a real graph and solves for
 * positions, and seven modules whose whole job is to stand still under a replay do not need a
 * solver — they need to be in the same place on every paint, in both themes, at every width.
 * So the geometry is written down here and the vocabulary is borrowed whole from `atlas.tsx`:
 * the same node measurements, the same class names, the same tokens, the same grid pattern and
 * arrowhead. A node here and a node on a review page are the same drawing, and the day one of
 * them moves the other has to move with it.
 *
 * Decorative by construction. The ledger beside it is this section's text — it says which
 * boundary is under the model and how each came out — so the map carries `aria-hidden` and
 * announces nothing. A screen reader that read both would hear the run twice.
 *
 * The verdict is on the node. A boundary examined and cleared is drawn as cleared, never as an
 * ordinary node: the difference between "found to be earning its place" and "never looked at"
 * is the whole value of an exhaustive sweep, and a map that erased it would undo what the
 * review is for.
 */

const NODE_WIDTH = 190;
const NODE_HEIGHT = 78;

type NodeState = "normal" | "judging" | "hotspot" | "cleared";

/** Where each module sits, and which of the run's boundaries it holds. */
type Module = {
  label: string;
  x: number;
  y: number;
  /** The boundary's position in the run, or `null` for a module the detector surfaced none in. */
  boundary: number | null;
  meta: string;
};

const MODULES: Module[] = [
  { label: "orders/", x: 40, y: 56, boundary: 0, meta: "BR-001" },
  { label: "pricing/", x: 168, y: 230, boundary: 1, meta: "BR-002" },
  { label: "billing/", x: 422, y: 230, boundary: 2, meta: "BR-003" },
  { label: "notifications/", x: 422, y: 404, boundary: 3, meta: "BR-004" },
  { label: "catalog/", x: 40, y: 404, boundary: 4, meta: "BR-005" },
  { label: "checkout/", x: 295, y: 56, boundary: null, meta: "not surfaced" },
  { label: "invoicing/", x: 550, y: 56, boundary: null, meta: "not surfaced" },
];

/**
 * The relationships between them, by module index.
 *
 * Each path is written out rather than derived: `edgePath` in the workbench's atlas leaves a
 * node's bottom edge and arrives at another's top, and these are the eight curves that produced
 * — every one of them a bottom-to-top cubic through the midline between the two rows.
 */
type Edge = { from: number; to: number; kind: "imports" | "calls"; d: string };

const EDGES: Edge[] = [
  { from: 0, to: 1, kind: "imports", d: "M 135 134 C 135 182, 263 182, 263 230" },
  { from: 5, to: 1, kind: "imports", d: "M 390 134 C 390 182, 263 182, 263 230" },
  { from: 6, to: 1, kind: "imports", d: "M 645 134 C 645 182, 263 182, 263 230" },
  { from: 5, to: 2, kind: "imports", d: "M 390 134 C 390 182, 517 182, 517 230" },
  { from: 6, to: 2, kind: "calls", d: "M 645 134 C 645 182, 517 182, 517 230" },
  { from: 0, to: 4, kind: "imports", d: "M 135 134 C 135 269, 135 269, 135 404" },
  { from: 2, to: 3, kind: "calls", d: "M 517 308 C 517 356, 517 356, 517 404" },
  { from: 0, to: 2, kind: "calls", d: "M 135 134 C 135 182, 517 182, 517 230" },
];

const SYMBOL: Record<NodeState, string> = {
  hotspot: "!",
  cleared: "✓",
  judging: "·",
  normal: "·",
};

/** What the four states are called, as a miniature of the node each one names. */
const LEGEND: { state: string; label: string }[] = [
  { state: "hotspot", label: "Should change" },
  { state: "cleared", label: "Left as it is" },
  { state: "judging", label: "Under the model now" },
  { state: "", label: "Not yet judged" },
];

/**
 * A boundary's state on the map, from the one counter the ledger beside it reads.
 *
 * Behind the count is decided, at the count is under the model, ahead of it has not been
 * looked at. A module holding no boundary is never any of those.
 */
function stateOf(boundary: number | null, judged: number, material: boolean[]): NodeState {
  if (boundary === null || boundary > judged) return "normal";
  if (boundary === judged) return "judging";
  return material[boundary] ? "hotspot" : "cleared";
}

export function HomeAtlas({
  judged,
  /** Whether each boundary came out material, in the run's own order. */
  material,
  /** What each boundary's verdict cited, as `borne/presented`, once it has landed. */
  bearings,
}: {
  judged: number;
  material: boolean[];
  bearings: string[];
}) {
  const states = MODULES.map((module) => stateOf(module.boundary, judged, material));

  return (
    <div className="atlas-panel home-atlas">
      <div className="atlas-toolbar">
        <div className="atlas-legend">
          {LEGEND.map((key) => (
            <span
              key={key.label}
              className={`atlas-legend__key${key.state ? ` atlas-legend__key--${key.state}` : ""}`}
            >
              <i aria-hidden className="atlas-legend__swatch" />
              {key.label}
            </span>
          ))}
        </div>
      </div>

      <div className="atlas-canvas">
        {/* `data-pulse` is the workbench atlas's own switch for how a live relationship moves,
            and `ripple` is the mode this replay wants: one comet head per wire at the run's
            own tempo, every head leaving the boundary under the model, and a ring going out
            from the node itself. Set here rather than restated as a second set of rules. */}
        <svg
          viewBox="0 0 780 520"
          preserveAspectRatio="xMidYMid meet"
          data-pulse="ripple"
          aria-hidden
          focusable="false"
        >
          <defs>
            <pattern id="home-atlas-grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path className="atlas-grid-line" d="M 24 0 L 0 0 0 24" fill="none" />
            </pattern>
            <marker
              id="home-atlas-arrow"
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
          <rect fill="url(#home-atlas-grid)" width="100%" height="100%" />
          <g className="atlas-clusters">
            <rect x="14" y="14" width="752" height="492" rx="22" />
            <text x="30" y="35">your-repository · 7</text>
          </g>

          <g>
            {EDGES.map((edge) => {
              const live = states[edge.from] === "judging" || states[edge.to] === "judging";
              // A relationship arriving at a boundary the review says should change.
              const risk = states[edge.to] === "hotspot";
              return (
                <path
                  key={edge.d}
                  className={`atlas-edge atlas-edge--kind-${edge.kind}${
                    live ? " atlas-edge--active" : ""
                  }${risk ? " atlas-edge--risk" : ""}`}
                  pathLength={100}
                  markerEnd="url(#home-atlas-arrow)"
                  d={edge.d}
                />
              );
            })}
          </g>

          {/* Over every edge and under every node, and only on the live ones: the pulse is
              its own path because three edge kinds already spend `stroke-dasharray` on
              meaning. Half the neighbourhood is drawn towards the node under the model and
              simply plays backwards, so every head leaves the boundary being judged. */}
          <g>
            {EDGES.filter(
              (edge) => states[edge.from] === "judging" || states[edge.to] === "judging",
            ).map((edge) => (
              <path
                key={edge.d}
                className={`atlas-pulse${
                  states[edge.to] === "judging" ? " atlas-pulse--incoming" : ""
                }`}
                pathLength={100}
                d={edge.d}
              />
            ))}
          </g>

          {MODULES.map((module, index) => {
            const state = states[index];
            // The workbench atlas draws the one under the model as the selected node, and
            // that is what this is: `--active` carries the fill, the border and the ring.
            const mark = state === "judging" ? "active" : state;
            const landed = module.boundary !== null && module.boundary < judged;
            return (
              <g
                key={module.label}
                className={`atlas-node atlas-node--${mark}`}
                transform={`translate(${module.x} ${module.y})`}
              >
                <rect
                  className="atlas-node__body"
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="10"
                />
                <rect
                  className="atlas-node__halo"
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="10"
                />
                <circle className="atlas-node__kind" cx="24" cy="25" r="10" />
                <text className="atlas-node__symbol" x="24" y="29" textAnchor="middle">
                  {SYMBOL[state]}
                </text>
                <text className="atlas-node__label" x="43" y="29">
                  {module.label}
                </text>
                <text className="atlas-node__meta" x="18" y="59">
                  {module.meta}
                </text>
                <text
                  className="atlas-node__metric"
                  x={NODE_WIDTH - 16}
                  y="59"
                  textAnchor="end"
                >
                  {landed ? bearings[module.boundary!] : ""}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <p className="atlas-visible-count">
        7 modules · 8 dependencies · 5 boundaries detected. A module with no reference is one
        the detector surfaced no boundary in.
      </p>
    </div>
  );
}
