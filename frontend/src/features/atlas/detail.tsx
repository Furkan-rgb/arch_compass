import { cn } from "../../lib/cn";
import { humanise, plural } from "../../lib/format";
import { Button } from "../../ui/button";
import { Mono, PathRef, TONE_TEXT } from "../../ui/meta";
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
 */

const EXPLORATIONS: { operation: ExploreOperation; label: string; depth?: number }[] = [
  { operation: "children", label: "Children" },
  { operation: "dependencies", label: "Dependencies" },
  { operation: "dependants", label: "Dependants" },
  { operation: "callers", label: "Callers" },
  { operation: "implementations", label: "Implementations" },
  { operation: "tests", label: "Tests" },
  { operation: "forward_neighbourhood", label: "Two hops out", depth: 2 },
];

export function AtlasDetailPanel({
  node,
  edges,
  nodes,
  onSelectNode,
  onOpenFinding,
  onExploreNode,
  pathStartNodeId,
  onSetPathStart,
  onTracePath,
  exploreNote,
  traceNote,
  loading,
}: {
  node?: AtlasNodeView;
  edges: AtlasEdgeView[];
  nodes: AtlasNodeView[];
  onSelectNode: (nodeId: string) => void;
  onOpenFinding?: AtlasExplorerProps["onOpenFinding"];
  onExploreNode?: AtlasExplorerProps["onExploreNode"];
  pathStartNodeId?: string | null;
  onSetPathStart?: (nodeId: string) => void;
  onTracePath?: (targetNodeId: string) => void;
  exploreNote?: string;
  traceNote?: string;
  loading?: boolean;
}) {
  if (!node) {
    return (
      <aside className="border-t border-rule p-4 lg:border-l lg:border-t-0">
        <p className="text-sm leading-6 text-ink-2">
          Select an element to read what the atlas stored about it — what it reaches, what
          reaches it, and what was measured of it.
        </p>
      </aside>
    );
  }
  const relationships = edges.filter(
    (edge) => edge.sourceId === node.id || edge.targetId === node.id,
  );
  const outgoing = relationships.filter((edge) => edge.sourceId === node.id);
  const incoming = relationships.filter((edge) => edge.targetId === node.id);
  const byId = new Map(nodes.map((item) => [item.id, item]));

  return (
    <aside
      className="min-w-0 space-y-4 overflow-y-auto border-t border-rule p-4 lg:border-l lg:border-t-0"
      aria-live="polite"
    >
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

      <PathRef path={node.path} />

      {node.description ? (
        <p className="text-sm leading-6 text-ink-2">{node.description}</p>
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
                    this wide, and "Maximum nesting d…" is a measurement a reader cannot use. */}
                <dt
                  className="text-[11px] leading-4 text-ink-3"
                  title={[
                    metric.definition,
                    metric.limitations,
                    metric.scope ? `Scope: ${humanise(metric.scope)}` : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
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
                  {signal.nature === "structural_proxy" ? "Structural proxy" : "Objective signal"}
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
          {/* What the last one came back with, including when that was nothing. A press that
              changes the map not at all is indistinguishable from a press that did not work. */}
          {exploreNote ? (
            <p aria-live="polite" className="mt-2 text-[12px] leading-5 text-ink">
              {exploreNote}
            </p>
          ) : null}
          {/* Every one of those is a query against the atlas this review pinned, so what comes
              back is what the repository held when it was read — never a fresh look. */}
          <p className="mt-2 text-[11px] leading-4 text-ink-3">
            Answered from the atlas this review was judged against, not from the repository as
            it stands now.
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
          {traceNote ? (
            <p aria-live="polite" className="mt-2 text-[12px] leading-5 text-ink">
              {traceNote}
            </p>
          ) : null}
        </Section>
      )}

      <Section title="Relationships">
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
        {!relationships.length && (
          <p className="text-[13px] leading-5 text-ink-3">
            Nothing drawn on this map touches it. The lens may be hiding what does.
          </p>
        )}
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-rule pt-3">
      <Mono className="mb-2 block text-[10px] uppercase tracking-[0.13em] text-ink-3">
        {title}
      </Mono>
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
  return (
    <div className="mb-3 last:mb-0">
      <Mono className="mb-1 block text-[10px] uppercase tracking-[0.13em] text-ink-3">
        {title} · {relationships.length}
      </Mono>
      <ul>
        {relationships.slice(0, 6).map((edge) => {
          const otherId = edge.sourceId === nodeId ? edge.targetId : edge.sourceId;
          const other = byId.get(otherId);
          return (
            <li key={edge.id}>
              <button
                type="button"
                disabled={!other}
                onClick={() => other && onSelectNode(other.id)}
                className={cn(
                  "flex min-h-8 pointer-coarse:min-h-11 w-full items-baseline justify-between gap-2",
                  "rounded-sm px-1.5 text-left transition hover:bg-sunken",
                  "disabled:pointer-events-none disabled:opacity-45",
                )}
              >
                <span className="truncate text-[13px] font-medium text-ink">
                  {other?.label || truncate(otherId, 18)}
                </span>
                <Mono className="shrink-0 text-[10px] uppercase tracking-[0.13em] text-ink-3">
                  {edge.kind}
                </Mono>
              </button>
            </li>
          );
        })}
      </ul>
      {relationships.length > 6 && (
        <Mono className="mt-1 block px-1.5 text-[10px] uppercase tracking-[0.13em] text-ink-3">
          {relationships.length - 6} more not listed
        </Mono>
      )}
    </div>
  );
}
