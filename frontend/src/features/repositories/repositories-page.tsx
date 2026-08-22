import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, type CheckoutRefresh, type RepositorySummary, type ReviewSummary } from "../../api";
import { cn } from "../../lib/cn";
import {
  atlasFreshness,
  plural,
  relativeTime,
  repositoryName,
  shortId,
  statusOf,
} from "../../lib/format";
import { Badge, Tag } from "../../ui/badge";
import { Button, ButtonLink } from "../../ui/button";
import { Field, Input, SearchInput } from "../../ui/field";
import { GitBranchIcon, RefreshIcon } from "../../ui/icons";
import { MetaLine, Mono, PathRef, Statistic } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelHeader } from "../../ui/panel";
import { EmptyState, ErrorNotice, LoadingPanel, Notice, Spinner } from "../../ui/states";
import { useToast } from "../../ui/toast";

function latestReviewFor(reviews: ReviewSummary[], root: string): ReviewSummary | undefined {
  return reviews
    .filter((review) => review.repository.path === root)
    .sort((left, right) => Date.parse(right.started_at) - Date.parse(left.started_at))[0];
}

/**
 * What a review of this repository costs, in the two units somebody plans around.
 *
 * The card counted nodes, edges and signals — three measurements of the atlas, and none of
 * them a number anybody can act on. What a person deciding whether to run a review wants to
 * know is how long it takes and how much of their afternoon it hands back, and the newest
 * review already carries both: a finding count, a start and a finish.
 */
function reviewCost(review: ReviewSummary | undefined): string | null {
  if (!review) return null;
  const candidates = plural(review.finding_count, "candidate");
  if (!review.finished_at) return `${candidates}, still running`;
  const elapsed = Date.parse(review.finished_at) - Date.parse(review.started_at);
  if (Number.isNaN(elapsed) || elapsed < 0) return candidates;
  const minutes = Math.round(elapsed / 60_000);
  return `${candidates}, ${minutes < 1 ? "under a minute" : plural(minutes, "minute")}`;
}

function RepositoryCard({
  repository,
  latest,
  selected,
  onSelect,
}: {
  repository: RepositorySummary;
  latest?: ReviewSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const snapshots = repository.snapshot_count ?? 1;
  // The distance from the checkout where the workspace can measure one, and the clock only
  // where it cannot. Nothing here holds a second answer of its own any more: re-indexing and
  // fetching both invalidate the listing, and the listing is where the distance comes from.
  const behind = repository.commits_behind ?? 0;
  const freshness = atlasFreshness(repository.created_at, repository.commits_behind);
  const cost = reviewCost(latest);

  const reindex = useMutation({
    mutationFn: () => api.indexRepository(repository.root_path),
    onSuccess: async (version) => {
      await client.invalidateQueries({ queryKey: ["repositories"] });
      // Said as what it found, not as "done". Re-indexing an unchanged checkout is the
      // ordinary case and it is worth knowing that it was a no-op, because the reason
      // somebody pressed this is usually a suspicion that the atlas had fallen behind.
      const moved = version.git_commit_sha !== repository.git_commit_sha;
      toast.say(
        moved
          ? `Re-indexed ${repositoryName(repository.root_path)} at ${shortId(version.git_commit_sha ?? "", 8)}.`
          : `Re-indexed ${repositoryName(repository.root_path)}. Nothing on disk had changed since the last atlas.`,
      );
    },
  });

  const refresh = useMutation({
    mutationFn: () => api.refreshRepository(repository.root_path),
    onSuccess: async (result: CheckoutRefresh) => {
      // `updated` has been on the wire all along and nothing read it, so a fetch that pulled
      // thirty commits said exactly as much as a fetch that pulled none.
      if (!result.managed) {
        toast.say(
          `${repositoryName(repository.root_path)} is not a managed checkout — nothing was fetched. Reviews read what is on disk.`,
        );
        return;
      }
      await client.invalidateQueries({ queryKey: ["repositories"] });
      toast.say(
        result.updated
          ? `Fetched new commits on ${result.branch_name ?? repository.branch_name ?? "the checkout"}. Re-index to bring the atlas up to date.`
          : `${repositoryName(repository.root_path)} is already up to date with its remote.`,
      );
    },
  });

  return (
    <article
      className={cn(
        "rounded-lg border bg-surface p-4 transition",
        selected
          ? "border-rule-strong ring-1 ring-rule-strong"
          : "border-rule hover:border-rule-strong",
      )}
    >
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-display text-base font-semibold tracking-tight text-ink">
            {repositoryName(repository.root_path)}
          </h2>
          <Badge glyph={freshness.step}>Atlas {freshness.label}</Badge>
          {latest ? (
            <Badge tone={statusOf(latest.status).tone} glyph={statusOf(latest.status).glyph}>
              {statusOf(latest.status).label}
            </Badge>
          ) : null}
        </div>
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
            snapshots > 1 ? plural(snapshots, "snapshot") : null,
            // The commit is part of the claim rather than a decoration beside it: what this
            // line says is which snapshot of the repository the atlas was built from.
            repository.git_commit_sha ? (
              <span className="inline-flex items-center gap-1">
                {snapshots > 1 ? "newest" : "indexed"} {relativeTime(repository.created_at)} at{" "}
                <Mono className="text-[11px]">{shortId(repository.git_commit_sha, 8)}</Mono>
              </span>
            ) : (
              `${snapshots > 1 ? "newest" : "indexed"} ${relativeTime(repository.created_at)}`
            ),
            latest ? `last review ${relativeTime(latest.started_at)}` : "never reviewed",
          ]}
        />
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Tag>{(repository.node_count ?? 0).toLocaleString()} nodes</Tag>
          <Tag>{(repository.edge_count ?? 0).toLocaleString()} edges</Tag>
          <Tag>{(repository.signal_count ?? 0).toLocaleString()} signals</Tag>
          {/* Beside the counts because it belongs to the same claim: these are the
              measurements of an analysis, and this says what that analysis was not shown.
              A narrowed repository stays narrowed through every later index, deliberately
              and until now silently — so a review that skipped half the code looked exactly
              like one that had read all of it. */}
          {repository.excluded_path_count ? (
            <Tag>{plural(repository.excluded_path_count, "folder")} left out</Tag>
          ) : null}
          {cost ? <Tag>Last review: {cost}</Tag> : null}
        </div>
      </button>

      {/* Below the selecting button, not inside it: a path is a control of its own now — it
          copies — and a control inside a control is one press with two meanings. */}
      <PathRef path={repository.root_path} className="mt-2.5" />

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
          {reindex.isPending ? <Spinner label="" /> : <RefreshIcon className="size-3.5" />} Re-index
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate()}
          title="Pull whatever has landed on the remote, for a checkout ArchCompass manages"
        >
          {refresh.isPending ? <Spinner label="" /> : null} Fetch
        </Button>
      </div>

      {behind > 0 ? (
        <Notice tone="working" className="mt-3">
          {plural(behind, "commit")} landed since this atlas was built at{" "}
          <Mono className="text-[11px]">{shortId(repository.git_commit_sha ?? "", 8)}</Mono>. A
          review started now would read the old snapshot.
        </Notice>
      ) : null}
      {/* Neither mutation renders its failure here. `main.tsx` toasts every unhandled
          mutation error, and a card that is scrolled off screen — which is where both of
          these are pressed from — cannot report anything to anybody in place. */}
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
      <PanelHeader title="Atlas" description={<PathRef path={root} />} />
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
              <Spinner label="" /> Reading the atlas…
            </div>
          ) : hotspots.error ? (
            <div className="mt-2">
              <ErrorNotice
                error={hotspots.error}
                action={
                  <Button size="sm" variant="secondary" onClick={() => void hotspots.refetch()}>
                    Try again
                  </Button>
                }
              />
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
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");

  /**
   * Which repository is selected lives in the URL, because it is a place rather than a
   * gesture.
   *
   * It was `useState`, and nothing outside this component could name a repository — so the
   * command palette listed every one of them and linked all of them to `/repositories`,
   * where the first card is selected whatever you searched for. Searching `billing-service`
   * and pressing Enter landed on `payments-platform`, which is indistinguishable from the
   * palette not working at all.
   *
   * `replace` rather than a push: walking down a list of cards is not seven pages of
   * history, and Back from here should be wherever you came from.
   */
  const [params, setParams] = useSearchParams();
  const requestedRoot = params.get("root");
  const select = (root: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("root", root);
        return next;
      },
      { replace: true },
    );

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  /**
   * The summary, not the reviews: all this page reads off a review is its path, its status,
   * its start, its finish and a finding count — and a stored review is most of a
   * repository's atlas, so the full list was megabytes a row to draw one line of text.
   *
   * Filed under `["reviews", …]` on purpose. React Query matches a key by prefix, so the
   * seven `invalidateQueries({ queryKey: ["reviews"] })` already written across this
   * application reach this list too, and a review deleted or composed elsewhere does not
   * leave this page quoting it.
   */
  const reviews = useQuery({ queryKey: ["reviews", "summary"], queryFn: api.reviewSummaries });
  const checkout = useMutation({
    mutationFn: () => api.checkoutRepository(url.trim(), branch.trim() || null),
    // The form is on screen and the failure belongs beside it, so the global toast would be
    // saying the same sentence twice in one eyeline.
    meta: { handled: true },
    onSuccess: async (result) => {
      select(result.root_path);
      setUrl("");
      setBranch("");
      await client.invalidateQueries({ queryKey: ["repositories"] });
      toast.say(`Cloned ${repositoryName(result.root_path)}. It is indexed when a review starts.`);
    },
  });

  // One row per repository, newest atlas first, straight off the wire. This page used to
  // collapse the indexing history itself, because the listing was that history: a repository
  // indexed twenty-five times arrived twenty-five times, and drawn row for row that was
  // sixty-five cards for seven repositories, growing by one on every Re-index. The service
  // groups now, so the only thing left to key on is the path — which is what the selection,
  // the atlas panel and the review lookup were all already comparing.
  const all = repositories.data;
  const visible = useMemo(
    () =>
      (all ?? []).filter((repository) =>
        `${repository.root_path} ${repository.branch_name ?? ""}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [all, query],
  );
  // An explicit `?root=` wins over the search, so arriving from the palette selects what the
  // palette named even where a stale search term would have hidden it.
  const selected =
    (all ?? []).find((repository) => repository.root_path === requestedRoot) ??
    visible[0] ??
    null;

  return (
    <div>
      <PageHeader
        eyebrow="Deterministic analysis"
        title="Repositories"
        description="What ArchCompass has indexed."
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

      {/* The header and the clone form stay mounted through every state below them. A page
          that replaces itself with its own error message takes away the two things a person
          can still do about it — go somewhere else, or clone something. */}
      {repositories.isPending ? (
        <LoadingPanel label="Loading indexed repositories…" rows={4} />
      ) : !all ? (
        <ErrorNotice
          error={repositories.error}
          action={
            <Button size="sm" variant="secondary" onClick={() => void repositories.refetch()}>
              Try again
            </Button>
          }
        />
      ) : !all.length ? (
        <EmptyState
          title="No repository has been indexed"
          action={<ButtonLink to="/start">Start the first review</ButtonLink>}
        >
          Indexing happens when a review starts, or when you clone a repository above.
        </EmptyState>
      ) : (
        <>
          {/* A background poll that failed while the list is on screen is a moment, not a
              fault: the list stays, and the page says it has lost contact rather than
              claiming the workspace holds nothing. */}
          {repositories.isError ? (
            <Notice tone="working" className="mb-4">
              Lost contact with the workspace. This list may be out of date.
            </Notice>
          ) : null}
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
                  key={repository.root_path}
                  repository={repository}
                  latest={latestReviewFor(reviews.data ?? [], repository.root_path)}
                  selected={selected?.root_path === repository.root_path}
                  onSelect={() => select(repository.root_path)}
                />
              ))}
              {!visible.length ? (
                <EmptyState title="No repository matches that">
                  Clear the search to see every indexed repository.
                </EmptyState>
              ) : null}
            </div>
            {selected ? <AtlasPreview repository={selected} /> : null}
          </div>
        </>
      )}
    </div>
  );
}
