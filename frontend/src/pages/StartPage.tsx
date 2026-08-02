import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUp,
  ChevronRight,
  FlaskConical,
  FolderOpen,
  Play,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
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
import { CaseView } from "../case-view";
import { EmptyLine, ErrorPanel, Loading, PageHeader, page, sheet } from "../components";
import { useModelPicker } from "../model-picker";
import { latestPerRepository } from "../repositories";
import { useRun } from "../run";
import {
  chooseCase as pickCase,
  isReady,
  runIntent,
  type StartSelection,
} from "../start-selection";
import type { BundledCase, CaseSummary } from "../types";

/**
 * The floating layer a stored case is read on.
 *
 * A case is prose — eleven fields of it — and rendering that inline pushed the two pickers
 * and the run bar off the screen the moment anyone opened it, so the step you were in the
 * middle of disappeared while you did a different one. It floats instead: the start screen
 * stays behind it, unmoved, and closing puts the reader back exactly where they were.
 *
 * This layer once carried a case being *written*, and with it two refusals — Escape and the
 * backdrop would not dismiss half-written prose. Authoring moved into the review itself (a
 * run without a case asks, and the answers become the case), so nothing shown here can be
 * lost any more and both dismissals do what a reader expects of them.
 *
 * The one thing the dialog primitive cannot do here is give the focus back. A modal dialog
 * returns it to its own `DialogTrigger`, and there is none: this layer is rendered from
 * state. So the control that opened it is remembered by the page and handed back, because
 * putting the reader back exactly where they were is the whole promise of a surface that
 * floats over a step rather than replacing it.
 */
export function CaseLayer({
  label,
  opener,
  onClose,
  children,
}: {
  label: string;
  opener: React.RefObject<HTMLElement | null>;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent
        data-slot="case-layer"
        aria-label={label}
        // The surface inside has its own way out, in its own head, beside its own heading.
        showCloseButton={false}
        // Not centred: a case is taller than the window, and a form that starts halfway down
        // a scroller opens on its own middle.
        overlayClassName="items-start px-[var(--gutter)] py-6"
        className="max-w-[880px] gap-0 p-0"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          opener.current?.focus();
        }}
      >
        {children}
      </DialogContent>
    </Dialog>
  );
}

/* A short list of things to pick from, at the density of a list rather than of a card wall:
   name, one fact about it, and the path or sentence that tells two of them apart.
   `aria-pressed` is the whole state — a case can be un-picked. */
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
/* A path is this product's material and wears the mono face; a problem statement is a
   sentence someone wrote, and setting prose in mono makes it look like a value. */
const pickProse = "col-span-full overflow-hidden text-meta text-ellipsis whitespace-nowrap text-ink-3";
/* An example is a pill rather than a button: it fills both rails at once, which is a thing
   to take rather than an action to perform. */
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
/* A read that failed is reported once, above both columns, inside the sheet's own gutter. */
const readError = "px-[var(--card-pad-x)] [&_[data-slot=error-strip]]:mt-3 [&_[data-slot=error-strip]]:mb-0";

/**
 * Walking the machine's folders to find the one to index. State lives here, not on the page,
 * so the dialog unmounting it resets the walk.
 */
function FolderBrowser({
  start,
  indexing,
  error,
  onIndex,
}: {
  /** Where to open: a repository some case named, or the home folder where `null` lands. */
  start: string | null;
  indexing: boolean;
  error: unknown;
  onIndex: (root: string) => void;
}) {
  const [at, setAt] = useState<string | null>(start);
  const [typed, setTyped] = useState(start ?? "");
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
          go();
        }}
      >
        <Button
          type="button"
          size="icon"
          aria-label="Go up to the parent folder"
          // A null parent is the server saying there is nowhere above this; nothing here
          // counts slashes to work that out.
          disabled={!listing.data?.parent}
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
          aria-label="Folder path"
          spellCheck={false}
        />
        <Button type="submit" disabled={!typed.trim()}>
          Go
        </Button>
      </form>

      {listing.isLoading ? <Loading label="Reading folders…" rows={3} /> : null}
      {listing.error ? (
        <ErrorPanel
          error={listing.error}
          onRetry={() => void listing.refetch()}
          retrying={listing.isFetching}
        />
      ) : null}
      {listing.data?.directories.length ? (
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

      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-t border-rule-soft pt-3.5">
        <Button
          type="button"
          variant="primary"
          // Indexes the folder whose contents are on screen, never a half-typed line.
          disabled={!here || indexing}
          onClick={() => here && onIndex(here)}
        >
          {indexing ? "Indexing…" : "Index this folder"}
        </Button>
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
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled: boolean;
  start: string | null;
  indexing: boolean;
  error: unknown;
  onIndex: (root: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" disabled={disabled}>
          <FolderOpen size={14} aria-hidden />
          Index a folder…
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-[560px]"
        // Top-aligned, not centred: the list changes height on every folder walked into, and
        // centring would slide the controls out from under the pointer each time.
        overlayClassName="items-start py-[12vh]"
      >
        <DialogHeader>
          <DialogTitle>Index a folder</DialogTitle>
          <DialogDescription>
            Browse to the root of a local Python project, or paste its path. Parsing reads
            the code without importing or modifying it.
          </DialogDescription>
        </DialogHeader>
        <FolderBrowser
          start={start}
          indexing={indexing}
          error={error}
          onIndex={onIndex}
        />
      </DialogContent>
    </Dialog>
  );
}

export function StartPage() {
  const client = useQueryClient();
  const [repositoryRoot, setRepositoryRoot] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [path, setPath] = useState("");
  // The case whose stored revision is open for reading, if any.
  const [viewing, setViewing] = useState<string | null>(null);
  // Held here rather than inside the picker: a successful index is what closes it, and the
  // mutation is this page's.
  const [picking, setPicking] = useState(false);
  // Read at the click rather than at the layer's mount: the layer re-mounts when the stored
  // case arrives, and by then focus is already inside it.
  const opener = useRef<HTMLElement | null>(null);
  const openView = useCallback((caseId: string) => {
    opener.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setViewing(caseId);
  }, []);
  const closeView = useCallback(() => setViewing(null), []);

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const examples = useQuery({ queryKey: ["bundled-cases"], queryFn: api.bundledCases });
  // The stored revision behind the open panel, not the summary the picker shows.
  const viewed = useQuery({
    queryKey: ["case", viewing],
    queryFn: () => api.case(viewing!),
    enabled: Boolean(viewing),
  });

  const indexed = useMemo(
    () => latestPerRepository(repositories.data || []),
    [repositories.data],
  );
  const chosenCase = (cases.data || []).find((item) => item.case_id === caseId) || null;
  const indexedRoots = useMemo(
    () => indexed.map((repository) => repository.root_path),
    [indexed],
  );

  /**
   * A single indexed repository is not a choice to make. The atlas is substrate (master
   * plan §9.2) and the user's concept here is "my repo". The case is deliberately not
   * pre-filled however many exist: it is the input that decides the answer, and choosing
   * it for someone would put a verdict behind a case they never read.
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

  const loadExample = useMutation({
    mutationFn: async (example: BundledCase) => {
      const revision = await api.loadBundledCase(example.name);
      return { caseId: revision.case_id, root: example.repository_root };
    },
    onSuccess: async (filled) => {
      setCaseId(filled.caseId);
      setRepositoryRoot(filled.root);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["cases"] }),
        client.invalidateQueries({ queryKey: ["repositories"] }),
      ]);
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
      const revision = await api.startFromRepository(root);
      if (!revision.case_id) {
        throw new Error("The workspace returned a case without an identifier.");
      }
      return { caseId: revision.case_id, root };
    },
    onSuccess: async (started) => {
      setPath("");
      setCaseId(started.caseId);
      setRepositoryRoot(started.root);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["cases"] }),
        client.invalidateQueries({ queryKey: ["repositories"] }),
      ]);
      run.start(started.caseId, started.root);
    },
  });

  // Which rail a choice fills, what it leaves alone, and what Run then does all live in
  // `start-selection`, where they are checkable without rendering anything. This component
  // holds the state and applies the result; it decides none of the rules.
  const selection: StartSelection = { repositoryRoot, caseId, path };

  function apply(next: StartSelection) {
    setRepositoryRoot(next.repositoryRoot);
    setCaseId(next.caseId);
    setPath(next.path);
  }

  const chooseCase = (item: CaseSummary) => {
    apply(pickCase(selection, item, indexedRoots));
  };

  // The three lists this screen reads come from one server, so when it stops answering they
  // stop together. Reported once, above both columns, rather than as the same sentence three
  // times over. Failures of the *actions* below stay where the action was asked for: those
  // are genuinely separate, and which one refused is the whole content of the message.
  // The second attempt is the one that failed, not all three: when they stop together the
  // first re-read is enough to prove the server is back, and re-running the two that were
  // fine would only make the strip slower to leave.
  const readFailure = [repositories, cases, examples].find((query) => query.error);
  const reading = readFailure?.error;

  // The model is chosen in the top bar and outlives this page, but a run needs one, so this
  // step has to say so rather than let the request be refused after the button is pressed.
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const hasModel = Boolean(workspace.data?.models.reasoning);
  // The hosted demo has no folders worth walking: the server refuses to browse its own
  // filesystem, so offering the picker would offer a control whose every click is a 403.
  // The bundled examples are the whole repertoire there, and the copy says so.
  const hosted = Boolean(workspace.data?.hosted);
  const openPicker = useModelPicker();

  const ready = isReady(selection, hasModel);
  const busy =
    run.running || loadExample.isPending || index.isPending || reviewRepository.isPending;

  return (
    <div className={page}>
      <PageHeader
        title="Start a review"
        meta={
          <Badge>
            {indexed.length} indexed · {cases.data?.length || 0}{" "}
            {cases.data?.length === 1 ? "case" : "cases"}
          </Badge>
        }
      />

      {/* One sheet, not a panel of panels. The two inputs are the same kind of thing —
          pick one from a short list — and giving each its own bordered box said they were
          two separate errands rather than two halves of one. */}
      {/* `minmax(0,1fr)`, not the implicit auto track: auto sizes to the widest child's
          content, and one example pill longer than a phone screen was setting the width
          of the entire sheet. A zero-minimum track makes the sheet the viewport's size
          and leaves each child to truncate inside it. */}
      <section className={cn(sheet, "grid grid-cols-[minmax(0,1fr)]")} aria-label="Start a review">
        {/* Both rails at once, which is what makes an example an example: a repository
            already parsed and a case already written, so the first run is a real one. */}
        <div
          data-slot="examples"
          className="flex flex-wrap items-center gap-2.5 border-b border-rule-soft px-[var(--card-pad-x)] py-4"
        >
          <span className="text-micro font-[650] tracking-[.08em] uppercase text-ink-3">
            Examples fill both rails
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
              title={example.problem_statement}
            >
              <span className="min-w-0 overflow-hidden text-ellipsis">{example.title}</span>
              {/* The badge survives whole and the title gives way: "scored" is the fact
                  that distinguishes this pill, and the title's tail is recoverable from
                  the tooltip where a cut badge would just be a smudge. */}
              {example.has_expected_answers ? (
                <Badge variant="accent" className="flex-none px-1.5 py-0">
                  <FlaskConical size={11} aria-hidden /> scored
                </Badge>
              ) : null}
            </button>
          ))}
          {loadExample.isPending ? (
            <span className="text-meta text-accent-ink">
              Indexing its repository and creating its case…
            </span>
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

        {/* Side by side and equal, because neither input depends on the other — a wizard
            would impose an order the flow does not have. They stack once the pair is
            narrower than two columns of prose, and the rule between them turns to run
            across. */}
        <div className="grid grid-cols-2 max-[1050px]:grid-cols-1">
          <div data-slot="start-column" className={startColumn}>
            <div className={startHead}>
              <h3 className="m-0 text-ui font-[650]">Repository</h3>
            </div>
            <p className={hint}>
              Python is parsed without being imported or modified. Indexing the same path
              again is cheap; freshness is checked before every review.
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
                {hosted
                  ? "Nothing indexed yet — load an example above."
                  : "Nothing indexed yet — browse to a local Python project below, or load an example above."}
              </EmptyLine>
            )}

            {!hosted ? (
              <div className="flex flex-wrap gap-2">
                <FolderPicker
                  open={picking}
                  onOpenChange={setPicking}
                  disabled={busy}
                  // A repository some case named that nothing has parsed yet: the picker
                  // opens there so the reader confirms the folder rather than finding it
                  // again.
                  start={path.trim() || null}
                  indexing={index.isPending}
                  error={index.error}
                  onIndex={(root) => index.mutate(root)}
                />
              </div>
            ) : null}
          </div>

          {/* The rule between the two columns lives on the second of them, and turns to run
              across it once they stack. */}
          <div
            data-slot="start-column"
            className={cn(
              startColumn,
              "border-l border-rule-soft max-[1050px]:border-t max-[1050px]:border-l-0",
            )}
          >
            <div className={startHead}>
              <h3 className="m-0 text-ui font-[650]">Case</h3>
              <Badge className="ml-auto">optional</Badge>
            </div>
            {/* Nothing here authors a case, deliberately. There used to be a form, and its
                correct use was almost always "skip it": the review runs without a case and
                asks what it could not weigh, and the answers are how a case gets written
                (master plan §6C.1). What this rail offers is the cases that already exist —
                shaped by earlier reviews or loaded from an example — to run against again. */}
            <p className={hint}>
              A case is written by the review itself: run without one and it asks what it
              could not weigh — your answers become the case. Pick one here only to judge
              against a case an earlier review already shaped.
            </p>

            {cases.isLoading ? <Loading label="Reading cases…" rows={2} /> : null}
            {cases.data?.length ? (
              // The second line here is a sentence, not a path, so it is not set in the
              // mono face — that face carries this product's material: names, refs, paths.
              <ul data-slot="pick" data-prose="true" className={pick}>
                {cases.data.map((item) => (
                  <li key={item.case_id}>
                    <button
                      type="button"
                      className={pickButton}
                      aria-pressed={caseId === item.case_id}
                      onClick={() => chooseCase(item)}
                    >
                      <b className={pickName}>{item.title}</b>
                      <Badge className="self-center">rev {item.revision}</Badge>
                      <span className={pickProse}>{item.problem_statement}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : cases.isLoading || cases.isError ? null : (
              <EmptyLine>
                No cases yet — run a review and its questions will write one, or load a
                bundled example above to see what a filled-in case looks like.
              </EmptyLine>
            )}

            {caseId ? (
              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={() => openView(caseId)}>
                  View
                </Button>
              </div>
            ) : null}
          </div>
        </div>

        {/* Pinned to the foot of the sheet and never scrolled away from: the one control
            that commits anything, beside the sentence saying exactly what it will do. */}
        <div
          data-slot="commit"
          className="flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-b-panel border-t border-rule bg-sunken px-[var(--card-pad-x)] py-4"
        >
          <p className="m-0 flex-[1_1_32ch] text-meta leading-[1.5] text-ink-2 [&_strong]:font-[650] [&_strong]:text-ink">
            {!selection.repositoryRoot ? (
              <>Choose or index a repository to run. A case is optional.</>
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
            ) : caseId ? (
              <>
                Judging every boundary in{" "}
                <strong>{repositoryRoot?.split("/").at(-1)}</strong> against{" "}
                <strong>{chosenCase?.title}</strong>. This opens the review and follows it
                there.
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
              // One run, two ways in, decided in one place rather than re-derived here: a
              // chosen case is reviewed against, and no case opens an empty one about this
              // repository first.
              const intent = runIntent(selection, hasModel);
              if (intent === null) return;
              if (intent.kind === "against-case") {
                run.start(intent.caseId, intent.repositoryRoot);
              } else {
                reviewRepository.mutate(intent.repositoryRoot);
              }
            }}
          >
            <Play size={15} aria-hidden />
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

      {viewing ? (
        <CaseLayer opener={opener} label="The case, as stored" onClose={closeView}>
          <CaseView
            snapshot={viewed.data?.snapshot}
            loading={viewed.isLoading}
            error={viewed.error}
            onRetry={() => void viewed.refetch()}
            retrying={viewed.isFetching}
            onClose={closeView}
          />
        </CaseLayer>
      ) : null}
    </div>
  );
}
