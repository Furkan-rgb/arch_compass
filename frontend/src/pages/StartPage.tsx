import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUp,
  ChevronRight,
  FlaskConical,
  FolderOpen,
  Play,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { api } from "../api";
import { EmptyLine, ErrorPanel, Loading, PageHeader, page, sheet } from "../components";
import { useModelPicker } from "../model-picker";
import { latestPerRepository } from "../repositories";
import { useRun } from "../run";
import { isReady, looksLikeGitAddress, runIntent, type StartSelection } from "../start-selection";
import type { BundledExample } from "../types";

/* A short list of things to pick from, at the density of a list rather than of a card wall:
   name, one fact about it, and the path that tells two of them apart. `aria-pressed` is
   the whole state. */
const pick = "m-0 grid max-h-[232px] list-none gap-0.5 overflow-y-auto p-0";
const pickButton = cn(
  "grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] gap-x-2 gap-y-0.5",
  "rounded-control border border-transparent bg-sunken px-2.5 py-2 text-left",
  "hover:border-rule",
  "aria-pressed:border-accent-rule aria-pressed:bg-accent-soft",
);
/* Not a `small`: the one surviving line of the old preflight sets that element's size
   unlayered, which no utility can outrank, and this line is 11px. */
const pickName = "min-w-0 overflow-hidden text-meta font-[650] text-ellipsis whitespace-nowrap";
const pickWhere = "col-span-full overflow-hidden font-mono text-micro text-ellipsis whitespace-nowrap text-ink-3";
/* An example is a pill rather than a button: it brings a repository and its case at once,
   which is a thing to take rather than an action to perform. */
const examplePill = cn(
  // `min-w-0 max-w-full` because a pill's width is set by its title, and the longest title
  // is longer than a phone: without them the flex row cannot shrink the pill, and the
  // whole sheet is dragged past the viewport edge rather than the one label truncating.
  "inline-flex h-[26px] min-w-0 max-w-full cursor-pointer items-center gap-2 rounded-pill border border-rule",
  "bg-surface px-3 text-meta whitespace-nowrap text-ink",
  "not-disabled:hover:border-accent-rule not-disabled:hover:bg-accent-soft",
  "disabled:cursor-not-allowed disabled:opacity-55",
);
const startColumn = "grid min-w-0 content-start gap-2.5 px-[var(--card-pad-x)] pt-4 pb-5";
const startHead = "flex items-baseline gap-2";
const hint = "m-0 text-meta leading-[1.5] text-ink-2";
/* A read that failed is reported once, at the top of the sheet, inside its own gutter. */
const readError = "px-[var(--card-pad-x)] [&_[data-slot=error-strip]]:mt-3 [&_[data-slot=error-strip]]:mb-0";

/** `a`, `a and b`, `a, b and c` — a list read aloud rather than joined with commas. */
function listed(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/**
 * Walking the machine's folders to find the one to index. State lives here, not on the page,
 * so the dialog unmounting it resets the walk.
 */
function FolderBrowser({
  start,
  indexing,
  error,
  onIndex,
  fetching,
  checkoutError,
  onCheckout,
}: {
  /** Where to open: a repository some case named, or the home folder where `null` lands. */
  start: string | null;
  indexing: boolean;
  error: unknown;
  onIndex: (root: string) => void;
  fetching: boolean;
  checkoutError: unknown;
  onCheckout: (url: string, branch: string | null) => void;
}) {
  const [at, setAt] = useState<string | null>(start);
  const [typed, setTyped] = useState(start ?? "");
  const [branch, setBranch] = useState("");
  // One field for "the project": recognised from what was pasted, never asked about.
  const address = looksLikeGitAddress(typed);
  // The field follows the walk until anybody edits it, so a listing that lands a beat later
  // cannot eat a path half way through being pasted.
  const [edited, setEdited] = useState(false);
  const listing = useQuery({
    queryKey: ["directories", at],
    queryFn: () => api.directories(at ?? undefined),
  });
  // The server's resolved path, never what the field holds.
  const here = listing.data?.path ?? null;

  useEffect(() => {
    if (here && !edited) setTyped(here);
  }, [here, edited]);

  const walk = (next: string | null) => {
    setEdited(false);
    setAt(next);
  };

  const go = () => {
    const asked = typed.trim();
    if (!asked) return;
    // An unchanged query key will not fetch again on its own, so asking for where we already
    // are has to refetch by hand.
    if (asked === at) {
      setEdited(false);
      void listing.refetch();
    } else {
      walk(asked);
    }
  };

  return (
    <>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          // Enter does what the line says: an address is fetched, a path is walked to.
          if (address) {
            if (!fetching) onCheckout(typed.trim(), branch.trim() || null);
          } else {
            go();
          }
        }}
      >
        <Button
          type="button"
          size="icon"
          aria-label="Go up to the parent folder"
          // A null parent is the server saying there is nowhere above this; nothing here
          // counts slashes to work that out.
          disabled={address || !listing.data?.parent}
          onClick={() => walk(listing.data?.parent ?? null)}
        >
          <ArrowUp size={14} aria-hidden />
        </Button>
        <Input
          className="min-w-0 flex-1 font-mono text-meta"
          value={typed}
          onChange={(event) => {
            setEdited(true);
            setTyped(event.target.value);
          }}
          aria-label="Folder path or git address"
          spellCheck={false}
        />
        {address ? null : (
          <Button type="submit" disabled={!typed.trim()}>
            Go
          </Button>
        )}
      </form>

      {address ? (
        // The line named a repository elsewhere, so the walk yields to the fetch: a branch
        // to ask for, and nothing else — the folder list below is about this machine.
        <Input
          className="font-mono text-meta"
          value={branch}
          onChange={(event) => setBranch(event.target.value)}
          placeholder="branch — empty means the default"
          aria-label="Branch"
          spellCheck={false}
        />
      ) : null}

      {!address && listing.isLoading ? <Loading label="Reading folders…" rows={3} /> : null}
      {!address && listing.error ? (
        <ErrorPanel
          error={listing.error}
          onRetry={() => void listing.refetch()}
          retrying={listing.isFetching}
        />
      ) : null}
      {address ? null : listing.data?.directories.length ? (
        <ul data-slot="pick" className={cn(pick, "max-h-[280px]")}>
          {listing.data.directories.map((folder) => (
            <li key={folder.path}>
              <button
                type="button"
                className={pickButton}
                onClick={() => walk(folder.path)}
              >
                <b className={pickName}>{folder.name}</b>
                <ChevronRight size={14} aria-hidden className="self-center text-ink-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : listing.isLoading || listing.isError ? null : (
        <EmptyLine>No folders in here — index this one, or go up.</EmptyLine>
      )}

      {error ? <ErrorPanel error={error} /> : null}
      {address && checkoutError ? <ErrorPanel error={checkoutError} /> : null}

      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-t border-rule-soft pt-3.5">
        {address ? (
          <Button
            type="button"
            variant="primary"
            disabled={fetching}
            onClick={() => onCheckout(typed.trim(), branch.trim() || null)}
          >
            {fetching ? (
              <>
                <Spinner /> Fetching…
              </>
            ) : (
              "Check out and index"
            )}
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            // Indexes the folder whose contents are on screen, never a half-typed line.
            disabled={!here || indexing}
            onClick={() => here && onIndex(here)}
          >
            {indexing ? (
              <>
                <Spinner /> Indexing…
              </>
            ) : (
              "Index this folder"
            )}
          </Button>
        )}
      </div>
    </>
  );
}

/**
 * Where a repository comes from. Browsing happens on the server, which is the same machine:
 * a browser's native folder picker hands over a name and some bytes, never a location on disk.
 *
 * Ordinarily dismissable, unlike the layer a case is written on — nothing in here is anyone's
 * writing, so Escape and the backdrop cost at most one directory of walking.
 */
function FolderPicker({
  open,
  onOpenChange,
  disabled,
  start,
  indexing,
  error,
  onIndex,
  fetching,
  checkoutError,
  onCheckout,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled: boolean;
  start: string | null;
  indexing: boolean;
  error: unknown;
  onIndex: (root: string) => void;
  fetching: boolean;
  checkoutError: unknown;
  onCheckout: (url: string, branch: string | null) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="icon"
          disabled={disabled}
          aria-label="Browse local folders"
          title="Browse local folders"
        >
          <FolderOpen size={14} aria-hidden />
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-[560px]"
        // Top-aligned, not centred: the list changes height on every folder walked into, and
        // centring would slide the controls out from under the pointer each time.
        overlayClassName="items-start py-[12vh]"
      >
        <DialogHeader>
          <DialogTitle>Add a repository</DialogTitle>
          <DialogDescription>
            Browse to a local Python project — or paste a path, or a git address. An
            address is cloned into this workspace and kept fresh on later visits; parsing
            reads the code without importing or modifying it.
          </DialogDescription>
        </DialogHeader>
        <FolderBrowser
          start={start}
          indexing={indexing}
          error={error}
          onIndex={onIndex}
          fetching={fetching}
          checkoutError={checkoutError}
          onCheckout={onCheckout}
        />
      </DialogContent>
    </Dialog>
  );
}

export function StartPage() {
  const client = useQueryClient();
  const [repositoryRoot, setRepositoryRoot] = useState<string | null>(null);
  const [path, setPath] = useState("");
  // Held here rather than inside the picker: a successful index is what closes it, and the
  // mutation is this page's.
  const [picking, setPicking] = useState(false);

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const examples = useQuery({ queryKey: ["examples"], queryFn: api.examples });

  const indexed = useMemo(
    () => latestPerRepository(repositories.data || []),
    [repositories.data],
  );

  /**
   * A single indexed repository is not a choice to make. The atlas is substrate (master
   * plan §9.2) and the user's concept here is "my repo". A case is never pre-filled: it
   * is the input that decides the answer, and choosing one for someone would put a
   * verdict behind a case they never read.
   */
  useEffect(() => {
    if (!repositoryRoot && indexed.length === 1) {
      setRepositoryRoot(indexed[0].root_path);
    }
  }, [indexed, repositoryRoot]);

  const index = useMutation({
    mutationFn: (root: string) => api.indexRepository(root),
    onSuccess: async (version) => {
      // Only success closes the picker; a refusal leaves it open on the folder that failed.
      setPicking(false);
      setPath("");
      setRepositoryRoot(version.root_path);
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  // Checking out is two steps worn as one: fetch the address, then index what landed.
  // The reader asked to review a repository, not to perform the halves — and only the
  // second half produces the atlas the rest of this page works from.
  const checkout = useMutation({
    mutationFn: async ({ url, branch }: { url: string; branch: string | null }) => {
      const fetched = await api.checkoutRepository(url, branch);
      return api.indexRepository(fetched.root_path);
    },
    onSuccess: async (version) => {
      setPicking(false);
      setRepositoryRoot(version.root_path);
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  // An example brings a repository and nothing else. It takes the identical path a
  // folder-picked project takes from here on: run, be asked, answer — which is the flow
  // the examples exist to show.
  const loadExample = useMutation({
    mutationFn: async (example: BundledExample) => {
      const version = await api.loadExample(example.name);
      return { root: version.root_path };
    },
    onSuccess: async (indexed) => {
      setRepositoryRoot(indexed.root);
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  // The start step starts the run and stops being involved. The review's page is where a
  // run is watched, and it can be reached — and reloaded, and left — before the first
  // verdict, because the stream announces the review's identity before the first model call.
  const run = useRun();

  // Index, open an empty case about it, and go straight to the review — the whole first
  // step for someone who has not written a case (master plan §6C.1). The questions the run
  // comes back with are how the case gets written, so requiring one first would put the
  // price ahead of the value.
  const reviewRepository = useMutation({
    mutationFn: async (root: string) => {
      // A managed checkout is brought current first, exactly as the review page's New
      // revision does: "run a review" means the repository's code, not whatever the clone
      // last held. Anyone else's working copy comes back managed:false untouched, so this
      // is safe to ask unconditionally.
      await api.refreshRepository(root);
      const revision = await api.startFromRepository(root);
      if (!revision.case_id) {
        throw new Error("The workspace returned a case without an identifier.");
      }
      return { caseId: revision.case_id, root };
    },
    onSuccess: async (started) => {
      setPath("");
      setRepositoryRoot(started.root);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["cases"] }),
        client.invalidateQueries({ queryKey: ["repositories"] }),
      ]);
      run.start(started.caseId, started.root);
    },
  });

  // What Run does with the selection lives in `start-selection`, checkable without
  // rendering anything. This component holds the state; it decides none of the rules.
  const selection: StartSelection = { repositoryRoot, path };

  // The two lists this screen reads come from one server, so when it stops answering they
  // stop together. Reported once, above the columns, rather than as the same sentence
  // twice over. Failures of the *actions* below stay where the action was asked for: those
  // are genuinely separate, and which one refused is the whole content of the message.
  // The retry re-runs the one that failed, not both: when they stop together the first
  // re-read is enough to prove the server is back.
  const readFailure = [repositories, examples].find((query) => query.error);
  const reading = readFailure?.error;

  // The model is chosen in the top bar and outlives this page, but a run needs one, so this
  // step has to say so rather than let the request be refused after the button is pressed.
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const hasModel = Boolean(workspace.data?.models.reasoning);
  // The hosted demo has no folders worth walking: the server refuses to browse its own
  // filesystem, so offering the picker would offer a control whose every click is a 403.
  // The bundled examples are the whole repertoire there, and the copy says so.
  const hosted = Boolean(workspace.data?.hosted);
  // Which hosts this workspace will fetch a repository from. Empty on a local workspace,
  // which clones from wherever its git can reach — and empty on a hosted one that was not
  // given any, where the examples remain the whole repertoire.
  const sourceHosts = workspace.data?.source_hosts ?? [];
  // The line is offered wherever something can come of typing in it. Locally that is always;
  // on the demo it is exactly when the server named hosts it will fetch from, because there
  // the only alternative to a fetch is a 403 the reader had no way to predict.
  //
  // Withheld until the workspace has answered, rather than assumed and corrected. The
  // default before an answer is "not hosted", so assuming would put the field on screen and
  // then take it away again on a demo that has no hosts — and a control that appears and
  // vanishes reads as something breaking, where a beat of nothing reads as loading.
  const canAddRepository = !workspace.isPending && (!hosted || sourceHosts.length > 0);
  const openPicker = useModelPicker();

  const ready = isReady(selection, hasModel);
  const busy =
    run.running ||
    loadExample.isPending ||
    index.isPending ||
    checkout.isPending ||
    reviewRepository.isPending;

  return (
    <div className={page}>
      <PageHeader
        title="Start a review"
        meta={
          <Badge>
            {indexed.length} {indexed.length === 1 ? "repository" : "repositories"} indexed
          </Badge>
        }
      />

      {/* One sheet, not a panel of panels: everything here is one errand. */}
      {/* `minmax(0,1fr)`, not the implicit auto track: auto sizes to the widest child's
          content, and one example pill longer than a phone screen was setting the width
          of the entire sheet. A zero-minimum track makes the sheet the viewport's size
          and leaves each child to truncate inside it. */}
      <section className={cn(sheet, "grid grid-cols-[minmax(0,1fr)]")} aria-label="Start a review">
        {/* Repositories to try, nothing more: an example enters the same flow as any
            folder-picked project — run, be asked, answer — because the asking is what
            these exist to show. */}
        <div
          data-slot="examples"
          className="flex flex-wrap items-center gap-2.5 border-b border-rule-soft px-[var(--card-pad-x)] py-4"
        >
          <span className="text-micro font-[650] tracking-[.08em] uppercase text-ink-3">
            Example repositories
          </span>
          {examples.isLoading ? (
            // One row, at the width of a pill rather than of a table row.
            <Loading
              label="Finding examples…"
              rows={1}
              className="p-0 [&>[data-slot=skeleton-row]]:w-[200px]"
            />
          ) : null}
          {examples.data?.map((example) => (
            <button
              key={example.name}
              type="button"
              className={examplePill}
              disabled={busy}
              onClick={() => loadExample.mutate(example)}
              title={example.description}
            >
              <span className="min-w-0 overflow-hidden text-ellipsis">{example.title}</span>
            </button>
          ))}
          {loadExample.isPending ? (
            <span className="text-meta text-accent-ink">Indexing its repository…</span>
          ) : null}
        </div>
        {reading ? (
          <div className={readError}>
            <ErrorPanel
              error={reading}
              onRetry={() => void readFailure?.refetch()}
              retrying={readFailure?.isFetching}
            />
          </div>
        ) : null}
        {loadExample.isError ? (
          <div className={readError}>
            <ErrorPanel
              error={loadExample.error}
              onRetry={
                loadExample.variables
                  ? () => loadExample.mutate(loadExample.variables!)
                  : undefined
              }
              retrying={loadExample.isPending}
              retryLabel="Load it again"
            />
          </div>
        ) : null}

        {/* One column now. A case is not an input any more — the review writes it from
            your answers, or an example brings its own — so the only thing left to choose
            here is the code. */}
        <div data-slot="start-column" className={startColumn}>
          <div className={startHead}>
            <h3 className="m-0 text-ui font-[650]">Repository</h3>
          </div>
          {/* The way in, first: paste the repository — an address is cloned, a path is
              indexed in place — with browsing kept behind the folder button for the day
              the path isn't on the clipboard. */}
          {canAddRepository ? (
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                const line = path.trim();
                if (!line || busy) return;
                if (looksLikeGitAddress(line)) {
                  checkout.mutate({ url: line, branch: null });
                } else {
                  index.mutate(line);
                }
              }}
            >
              <Input
                className="min-w-0 flex-1 font-mono text-meta"
                value={path}
                onChange={(event) => setPath(event.target.value)}
                placeholder={
                  hosted
                    ? `https://${sourceHosts[0]}/owner/repository`
                    : "https://github.com/owner/repository — or a local path"
                }
                aria-label="Repository address or path"
                spellCheck={false}
              />
              <Button type="submit" variant="primary" disabled={!path.trim() || busy}>
                {checkout.isPending || index.isPending ? (
                  <>
                    <Spinner /> Adding…
                  </>
                ) : (
                  "Add"
                )}
              </Button>
              {/* Browsing is this machine's folders, so it belongs to a workspace that has
                  some: the hosted server refuses to list its own disk. */}
              {hosted ? null : (
                <FolderPicker
                  open={picking}
                  onOpenChange={setPicking}
                  disabled={busy}
                  start={path.trim() || null}
                  indexing={index.isPending}
                  error={index.error}
                  onIndex={(root) => index.mutate(root)}
                  fetching={checkout.isPending}
                  checkoutError={checkout.error}
                  onCheckout={(url, branch) => checkout.mutate({ url, branch })}
                />
              )}
            </form>
          ) : null}
          {canAddRepository && (checkout.error || index.error) && !picking ? (
            <ErrorPanel error={checkout.error || index.error} />
          ) : null}
          <p className={hint}>
            {hosted ? (
              <>
                Public repositories on {listed(sourceHosts)}. The code is downloaded and
                parsed — never imported, installed or run — and the copy goes when your
                session does.
              </>
            ) : (
              <>
                Python is parsed without being imported or modified. Indexing the same path
                again is cheap; freshness is checked before every review.
              </>
            )}
          </p>

          {repositories.isLoading ? (
            <Loading label="Reading indexed repositories…" rows={2} />
          ) : null}
          {indexed.length ? (
            <ul data-slot="pick" className={pick}>
              {indexed.map((repository) => (
                <li key={repository.version_id}>
                  <button
                    type="button"
                    className={pickButton}
                    aria-pressed={repositoryRoot === repository.root_path}
                    onClick={() => setRepositoryRoot(repository.root_path)}
                  >
                    <b className={pickName}>
                      {repository.root_path.split("/").at(-1)}
                    </b>
                    <Badge className="self-center">
                      {repository.node_count} nodes
                    </Badge>
                    <span className={pickWhere}>{repository.root_path}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : repositories.isLoading || repositories.isError ? null : (
            // Only when the list genuinely arrived empty. A list that failed to arrive is
            // not an empty one, and saying "nothing indexed yet" over a failed read is
            // this page telling the reader something it does not know.
            <EmptyLine>
              {!canAddRepository
                ? "Nothing indexed yet — load an example above."
                : hosted
                  ? "Nothing indexed yet — paste a repository above, or load an example."
                  : "Nothing indexed yet — browse to a local Python project below, or load an example above."}
            </EmptyLine>
          )}

        </div>

        {/* Pinned to the foot of the sheet and never scrolled away from: the one control
            that commits anything, beside the sentence saying exactly what it will do. */}
        <div
          data-slot="commit"
          className="flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-b-panel border-t border-rule bg-sunken px-[var(--card-pad-x)] py-4"
        >
          <p className="m-0 flex-[1_1_32ch] text-meta leading-[1.5] text-ink-2 [&_strong]:font-[650] [&_strong]:text-ink">
            {!selection.repositoryRoot ? (
              <>Choose or index a repository to run.</>
            ) : !hasModel ? (
              <>
                No reasoning model is chosen.{" "}
                <button
                  type="button"
                  onClick={() => openPicker?.()}
                  className="font-[650] text-primary underline underline-offset-2"
                >
                  Choose a model
                </button>{" "}
                to run — only models a reachable provider currently has are offered.
              </>
            ) : (
              <>
                Judging every boundary in{" "}
                <strong>{repositoryRoot?.split("/").at(-1)}</strong> on the code alone, with
                no case written. The review will ask what it could not weigh, and your
                answers become the case.
              </>
            )}
          </p>
          <Button
            type="button"
            variant="primary"
            disabled={!ready || busy}
            onClick={() => {
              const intent = runIntent(selection, hasModel);
              if (intent === null) return;
              reviewRepository.mutate(intent.repositoryRoot);
            }}
          >
            {busy ? <Spinner /> : <Play size={15} aria-hidden />}
            {busy ? "Starting…" : "Run review"}
          </Button>
          {/* A failure before the stream opens never reaches the review's page, because
              there is no review to reach. It is reported where the run was asked for. */}
          {run.error || reviewRepository.error ? (
            <div className="flex-[1_1_100%] [&_[data-slot=error-strip]]:my-0">
              <ErrorPanel error={run.error || reviewRepository.error} />
            </div>
          ) : null}
        </div>
      </section>

      {/* A pointer, not a listing. Past reviews are a standing record with its own place in
          the navigation; what belongs here is the way back to them after a run, in one
          line that cannot grow. */}
      {reviews.data?.length ? (
        <Link
          className="mt-1 inline-flex items-center gap-1 text-meta text-accent-ink hover:underline"
          to="/reviews"
        >
          {reviews.data.length} {reviews.data.length === 1 ? "review" : "reviews"} in this
          workspace <ArrowRight size={13} aria-hidden />
        </Link>
      ) : null}

    </div>
  );
}
