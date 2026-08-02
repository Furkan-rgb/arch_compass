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
import { CaseEditor, CaseView } from "../case-editor";
import { CaseForm, casePayload, type CaseFormValues } from "../case-form";
import { EmptyLine, ErrorPanel, Loading, PageHeader, page, sheet } from "../components";
import { useModelPicker } from "../model-picker";
import { latestPerRepository } from "../repositories";
import { useRun } from "../run";
import {
  applyRepositoryHint as hintRepository,
  chooseCase as pickCase,
  isReady,
  runIntent,
  type StartSelection,
} from "../start-selection";
import type { BundledCase, CaseRevision, CaseSummary } from "../types";

/** Which case surface is open, if any: writing a new one, or reading a stored one. */
type Editor =
  | { mode: "form" }
  | { mode: "revise"; caseId: string }
  | { mode: "yaml" }
  | { mode: "view"; caseId: string }
  | null;

/**
 * The floating layer a case is written on.
 *
 * A case is prose — eleven fields of it — and rendering that inline pushed the two pickers
 * and the run bar off the screen the moment anyone opened it, so the step you were in the
 * middle of disappeared while you did a different one. It floats instead: the start screen
 * stays behind it, unmoved, and closing puts the reader back exactly where they were.
 *
 * Deliberately not dismissed by a click on the backdrop. Everywhere else in this app that is
 * the courteous behaviour, but here the thing behind the click is half-written prose, and a
 * stray click is not a decision to throw it away. The close button is.
 *
 * Escape was, and should not have been. It is the same dismissal by reflex as the backdrop —
 * pressed to dismiss a suggestion, to leave a field, to make something go away — and it was
 * throwing away a case someone had spent ten minutes writing, in silence, with nothing to
 * undo it. So it is refused on exactly the terms the backdrop is refused on: while `unsaved`
 * says there is writing here that is not in a revision yet, neither one closes this, and the
 * close button beside the heading stays the way out. On a surface nobody has typed into there
 * is nothing to protect, and Escape keeps doing what a reader expects of it.
 *
 * A vendored dialog now, which is where those decisions ended up being cheapest to keep: two
 * prevented events and focus that lands on the close button because that is the first thing in
 * the surface below. It carries no title of its own — the surface inside writes the heading,
 * and saying it twice would have a screen reader read the same words on the way in.
 *
 * The one thing the primitive cannot do here is give the focus back. A modal dialog returns
 * it to its own `DialogTrigger`, and there is none: this layer is rendered from state by any
 * of four buttons. So the control that opened it is remembered by the page and handed back,
 * because putting the reader back exactly where they were is the whole promise of a surface
 * that floats over a step rather than replacing it.
 */
export function CaseLayer({
  label,
  opener,
  unsaved,
  onClose,
  children,
}: {
  label: string;
  opener: React.RefObject<HTMLElement | null>;
  /**
   * True while the surface inside holds writing that has not been saved as a revision.
   *
   * Absent on the surfaces where the question cannot arise — a stored case being read has
   * nothing to lose, and a dismissal of it is only ever a dismissal.
   */
  unsaved?: boolean;
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
        onInteractOutside={(event) => event.preventDefault()}
        // The one hole the backdrop's refusal left. Refused on the same terms and in the same
        // way — the keypress simply does not dismiss — so there is one rule here rather than a
        // second, differently-shaped guard for the same prose.
        onEscapeKeyDown={(event) => {
          if (unsaved) event.preventDefault();
        }}
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
  "inline-flex h-[26px] cursor-pointer items-center gap-2 rounded-pill border border-rule",
  "bg-surface px-3 text-meta whitespace-nowrap text-ink",
  "not-disabled:hover:border-accent-rule not-disabled:hover:bg-accent-soft",
  "disabled:cursor-not-allowed disabled:opacity-55",
);
const startColumn = "grid min-w-0 content-start gap-2.5 px-[22px] pt-4 pb-5";
const startHead = "flex items-baseline gap-2";
const hint = "m-0 text-meta leading-[1.5] text-ink-2";
const note = "m-0 text-meta leading-[1.5] text-ink-3";
/* A read that failed is reported once, above both columns, inside the sheet's own gutter. */
const readError = "px-[22px] [&_[data-slot=error-strip]]:mt-3 [&_[data-slot=error-strip]]:mb-0";

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

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-rule-soft pt-3.5">
        <p className={cn(note, "flex-[1_1_28ch]")}>
          The workspace must not sit inside the project being analysed.
        </p>
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
  const [editor, setEditor] = useState<Editor>(null);
  // Held here rather than inside the picker: a successful index is what closes it, and the
  // mutation is this page's.
  const [picking, setPicking] = useState(false);
  // Read at the click rather than at the layer's mount: the revise layer re-mounts when the
  // stored case arrives, and by then focus is already inside it.
  const opener = useRef<HTMLElement | null>(null);
  // Whether the open surface holds writing that is not in a revision yet. Held here rather
  // than in the layer because the form is the only thing that can tell, and the layer is not
  // its parent: this page renders both, and passing the answer between them is what lets the
  // layer refuse a dismissal without knowing what a case field is.
  const [unsaved, setUnsaved] = useState(false);
  const openEditor = useCallback((next: Editor) => {
    opener.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Every surface opens with nothing written in it. Reset here as well as on the way out,
    // because a form that was closed while dirty unmounts without ever reporting otherwise.
    setUnsaved(false);
    setEditor(next);
  }, []);
  // One stable closure for all four surfaces below. It used to carry more weight than that:
  // the hand-rolled focus trap re-ran — and re-grabbed focus — whenever this handler changed
  // identity, so a fresh closure each render pulled the caret out of the field being typed
  // into on every keystroke. The vendored dialog does not, and this stays anyway.
  const closeEditor = useCallback(() => {
    setUnsaved(false);
    setEditor(null);
  }, []);

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const examples = useQuery({ queryKey: ["bundled-cases"], queryFn: api.bundledCases });
  // The case behind an open panel: read for viewing, and read for revising so the form
  // starts from the stored revision rather than from the summary the picker shows.
  const opened = editor?.mode === "view" || editor?.mode === "revise" ? editor.caseId : null;
  const viewed = useQuery({
    queryKey: ["case", opened],
    queryFn: () => api.case(opened!),
    enabled: Boolean(opened),
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

  const created = async (revision: CaseRevision) => {
    setEditor(null);
    // One selection, derived in one step, exactly as choosing a case from the list is.
    // Setting the case and then applying the repository hint separately did not survive
    // batching: the hint writes the whole selection back, and the one it was computed from
    // still had the previous case in it — so a case authored here was created, listed, and
    // silently left unchosen, with the run bar still offering a run on the code alone.
    apply(
      hintRepository(
        { ...selection, caseId: revision.case_id },
        revision.snapshot?.repository?.root_path,
        indexedRoots,
      ),
    );
    await client.invalidateQueries({ queryKey: ["cases"] });
  };

  const create = useMutation({
    mutationFn: (source: string) => api.importCase(source),
    onSuccess: created,
  });

  const write = useMutation({
    mutationFn: (values: CaseFormValues) => api.createCase(casePayload(values)),
    onSuccess: created,
  });

  const revise = useMutation({
    mutationFn: (values: CaseFormValues) => {
      const target = editor?.mode === "revise" ? editor.caseId : null;
      if (!target) throw new Error("No case is open for revision.");
      return api.updateCase(target, casePayload(values));
    },
    onSuccess: created,
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
      <section className={cn(sheet, "grid")} aria-label="Start a review">
        {/* Both rails at once, which is what makes an example an example: a repository
            already parsed and a case already written, so the first run is a real one. */}
        <div
          data-slot="examples"
          className="flex flex-wrap items-center gap-2.5 border-b border-rule-soft px-[22px] py-4"
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
              <span>{example.title}</span>
              {example.has_expected_answers ? (
                <Badge variant="accent" className="px-1.5 py-0">
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
            {/* Optional, and saying so is the point. A case is what separates a boundary
                that earns its place from one that does not, and it is also the reason
                nobody got as far as a first verdict — so the review runs without one and
                asks for what it lacked instead (master plan §6C.1). */}
            <p className={hint}>
              Skip this and the review runs on the repository alone, then asks what it could
              not weigh — your answers become the case. Pick or write one here only if you
              already know what this software has to do.
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
                No cases yet — write one below, or load a bundled example above to see what
                a filled-in case looks like.
              </EmptyLine>
            )}

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                onClick={() => openEditor({ mode: "form" })}
              >
                New case
              </Button>
              {caseId ? (
                <>
                  <Button
                    type="button"
                    onClick={() => openEditor({ mode: "revise", caseId })}
                  >
                    Revise
                  </Button>
                  <Button
                    type="button"
                    onClick={() => openEditor({ mode: "view", caseId })}
                  >
                    View
                  </Button>
                </>
              ) : null}
              {/* The escape hatch stays: a case someone already has as YAML, or a field the
                  form does not ask for, goes in this way. */}
              <Button
                type="button"
                onClick={() => openEditor({ mode: "yaml" })}
              >
                Paste YAML
              </Button>
            </div>
          </div>
        </div>

        {/* Pinned to the foot of the sheet and never scrolled away from: the one control
            that commits anything, beside the sentence saying exactly what it will do. */}
        <div
          data-slot="commit"
          className="flex flex-wrap items-center gap-x-4 gap-y-2.5 rounded-b-panel border-t border-rule bg-sunken px-[22px] py-4"
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

      {editor?.mode === "form" ? (
        <CaseLayer
          opener={opener}
          label="Write a case"
          unsaved={unsaved}
          onClose={closeEditor}
        >
          <CaseForm
            heading="Write a case"
            initial={undefined}
            submitLabel="Create the case"
            pendingLabel="Creating…"
            pending={write.isPending}
            error={write.error}
            onSubmit={(values) => write.mutate(values)}
            onClose={closeEditor}
            onDirtyChange={setUnsaved}
          />
        </CaseLayer>
      ) : null}
      {editor?.mode === "revise" ? (
        // Keyed by revision so the form re-mounts with the loaded case as its defaults
        // rather than holding the empty values it was first built with. The key sits on the
        // layer rather than on the form so that the re-mount takes the focus trap with it —
        // keyed on the form alone, the element focus was resting on is replaced underneath
        // it and the dialog stops hearing Escape.
        <CaseLayer
          key={`${editor.caseId}:${viewed.data?.revision ?? "loading"}`}
          opener={opener}
          label="Revise this case"
          unsaved={unsaved}
          onClose={closeEditor}
        >
          <CaseForm
            heading="Revise this case"
            initial={viewed.data?.snapshot}
            submitLabel="Save as a new revision"
            pendingLabel="Saving…"
            pending={revise.isPending}
            loading={viewed.isLoading}
            error={viewed.error || revise.error}
            onSubmit={(values) => revise.mutate(values)}
            onClose={closeEditor}
            onDirtyChange={setUnsaved}
            note={
              <p
                data-slot="case-warning"
                className="m-0 border-l-[3px] border-l-material bg-material-soft p-3 text-body leading-[1.55] text-ink [&>strong]:block"
              >
                <strong>Earlier reviews are not affected.</strong> This writes revision{" "}
                {(viewed.data?.revision ?? 0) + 1}; every review that has already run stays
                pinned to the revision it judged.
              </p>
            }
          />
        </CaseLayer>
      ) : null}
      {editor?.mode === "yaml" ? (
        <CaseLayer opener={opener} label="Paste a case as YAML" onClose={closeEditor}>
          <CaseEditor
            pending={create.isPending}
            error={create.error}
            onCreate={(source) => create.mutate(source)}
            onClose={closeEditor}
          />
        </CaseLayer>
      ) : null}
      {editor?.mode === "view" ? (
        <CaseLayer opener={opener} label="The case, as stored" onClose={closeEditor}>
          <CaseView
            snapshot={viewed.data?.snapshot}
            loading={viewed.isLoading}
            error={viewed.error}
            onRetry={() => void viewed.refetch()}
            retrying={viewed.isFetching}
            onClose={closeEditor}
          />
        </CaseLayer>
      ) : null}
    </div>
  );
}
