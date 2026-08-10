/** The side panel: everything stored about the selected node, and the ways on from it. */

import { AlertTriangle, GitBranch, Layers3, Route } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import type { AtlasEdgeView, AtlasNodeView, RepositoryAtlasProps } from "./graph-model";
import { truncate } from "./labels";
import { STATE_ICON } from "./node-states";

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

/** The node's relationships in one direction, each a way to the node at the other end. */
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
