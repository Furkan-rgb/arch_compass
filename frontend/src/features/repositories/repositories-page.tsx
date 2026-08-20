import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type RepositorySummary, type Review } from "../../api";
import { cn } from "../../lib/cn";
import {
  atlasFreshness,
  relativeTime,
  repositoryName,
  shortId,
  statusOf,
} from "../../lib/format";
import { Badge, Tag } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Field, Input, SearchInput } from "../../ui/field";
import { GitBranchIcon, RefreshIcon } from "../../ui/icons";
import { MetaLine, Mono, Statistic } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Spinner } from "../../ui/states";

function latestReviewFor(reviews: Review[], root: string): Review | undefined {
  return reviews
    .filter((review) => review.repository.path === root)
    .sort((left, right) => Date.parse(right.started_at) - Date.parse(left.started_at))[0];
}

function RepositoryCard({
  repository,
  latest,
  selected,
  onSelect,
}: {
  repository: RepositorySummary;
  latest?: Review;
  selected: boolean;
  onSelect: () => void;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const freshness = atlasFreshness(repository.created_at);
  const reindex = useMutation({
    mutationFn: () => api.indexRepository(repository.root_path),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
  const refresh = useMutation({
    mutationFn: () => api.refreshRepository(repository.root_path),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  return (
    <article
      className={cn(
        "rounded-lg border bg-surface p-4 transition",
        selected ? "border-rule-strong ring-1 ring-rule-strong" : "border-rule hover:border-rule-strong",
      )}
    >
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-base font-semibold tracking-tight text-ink">
            {repositoryName(repository.root_path)}
          </h2>
          <Badge tone={freshness.tone} glyph={freshness.tone === "cleared" ? "●" : "◆"}>
            Atlas {freshness.label}
          </Badge>
          {latest ? (
            <Badge tone={statusOf(latest.status).tone} glyph={statusOf(latest.status).glyph}>
              {statusOf(latest.status).label}
            </Badge>
          ) : null}
        </div>
        <Mono className="mt-1.5 block truncate text-[11px] text-ink-3">{repository.root_path}</Mono>
        <MetaLine
          className="mt-2"
          items={[
            repository.branch_name ? (
              <span className="inline-flex items-center gap-1">
                <GitBranchIcon className="size-3" />
                {repository.branch_name}
              </span>
            ) : (
              "bare folder"
            ),
            repository.git_commit_sha ? (
              <Mono className="text-[11px]">{shortId(repository.git_commit_sha, 8)}</Mono>
            ) : null,
            `indexed ${relativeTime(repository.created_at)}`,
            latest ? `latest review ${relativeTime(latest.started_at)}` : "never reviewed",
          ]}
        />
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Tag>{(repository.node_count ?? 0).toLocaleString()} nodes</Tag>
          <Tag>{(repository.edge_count ?? 0).toLocaleString()} edges</Tag>
          <Tag>{(repository.signal_count ?? 0).toLocaleString()} signals</Tag>
        </div>
      </button>

      <div className="mt-3.5 flex flex-wrap gap-2 border-t border-rule pt-3">
        <Button
          size="sm"
          onClick={() => navigate(`/start?root=${encodeURIComponent(repository.root_path)}`)}
        >
          Review
        </Button>
        {latest ? (
          <ButtonLink size="sm" variant="secondary" to={`/reviews/${latest.id}`}>
            Latest review
          </ButtonLink>
        ) : null}
        <Button size="sm" variant="secondary" onClick={onSelect}>
          Open atlas
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={reindex.isPending}
          onClick={() => reindex.mutate()}
          title="Rebuild the deterministic atlas from what is on disk"
        >
          {reindex.isPending ? <Spinner /> : <RefreshIcon className="size-3.5" />} Re-index
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate()}
          title="Pull whatever has landed on the remote, for a checkout ArchCompass manages"
        >
          {refresh.isPending ? <Spinner /> : null} Fetch
        </Button>
      </div>
      {refresh.data && !refresh.data.managed ? (
        <p className="mt-2 text-xs text-ink-3">
          Not a managed checkout — nothing was fetched. Reviews read what is on disk.
        </p>
      ) : null}
      {reindex.error ? (
        <div className="mt-2">
          <ErrorNotice error={reindex.error} />
        </div>
      ) : null}
      {refresh.error ? (
        <div className="mt-2">
          <ErrorNotice error={refresh.error} />
        </div>
      ) : null}
    </article>
  );
}

function AtlasPreview({ repository }: { repository: RepositorySummary }) {
  const root = repository.root_path;
  const hotspots = useQuery({
    queryKey: ["repository-hotspots", root],
    queryFn: () => api.repositoryHotspots(root),
  });

  return (
    <Panel className="xl:sticky xl:top-20">
      <PanelHeader title="Atlas" description={root} />
      <PanelBody>
        {/* The workspace's own overview summary is the sentence "N nodes, N edges, N objective
            signals" and the arrays beside it are a capped page rather than a total, so the
            counts here are the ones the indexer recorded against the snapshot. */}
        <div className="grid grid-cols-3 gap-4">
          <Statistic label="Nodes" value={(repository.node_count ?? 0).toLocaleString()} />
          <Statistic label="Relations" value={(repository.edge_count ?? 0).toLocaleString()} />
          <Statistic label="Signals" value={(repository.signal_count ?? 0).toLocaleString()} />
        </div>

        <div className="mt-5 border-t border-rule pt-4">
          <Label>Most depended upon</Label>
          {hotspots.isLoading ? (
            <div className="mt-2 flex items-center gap-2 text-sm text-ink-3">
              <Spinner /> Reading the atlas…
            </div>
          ) : hotspots.error ? (
            <div className="mt-2">
              <ErrorNotice error={hotspots.error} />
            </div>
          ) : hotspots.data?.metric_values?.length ? (
            <ul className="mt-2 grid gap-1">
              {hotspots.data.metric_values.slice(0, 8).map((metric) => {
                const node = hotspots.data?.node_summaries?.find(
                  (item) => item.node_id === metric.node_id,
                );
                return (
                  <li
                    key={metric.node_id}
                    className="flex items-center justify-between gap-3 rounded-sm px-2 py-1.5 text-xs odd:bg-sunken/50"
                  >
                    <Mono className="truncate text-[11px]">
                      {node?.qualified_name ?? shortId(metric.node_id, 14)}
                    </Mono>
                    <span className="shrink-0 tabular-nums text-ink-3">{metric.value}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-ink-3">
              Nothing in this snapshot is depended on by more than one other node.
            </p>
          )}
        </div>
      </PanelBody>
    </Panel>
  );
}

export function RepositoriesPage() {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  const checkout = useMutation({
    mutationFn: () => api.checkoutRepository(url.trim(), branch.trim() || null),
    onSuccess: async (result) => {
      setSelected(result.root_path);
      setUrl("");
      setBranch("");
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  if (repositories.isLoading) return <LoadingPanel label="Loading indexed repositories…" rows={4} />;
  if (repositories.error) return <ErrorNotice error={repositories.error} />;

  const all = repositories.data ?? [];
  const visible = all.filter((repository) =>
    `${repository.root_path} ${repository.branch_name ?? ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const activeRoot = selected ?? visible[0]?.root_path ?? null;
  const activeRepository = visible.find((item) => item.root_path === activeRoot) ?? null;

  return (
    <div>
      <PageHeader
        eyebrow="Deterministic analysis"
        title="Repositories"
        description="Every indexed snapshot ArchCompass holds, with the atlas it built and the review that read it."
        actions={<ButtonLink to="/start">Review a repository</ButtonLink>}
      />

      <Panel className="mb-5">
        <PanelHeader
          title="Clone a repository into the workspace"
          description="The checkout stays local and is indexed when a review starts."
        />
        <PanelBody className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-end">
          <Field label="Repository address">
            {(props) => (
              <Input
                {...props}
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://github.com/org/repository"
              />
            )}
          </Field>
          <Field label="Branch" hint="Optional">
            {(props) => (
              <Input
                {...props}
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                placeholder="main"
              />
            )}
          </Field>
          <Button
            variant="secondary"
            disabled={!url.trim() || checkout.isPending}
            onClick={() => checkout.mutate()}
          >
            {checkout.isPending ? <Spinner /> : "Clone"}
          </Button>
          {checkout.error ? (
            <div className="md:col-span-3">
              <ErrorNotice error={checkout.error} />
            </div>
          ) : null}
        </PanelBody>
      </Panel>

      {!all.length ? (
        <EmptyState
          title="No repository has been indexed"
          action={<ButtonLink to="/start">Start the first review</ButtonLink>}
        >
          Indexing happens when a review starts, or when you clone a repository above.
        </EmptyState>
      ) : (
        <>
          <div className="mb-4">
            <SearchInput
              label="Search repositories"
              value={query}
              onValueChange={setQuery}
              placeholder="Search path or branch"
              className="max-w-sm"
            />
          </div>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
            <div className="grid gap-2.5">
              {visible.map((repository) => (
                <RepositoryCard
                  key={repository.version_id}
                  repository={repository}
                  latest={latestReviewFor(reviews.data ?? [], repository.root_path)}
                  selected={activeRoot === repository.root_path}
                  onSelect={() => setSelected(repository.root_path)}
                />
              ))}
              {!visible.length ? (
                <EmptyState title="No repository matches that">
                  Clear the search to see every indexed repository.
                </EmptyState>
              ) : null}
            </div>
            {activeRepository ? <AtlasPreview repository={activeRepository} /> : null}
          </div>
        </>
      )}
    </div>
  );
}
