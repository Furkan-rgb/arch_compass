import { cn } from "../../lib/cn";
import { humanise, plural } from "../../lib/format";
import { Button } from "../../ui/button";
import { Mono, PathRef, TONE_TEXT } from "../../ui/meta";
import { Prose, plainProse } from "../../ui/prose";
import { truncate } from "./geometry";
import type { AtlasEdgeView, AtlasExplorerProps, AtlasNodeView, ExploreOperation } from "./graph";

/**
 * The panel beside the map: everything the atlas stored about the selected element, and the
 * ways on from it.
 *
 * This is the half of the surface that is not a picture. A map answers "where", and every
 * follow-up question a reader has once they are looking at a card — what depends on this, what
 * does it reach, what was measured of it, where is the finding — is answered here rather than
 * by drawing more. The map never grows a tooltip: a tooltip pinned to a card covers its
 * neighbours, which are the thing the map was consulted about.
 *
 * It is also the *only* text equivalent of the graph, because every connector on the canvas is
 * `aria-hidden` — an SVG path is not something to announce. So the relationship list is not a
 * summary of the map, it is the map, and it may not stop at six with a count of what it is not
 * saying.
 */

const EXPLORATIONS: { operation: ExploreOperation; label: string; depth?: number }[] = [
  { operation: "subsystem_summary", label: "Children" },
  { operation: "direct_dependencies", label: "Dependencies" },
  { operation: "direct_dependants", label: "Dependants" },
  { operation: "known_callers", label: "Callers" },
  { operation: "implementations", label: "Implementations" },
  { operation: "related_tests", label: "Tests" },
  { operation: "forward_neighbourhood", label: "Two hops out", depth: 2 },
];

/** How many relationships are listed before the rest go behind a disclosure. */
const LISTED = 6;

export function AtlasDetailPanel({
  node,
  edges,
  nodes,
  drawnEdgeIds,
  onSelectNode,
  onOpenFinding,
  onExploreNode,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  collapsed,
  loading,
}: {
  node?: AtlasNodeView;
  edges: AtlasEdgeView[];
  nodes: AtlasNodeView[];
  /** Which of those relationships the map is currently drawing, which is not all of them. */
  drawnEdgeIds: Set<string>;
  onSelectNode: (nodeId: string) => void;
  onOpenFinding?: AtlasExplorerProps["onOpenFinding"];
  onExploreNode?: AtlasExplorerProps["onExploreNode"];
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  /**
   * Whether the column this panel lives in has been given back to the map.
   *
   * It renders nothing but its live region when it is, and it is still *rendered* — see the
   * comment on that region. An aside that unmounts itself when nothing is selected takes the
   * live region with it, and the state it would unmount in is exactly the state a first arrow
   * key moves out of.
   */
  collapsed?: boolean;
  loading?: boolean;
}) {
  const relationships = node
    ? edges.filter((edge) => edge.sourceId === node.id || edge.targetId === node.id)
    : [];
  const drawn = relationships.filter((edge) => drawnEdgeIds.has(edge.id)).length;
  const outgoing = relationships.filter((edge) => edge.sourceId === node?.id);
  const incoming = relationships.filter((edge) => edge.targetId === node?.id);
  const byId = new Map(nodes.map((item) => [item.id, item]));

  return (
    <aside
      // Collapsed, the aside keeps nothing but its live region: no border, no padding, no
      // content — a zero-height row beside a canvas that has been given the whole width back.
      className={cn(
        "min-w-0 overflow-y-auto",
        !collapsed && "space-y-4 border-t border-rule p-4 lg:border-l lg:border-t-0",
      )}
    >
      {/**
       * One sentence, and nothing else, is what changes out loud.
       *
       * The whole panel was the live region, so every arrow-key step re-announced the
       * heading, the qualified name, the path, the six measurements, every structural signal
       * and the seven exploration buttons — and `navigateNode` selects as it moves, so
       * walking the map read the panel aloud once per keystroke. What a reader needs on
       * arrival is which card they are on; everything else is there to be read when they stop.
       *
       * Rendered on both branches so the region is in the document before it changes.
       * Announcing an element that was itself just inserted is unreliable, and the panel with
       * nothing selected is exactly the state a first arrow key moves out of.
       */}
      <p className="sr-only" aria-live="polite">
        {node
          ? `${node.label}, ${humanise(node.kind)}${
              node.verdictLabel ? `, ${node.verdictLabel}` : ""
            }. ${plural(relationships.length, "relationship")}.`
          : ""}
      </p>

      {collapsed ? null : !node ? (
        <p className="text-sm leading-6 text-ink-2">
          Select an element to read what the atlas stored about it — what it reaches, what
          reaches it, and what was measured of it.
        </p>
      ) : (
        <>
          <div>
            <Mono className="block text-[10px] uppercase tracking-[0.13em] text-ink-3">
              {humanise(node.kind)}
            </Mono>
            <h3
              className={cn(
                "mt-1 text-base font-semibold leading-tight [overflow-wrap:anywhere]",
                node.tone ? TONE_TEXT[node.tone] : "text-ink",
              )}
            >
              {node.label}
            </h3>
            <Mono className="mt-1 block text-[11px] text-ink-3 [overflow-wrap:anywhere]">
              {node.qualified}
            </Mono>
          </div>

          {/* The span as data, not joined into the path string. `PathRef` takes the three
              apart precisely so the copy value is the `path:line` an editor's go-to-file box
              accepts while the screen shows the readable range — the atlas was the one call
              site that handed it "file.py:10-40" as a path, which defeated all three of its
              jobs at once: the copy, the `--ink-3` demotion of the span, and the editor href. */}
          <PathRef path={node.path} line={node.line} endLine={node.endLine} />

          {node.description ? (
            // This is a finding's reasoning, on its second surface: `atlas-surface.tsx`
            // builds the description as "`${verdict}. ${finding.reasoning}`", so the same
            // sentence and the same quoted names arrive here as arrive in the Judged block.
            <p className="text-sm leading-6 text-ink-2">
              <Prose>{node.description}</Prose>
            </p>
          ) : null}

          {/* The other half of the link a finding already offers into the map. A reader who
              arrived here from the docket can get back to the reasoning, and one who found the
              element on the canvas can reach the verdict written about it. Only where a review
              judged it: the map draws plenty that no finding is about. */}
          {onOpenFinding && node.candidateId ? (
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              onClick={() => onOpenFinding(node.candidateId!)}
            >
              Open the finding
            </Button>
          ) : null}

          {node.metrics.length > 0 && (
            <Section title="Measured">
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2.5">
                {node.metrics.slice(0, 6).map((metric) => (
                  <div key={metric.label} className="min-w-0">
                    <dd className="font-mono text-sm font-semibold tabular-nums text-ink">
                      {metric.value}
                    </dd>
                    {/* Wrapping rather than truncating. Half of these names do not fit a column
                        this wide, and "Maximum nesting d…" is a measurement a reader cannot
                        use. */}
                    <dt
                      className="text-[11px] leading-4 text-ink-3"
                      // A `title` is a string, so anything a model might have quoted in it
                      // has to have its delimiters taken off rather than drawn. These three
                      // fields come from the analysis today and carry none; this is what
                      // keeps that true if one of them ever stops being written by code.
                      title={plainProse(
                        [
                          metric.definition,
                          metric.limitations,
                          metric.scope ? `Scope: ${humanise(metric.scope)}` : "",
                        ]
                          .filter(Boolean)
                          .join(" · "),
                      )}
                    >
                      {metric.label}
                    </dt>
                  </div>
                ))}
              </dl>
            </Section>
          )}

          {node.signals && node.signals.length > 0 && (
            <Section title={plural(node.signals.length, "structural signal")}>
              <ul className="space-y-2.5">
                {node.signals.map((signal, index) => (
                  <li key={`${signal.code}-${index}`} className="border-l border-rule-strong pl-3">
                    <Mono className="block text-[11px] text-ink">
                      {signal.code.replaceAll("-", " ")}
                    </Mono>
                    <p className="mt-0.5 text-[13px] leading-5 text-ink-2">{signal.message}</p>
                    {/* What a signal *is* travels with it. A count of obscurity signals a reader
                        cannot qualify is a number they will read as meaning more than it does. */}
                    <Mono className="mt-1 block text-[10px] uppercase tracking-[0.13em] text-ink-3">
                      {signal.nature === "structural_proxy"
                        ? "Structural proxy"
                        : "Objective signal"}
                    </Mono>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {onExploreNode && (
            <Section title="Explore from here">
              <div className="flex flex-wrap gap-1">
                {EXPLORATIONS.map(({ operation, label, depth }) => (
                  <Button
                    key={operation}
                    variant="quiet"
                    size="sm"
                    disabled={loading}
                    onClick={() => onExploreNode(node.id, operation, depth)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              {/* What the last one came back with is written above the map rather than here.

                  It lived in this section, which exists only when a card is selected — so a
                  search that matched nothing on the map answered into a block that was not
                  rendered, and the reader who pressed Find with nothing selected got no answer
                  at all. It also appeared under a heading meaning "explore from this card"
                  when it was frequently about something else. `AtlasExplorer` draws it in the
                  strip above the canvas now, where the request was made from. */}
              {/* Every one of those is a query against the atlas this review pinned, so what comes
                  back is what the repository held when it was read — never a fresh look. */}
              <p className="mt-2 text-[11px] leading-4 text-ink-3">
                Answered from the atlas this review was judged against, not from the repository
                as it stands now.
              </p>
            </Section>
          )}

          {onSetPathStart && onTracePath && (
            <Section title="Dependency path">
              {pathStartNodeId && pathStartNodeId !== node.id ? (
                <Button
                  variant="quiet"
                  size="sm"
                  className="w-full"
                  disabled={loading}
                  onClick={() => onTracePath(node.id)}
                >
                  Trace from {byId.get(pathStartNodeId)?.label || "the start"} to here
                </Button>
              ) : (
                <Button
                  variant="quiet"
                  size="sm"
                  className="w-full"
                  disabled={loading}
                  onClick={() => onSetPathStart(node.id)}
                >
                  {pathStartNodeId === node.id ? "The path starts here" : "Use as the path start"}
                </Button>
              )}
              {/* The answer to a trace is written above the map with every other exploration's,
                  for the reason the section above gives. */}
            </Section>
          )}

          {/* No "Relationships" heading over "Reaches · 4" and "Reached by · 2": all three were
              the same 10px uppercase recipe, so the panel's deepest nesting was its
              flattest-looking, and the outer label added no fact the two inner ones did not
              already carry. The section rule is what says a block starts here. */}
          <Section>
            <RelationshipGroup
              title="Reaches"
              relationships={outgoing}
              nodeId={node.id}
              byId={byId}
              onSelectNode={onSelectNode}
            />
            <RelationshipGroup
              title="Reached by"
              relationships={incoming}
              nodeId={node.id}
              byId={byId}
              onSelectNode={onSelectNode}
            />
            {/**
             * Two different answers, and the sentence used to give the second one to the
             * first.
             *
             * "The lens may be hiding what does" was printed when the *whole* edge set was
             * empty — which is precisely when the lens is not the cause, because there is
             * nothing for it to hide. The lens can only be blamed where the atlas recorded
             * relationships and the map is drawing none of them.
             */}
            {!relationships.length ? (
              <p className="text-[13px] leading-5 text-ink-3">
                The atlas recorded nothing reaching it and nothing it reaches.
              </p>
            ) : !drawn ? (
              <p className="text-[13px] leading-5 text-ink-3">
                None of its {plural(relationships.length, "relationship")} is drawn under this
                lens. They are listed above; the lens and the relationship filters decide which
                the map draws.
              </p>
            ) : drawn < relationships.length ? (
              <Mono className="block text-[10px] uppercase tracking-[0.13em] text-ink-3">
                {drawn} of {relationships.length} drawn under this lens
              </Mono>
            ) : null}
          </Section>
        </>
      )}
    </aside>
  );
}

/** A block, with the rule that starts it and — where the block needs naming — its label. */
function Section({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-rule pt-3">
      {title ? (
        <Mono className="mb-2 block text-[10px] uppercase tracking-[0.13em] text-ink-3">
          {title}
        </Mono>
      ) : null}
      {children}
    </section>
  );
}

/** The element's relationships in one direction, each a way to the element at the other end. */
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
  const listed = relationships.slice(0, LISTED);
  const rest = relationships.slice(LISTED);
  const row = (edge: AtlasEdgeView) => (
    <RelationshipRow
      key={edge.id}
      edge={edge}
      nodeId={nodeId}
      byId={byId}
      onSelectNode={onSelectNode}
    />
  );
  return (
    <div className="mb-3 last:mb-0">
      <Mono className="mb-1 block text-[10px] uppercase tracking-[0.13em] text-ink-3">
        {title} · {relationships.length}
      </Mono>
      <ul>{listed.map(row)}</ul>
      {/* A disclosure rather than a count. "18 more not listed" is the panel telling the
          reader about eighteen elements it will not name and offering no way to name them —
          and these edges are `aria-hidden` on the canvas, so for anyone not looking at the
          picture that count was the end of the road.

          `<details>` rather than a button and a piece of state, so the disclosure role, the
          keyboard path and the expanded state announced to a screen reader are free. */}
      {rest.length > 0 && (
        <details className="group">
          <summary className="flex min-h-8 pointer-coarse:min-h-11 cursor-pointer list-none items-center px-1.5 font-mono text-[10px] uppercase tracking-[0.13em] text-ink-3 hover:text-ink [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">List the other {rest.length}</span>
            <span className="hidden group-open:inline">Hide the other {rest.length}</span>
          </summary>
          <ul>{rest.map(row)}</ul>
        </details>
      )}
    </div>
  );
}

function RelationshipRow({
  edge,
  nodeId,
  byId,
  onSelectNode,
}: {
  edge: AtlasEdgeView;
  nodeId: string;
  byId: Map<string, AtlasNodeView>;
  onSelectNode: (nodeId: string) => void;
}) {
  const otherId = edge.sourceId === nodeId ? edge.targetId : edge.sourceId;
  const other = byId.get(otherId);
  return (
    <li>
      <button
        type="button"
        disabled={!other}
        onClick={() => other && onSelectNode(other.id)}
        className={cn(
          "flex min-h-8 pointer-coarse:min-h-11 w-full items-baseline justify-between gap-2",
          "rounded-sm px-1.5 text-left transition hover:bg-sunken",
          // Drawn rather than dimmed, so the colour is set on the row and inherited by the name
          // inside it. A row whose other end is not on this map is still a name the reader
          // should be able to read, and at 45% it fell under the bar the ink ramp is measured
          // against.
          "text-ink disabled:pointer-events-none disabled:text-ink-3",
        )}
      >
        <span className="truncate text-[13px] font-medium">
          {other?.label || truncate(otherId, 18)}
        </span>
        <Mono className="shrink-0 text-[10px] uppercase tracking-[0.13em] text-ink-3">
          {edge.kind}
        </Mono>
      </button>
    </li>
  );
}
