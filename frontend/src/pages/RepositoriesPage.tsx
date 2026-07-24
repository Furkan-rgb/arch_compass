import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, GitBranch, Network, Plus, SearchCode } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { RepositoryAtlas, type AtlasNodeView } from "../atlas";
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  Stat,
  formatDate,
  shortId,
} from "../components";

export function RepositoriesPage() {
  const queryClient = useQueryClient();
  const [rootPath, setRootPath] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const repositoryChoices = useMemo(
    () =>
      repositories.data?.filter(
        (repository, index, all) =>
          all.findIndex((item) => item.root_path === repository.root_path) === index,
      ) || [],
    [repositories.data],
  );
  const summary = useQuery({
    queryKey: ["repository-summary", selected],
    queryFn: () => api.repositorySummary(selected!),
    enabled: Boolean(selected),
  });
  const hotspots = useQuery({
    queryKey: ["repository-hotspots", selected],
    queryFn: () => api.repositoryHotspots(selected!),
    enabled: Boolean(selected),
  });
  const inspection = useQuery({
    queryKey: ["repository-inspect", selected, selectedNodeId],
    queryFn: () => api.repositoryInspect(selected!, selectedNodeId!),
    enabled: Boolean(selected && selectedNodeId),
  });
  const index = useMutation({
    mutationFn: api.indexRepository,
    onSuccess: (version) => {
      setRootPath("");
      setSelected(version.root_path);
      void queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  useEffect(() => {
    if (!selected && repositoryChoices.length) {
      setSelected(repositoryChoices[0].root_path);
    }
  }, [repositoryChoices, selected]);

  useEffect(() => {
    setSelectedNodeId(summary.data?.node_summaries[0]?.node_id || null);
  }, [selected, summary.data]);

  const atlasNodes = useMemo(() => {
    const summaries = new Map(
      [...(summary.data?.node_summaries || []), ...(hotspots.data?.node_summaries || [])]
        .map((node) => [node.node_id, node]),
    );
    const hotspotMetrics = new Map(
      (hotspots.data?.metric_values || []).map((metric) => [metric.node_id, metric]),
    );
    const inspectMetrics = new Map(
      (inspection.data?.metric_values || [])
        .filter((metric) => metric.node_id === selectedNodeId)
        .map((metric) => [
          metric.metric,
          {
            label: metric.metric.replaceAll("_", " ").replaceAll(".", " · "),
            value: metric.value,
            group: metric.metric.split(".")[0].replaceAll("_", " "),
          },
        ]),
    );
    const signalCounts = new Map<string, number>();
    [...(summary.data?.signals || []), ...(inspection.data?.signals || [])].forEach((signal) =>
      signalCounts.set(signal.node_id, (signalCounts.get(signal.node_id) || 0) + 1),
    );
    return [...summaries.values()].map((node): AtlasNodeView => {
      const hotspot = hotspotMetrics.get(node.node_id);
      const selectedMetrics =
        node.node_id === selectedNodeId ? [...inspectMetrics.values()] : [];
      return {
        id: node.node_id,
        label: node.qualified_name.split(".").at(-1) || node.qualified_name,
        path: node.location
          ? `${node.path}:${node.location.start_line}–${node.location.end_line}`
          : node.path,
        kind: node.node_type,
        state: hotspot && (hotspot.rank || 99) <= 5
          ? "hotspot"
          : ["repository", "package"].includes(node.node_type)
            ? "contained"
            : "normal",
        description:
          node.node_id === selectedNodeId
            ? inspectionDescription(inspection.data?.summary)
            : undefined,
        metrics: selectedMetrics.length
          ? selectedMetrics
          : hotspot
            ? [{
                label: hotspot.metric.replaceAll("_", " "),
                value: hotspot.value,
                group: `Rank #${hotspot.rank || "—"}`,
              }]
            : [],
        signalCount: signalCounts.get(node.node_id) || 0,
      };
    });
  }, [hotspots.data, inspection.data, selectedNodeId, summary.data]);

  const atlasEdges = useMemo(() => {
    const nodeIds = new Set(atlasNodes.map((node) => node.id));
    return [
      ...(summary.data?.relationships || []),
      ...(inspection.data?.relationships || []),
    ]
      .filter(
        (edge, index, all) =>
          nodeIds.has(edge.source_id) &&
          nodeIds.has(edge.target_id) &&
          all.findIndex((item) => item.edge_id === edge.edge_id) === index,
      )
      .map((edge) => ({
        id: edge.edge_id,
        sourceId: edge.source_id,
        targetId: edge.target_id,
        kind: edge.edge_type,
        confidence: edge.confidence,
        risk: ["imports", "calls"].includes(edge.edge_type) &&
          atlasNodes.find((node) => node.id === edge.source_id)?.state === "hotspot" &&
          atlasNodes.find((node) => node.id === edge.target_id)?.state === "hotspot",
      }));
  }, [atlasNodes, inspection.data?.relationships, summary.data?.relationships]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Deterministic repository evidence"
        title="Repository atlases"
        description="Arch Compass parses Python without importing or modifying the analyzed project."
      />

      <section className="path-bar">
        <span className="path-bar__icon"><SearchCode size={20} /></span>
        <label>
          <span>Local repository path</span>
          <input
            value={rootPath}
            onChange={(event) => setRootPath(event.target.value)}
            placeholder="/absolute/path/to/python-project"
          />
        </label>
        <button
          className="button button--primary"
          type="button"
          disabled={!rootPath.trim() || index.isPending}
          onClick={() => index.mutate(rootPath.trim())}
        >
          <Plus size={16} />
          {index.isPending ? "Indexing…" : "Create atlas"}
        </button>
      </section>
      <p className="field-hint">
        The Arch Compass workspace must not be inside the project being analyzed.
      </p>
      {index.error && <ErrorPanel error={index.error} />}

      {repositories.isLoading && <Loading label="Reading repository atlases…" />}
      {repositories.error && <ErrorPanel error={repositories.error} />}
      {repositories.data && !repositories.data.length && (
        <EmptyState
          icon={<Boxes size={31} />}
          title="No indexed repositories"
          description="Paste an absolute project path above. Each index creates an immutable evidence version."
        />
      )}

      <div className="repository-overview">
        <div className="repository-list">
          {repositoryChoices.map((repository) => (
            <button
              type="button"
              key={repository.version_id}
              onClick={() => {
                setSelected(repository.root_path);
                setSelectedNodeId(null);
              }}
              className={`repository-card ${selected === repository.root_path ? "repository-card--active" : ""}`}
            >
              <span className="repo-glyph"><Boxes size={18} /></span>
              <span>
                <strong>{repository.root_path.split("/").at(-1)}</strong>
                <small>{repository.root_path}</small>
              </span>
              <Badge tone="neutral">{repository.node_count} nodes</Badge>
              <time>{formatDate(repository.created_at)}</time>
            </button>
          ))}
        </div>

        {selected && (
          <aside className="inspector repository-version">
            <span className="eyebrow">Latest atlas</span>
            <h2>{selected.split("/").at(-1)}</h2>
            <p className="mono-path">{selected}</p>
            {summary.isLoading && <Loading label="Freshness-checking atlas…" />}
            {summary.error && <ErrorPanel error={summary.error} />}
            {summary.data && (
              <>
                <Badge tone="success">Fresh evidence</Badge>
                <p className="summary-copy">{summary.data.summary || "Repository summary prepared."}</p>
              </>
            )}
            {repositoryChoices.find((item) => item.root_path === selected) && (() => {
              const repository = repositoryChoices.find((item) => item.root_path === selected)!;
              return (
                <>
                  <div className="stats-grid stats-grid--compact">
                    <Stat label="Nodes" value={repository.node_count} />
                    <Stat label="Relations" value={repository.edge_count} />
                    <Stat label="Signals" value={repository.signal_count} />
                  </div>
                  <dl className="meta-pairs">
                    <div><dt>Version</dt><dd>{shortId(repository.version_id)}</dd></div>
                    <div><dt>Identity</dt><dd>{shortId(repository.repository_identity)}</dd></div>
                    <div>
                      <dt><GitBranch size={13} /> Git</dt>
                      <dd>{repository.git_commit_sha?.slice(0, 10) || "uncommitted snapshot"}</dd>
                    </div>
                  </dl>
                </>
              );
            })()}
            <div className="inspector-note">
              <Network size={18} />
              <p>Freshness is checked again before any query or consultation uses this atlas.</p>
            </div>
          </aside>
        )}
      </div>

      {selected && (
        <>
          {(summary.error || hotspots.error || inspection.error) && (
            <ErrorPanel error={summary.error || hotspots.error || inspection.error} />
          )}
          <RepositoryAtlas
            title={`${selected.split("/").at(-1)} RepositoryAtlas`}
            description="A bounded structural map of the latest freshness-checked snapshot. Hotspots are ranked by reverse dependency reach."
            nodes={atlasNodes}
            edges={atlasEdges}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
            loading={summary.isLoading || hotspots.isLoading || inspection.isLoading}
          />
        </>
      )}
    </div>
  );
}

function inspectionDescription(summary?: string) {
  if (!summary) return undefined;
  return summary.split("; metrics=")[0];
}
