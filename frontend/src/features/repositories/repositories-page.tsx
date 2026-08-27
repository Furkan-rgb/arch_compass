import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
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
import { MetaLine, Mono, PathRef } from "../../ui/meta";
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
  const freshness = atlasFreshness(
    repository.created_at,
    repository.commits_behind,
    undefined,
    repository.head_commit_sha,
  );
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
      // Which card drives the panel beside it was carried by a hairline going one step
      // darker and a ring of the same value — 1.29:1 against the canvas in light, and
      // nothing at all in the accessibility tree, so a reader could not tell which of
      // fifteen identical cards the atlas belonged to. It is a ground change now, which is
      // what the ramp already defines for a selected row, and it is stated as
      // `aria-current`. `CaseCard` reached the same recipe first.
      aria-current={selected ? "true" : undefined}
      className={cn(
        "rounded-lg border p-4 transition",
        selected
          ? "border-rule-strong bg-sunken"
          : "border-rule bg-surface hover:border-rule-strong",
      )}
    >
      {/* Not a button. This wrapped the heading, both badges, the meta line and five tags in
          one control, so the card's accessible name was the whole card read out as a single
          string and the `<h2>` stopped being a heading anybody could navigate by — on the
          page whose entire job is "what ArchCompass has indexed". The card is content again
          and `Open atlas` below is the one named control that selects it, which is the same
          argument the `PathRef` beneath already makes: a control inside a control is one
          press with two meanings. */}
      <div>
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
        {repository.excluded_path_count || cost ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {/* The three atlas measurements used to lead this row and they are gone from it.
                They were on screen twice at once — here, and again as 24px statistics in the
                panel beside the card, with `edges` renamed to `Relations` in the second copy
                — and the comment on `reviewCost` above already argues that none of them is a
                number anybody can act on. What is left is what a person deciding whether to
                run a review actually weighs: what the analysis was not shown, and what the
                last one cost. */}
            {repository.excluded_path_count ? (
              <Tag>{plural(repository.excluded_path_count, "folder")} left out</Tag>
            ) : null}
            {cost ? <Tag>Last review: {cost}</Tag> : null}
          </div>
        ) : null}
      </div>

      {/* Below the card body rather than inside it: a path is a control of its own now — it
          copies — and a control inside a control is one press with two meanings. */}
      <PathRef path={repository.root_path} className="mt-2.5" />

      <div className="mt-3.5 flex flex-wrap gap-2 border-t border-rule pt-3">
        {/* `secondary`, not the accent fill. The accent means "this is the one thing the page
            is asking for" and a card list spends it once per row, so eight repositories drew
            eight solid reds plus the header's own and none of them was the one. The header's
            `Review a repository` keeps the page's single primary; inside the card, order is
            the hierarchy. */}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => navigate(`/start?root=${encodeURIComponent(repository.root_path)}`)}
        >
          Review
        </Button>
        {latest ? (
          <ButtonLink size="sm" variant="secondary" to={`/reviews/${latest.id}`}>
            Latest review
          </ButtonLink>
        ) : null}
        {/* The one control that selects this card, now that the card body is content rather
            than a control. It was already labelled, already 44px on a coarse pointer and
            already in the action row; the whole-card button beside it was the second way to
            do the same thing. */}
        <Button size="sm" variant="secondary" aria-pressed={selected} onClick={onSelect}>
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
    // `order-first` below `xl`, where this panel is stacked *after* every card in the list.
    // Pressing the third of fifteen cards changed something a dozen cards below the fold,
    // with no scroll and no announcement, so the press read as doing nothing. Above `xl` the
    // grid puts it back in the second column, unchanged.
    <Panel className="order-first xl:order-none xl:sticky xl:top-20">
      <PanelHeader title="Atlas" description={<PathRef path={root} />} />
      <PanelBody>
        {/* One sentence, not three 24px statistics. These were the largest type in the page
            body, set for three numbers the card's own comment calls unactionable, and the
            same three were printed as tags on the card at the same time. A number nobody
            acts on belongs in a sentence beside the thing it describes. The workspace's own
            overview summary is that same sentence, and the arrays beside it are a capped page
            rather than a total, so the counts here are the ones the indexer recorded against
            the snapshot. */}
        <Mono className="text-ink-3">
          {(repository.node_count ?? 0).toLocaleString()} nodes ·{" "}
          {(repository.edge_count ?? 0).toLocaleString()} relations ·{" "}
          {(repository.signal_count ?? 0).toLocaleString()} signals
        </Mono>

        <div className="mt-4 border-t border-rule pt-4">
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
            // Ruled, not striped. A zebra measured 1.09:1 against the panel in light and
            // 1.07:1 in dark, which is a tint nobody can see doing the job this system gives
            // a hairline. The `gap-1` went with it: a gap leaves a divider floating between
            // rows instead of ruling them.
            <ul className="mt-2 divide-y divide-rule">
              {hotspots.data.metric_values.slice(0, 8).map((metric) => {
                const node = hotspots.data?.node_summaries?.find(
                  (item) => item.node_id === metric.node_id,
                );
                const name = node?.qualified_name ?? metric.node_id;
                return (
                  // The whole name on the hover, because the column is about 200px wide and
                  // the rest of it was simply gone — no title, no wrap, no link.
                  <li
                    key={metric.node_id}
                    title={name}
                    className="flex items-center justify-between gap-3 py-1.5 text-xs"
                  >
                    {/* Truncated from the head rather than the tail. Eight qualified names
                        out of one repository share long prefixes, so clipping the end left
                        several rows reading identically; reversing the direction spends the
                        ellipsis on the part they have in common and keeps the part that
                        tells them apart. `bdi` is what stops the reversal reordering the
                        name itself. */}
                    <Mono className="truncate [direction:rtl] [text-align:left]">
                      <bdi>{name}</bdi>
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
  const [cloning, setCloning] = useState(false);
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

  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
  });
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
  const reviews = useQuery({
    queryKey: ["reviews", "summary"],
    queryFn: api.reviewSummaries,
  });
  const checkout = useMutation({
    mutationFn: () => api.checkoutRepository(url.trim(), branch.trim() || null),
    // The form is on screen and the failure belongs beside it, so the global toast would be
    // saying the same sentence twice in one eyeline.
    meta: { handled: true },
    onSuccess: async (result) => {
      select(result.root_path);
      setUrl("");
      setBranch("");
      setCloning(false);
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
  /**
   * An explicit `?root=` wins over the search, so arriving from the palette selects what the
   * palette named even where a stale search term would have hidden it.
   *
   * Where nobody has selected anything the first visible card stands in — and that made the
   * search box a selection control nobody asked for. With no `?root=` in the URL, every
   * keystroke re-pointed the panel at whichever repository had risen to the top of the
   * filtered list, swapped its counts, its hotspots and its path, fired another hotspots
   * request, and moved the selected treatment from card to card for a selection nobody made.
   * So the stand-in is latched: once a repository has stood in, it keeps standing in, and it
   * is resolved against the whole listing rather than the filtered one. A search now filters
   * the list and leaves the panel where it was.
   */
  const held = useRef<string | null>(null);
  const explicit = (all ?? []).find((repository) => repository.root_path === requestedRoot);
  const kept = held.current
    ? (all ?? []).find((repository) => repository.root_path === held.current)
    : undefined;
  const selected = explicit ?? kept ?? visible[0] ?? null;
  useEffect(() => {
    held.current = selected?.root_path ?? null;
  }, [selected]);

  return (
    <div>
      <PageHeader
        eyebrow="Deterministic analysis"
        title="Repositories"
        description="What ArchCompass has indexed."
        actions={
          <>
            {/* The clone form used to be the first surface under this header: a two-field
                form for a repository you do not have, standing between the page's own
                description and the list the page exists for, on every visit including the
                hundredth. It is a page-level control, so it lives where the page keeps its
                page-level controls, and the form opens when somebody wants it. */}
            <Button
              variant="secondary"
              aria-expanded={cloning}
              onClick={() => setCloning(!cloning)}
            >
              Clone a repository
            </Button>
            <ButtonLink to="/start">Review a repository</ButtonLink>
          </>
        }
      />

      {cloning ? (
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
              {/* The word stays and the mark joins it. Swapping the label for a spinner
                  collapsed the button's width and changed its accessible name to "Working",
                  so a reader lost the identity of the control they had just pressed. */}
              {checkout.isPending ? (
                <>
                  <Spinner label="" /> Cloning
                </>
              ) : (
                "Clone"
              )}
            </Button>
            {checkout.error ? (
              <div className="md:col-span-3">
                <ErrorNotice error={checkout.error} />
              </div>
            ) : null}
          </PanelBody>
        </Panel>
      ) : null}

      {/* The header stays mounted through every state below it, and it now carries the clone
          control as well as the primary action. A page that replaces itself with its own
          error message takes away the two things a person can still do about it — go
          somewhere else, or clone something. */}
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
                <EmptyState
                  title="No repository matches that"
                  action={
                    <Button variant="secondary" onClick={() => setQuery("")}>
                      Clear the search
                    </Button>
                  }
                >
                  {/* The panel beside this one keeps showing a full atlas for a repository
                      the search has hidden, and the two halves of the screen were
                      contradicting each other with nothing to explain it. The panel is
                      genuinely useful, so it stays and the empty state says whose it is. */}
                  {selected
                    ? `${repositoryName(selected.root_path)} is still open beside this. Clear the search to see it.`
                    : "Clear the search to see every indexed repository."}
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
