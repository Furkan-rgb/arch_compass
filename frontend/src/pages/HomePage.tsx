import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Boxes,
  CircleCheck,
  ClipboardList,
  Eye,
  FileCode2,
  FilePlus2,
  FileSearch,
  FlaskConical,
  PencilLine,
  Play,
  Plus,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { CaseEditor, CaseView } from "../case-editor";
import { CaseForm, casePayload, type CaseFormValues } from "../case-form";
import { Badge, ErrorPanel, Loading, PageHeader } from "../components";
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

export function HomePage() {
  const client = useQueryClient();
  const [repositoryRoot, setRepositoryRoot] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [editor, setEditor] = useState<Editor>(null);

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
    setCaseId(revision.case_id);
    applyRepositoryHint(revision.snapshot?.repository?.root_path);
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

  function applyRepositoryHint(root: string | null | undefined) {
    apply(hintRepository(selection, root, indexedRoots));
  }

  const chooseCase = (item: CaseSummary) => {
    apply(pickCase(selection, item, indexedRoots));
  };

  const ready = isReady(selection);
  const busy =
    run.running || loadExample.isPending || index.isPending || reviewRepository.isPending;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Local architecture workspace"
        title="Review a repository against a case."
        description="Every boundary the detector finds, judged one model call at a time against what this software actually has to do."
      />

      <section className="panel">
        <h2 className="panel__title">Start a review</h2>
        <p className="panel__hint">
          Point at a repository and review it. A case says what the software has to do and
          is what separates a boundary that earns its place from one that does not — but you
          do not have to write one first: the review asks for what it could not weigh, and
          your answers become the case.
        </p>

        {examples.isLoading ? <Loading label="Finding examples…" /> : null}
        {examples.isError ? <ErrorPanel error={examples.error} /> : null}
        {examples.data?.length ? (
          <div className="example-strip">
            <span>Bundled examples fill both rails</span>
            {examples.data.map((example) => (
              <button
                key={example.name}
                type="button"
                disabled={busy}
                onClick={() => loadExample.mutate(example)}
                title={example.problem_statement}
              >
                <FileSearch size={15} aria-hidden />
                <span>{example.title}</span>
                {example.has_expected_answers ? (
                  <Badge tone="teal">
                    <FlaskConical size={13} aria-hidden /> scored
                  </Badge>
                ) : null}
              </button>
            ))}
          </div>
        ) : null}
        {loadExample.isPending ? (
          <p className="panel__notice">
            Loading the example: indexing its repository and creating its case.
          </p>
        ) : null}
        {loadExample.isError ? <ErrorPanel error={loadExample.error} /> : null}

        <div className="rails">
          <div className={`rail ${repositoryRoot ? "rail--filled" : ""}`}>
            <div className="rail__head">
              <span className="rail__step">A</span>
              <h3>Repository</h3>
              {repositoryRoot ? (
                <CircleCheck className="rail__done" size={17} aria-label="Chosen" />
              ) : null}
            </div>
            <p className="rail__hint">
              Python is parsed without being imported or modified. Indexing the same path
              again is cheap; freshness is checked before every review.
            </p>

            {repositories.isLoading ? <Loading label="Reading indexed repositories…" /> : null}
            {repositories.isError ? <ErrorPanel error={repositories.error} /> : null}
            {indexed.length ? (
              <div className="repository-list">
                {indexed.map((repository) => (
                  <button
                    type="button"
                    key={repository.version_id}
                    aria-pressed={repositoryRoot === repository.root_path}
                    onClick={() => setRepositoryRoot(repository.root_path)}
                    className={`repository-card ${
                      repositoryRoot === repository.root_path ? "repository-card--active" : ""
                    }`}
                  >
                    <span className="repo-glyph">
                      <Boxes size={17} aria-hidden />
                    </span>
                    <span>
                      <strong>{repository.root_path.split("/").at(-1)}</strong>
                      <small>{repository.root_path}</small>
                    </span>
                    <Badge tone="neutral">{repository.node_count} nodes</Badge>
                  </button>
                ))}
              </div>
            ) : (
              <p className="rail__empty">
                Nothing indexed yet. Point at a local Python project below, or load an
                example above.
              </p>
            )}

            <label className="rail__field">
              <span>Index a new path</span>
              <input
                value={path}
                onChange={(event) => setPath(event.target.value)}
                placeholder="/absolute/path/to/python-project"
                aria-label="Local repository path"
              />
            </label>
            <button
              type="button"
              className="button button--secondary"
              disabled={!path.trim() || busy}
              onClick={() => index.mutate(path.trim())}
            >
              <Plus size={15} aria-hidden />
              {index.isPending ? "Indexing…" : "Index this path"}
            </button>
            <p className="rail__note">
              The workspace must not sit inside the project being analysed.
            </p>
            {index.isError ? <ErrorPanel error={index.error} /> : null}
          </div>

          <div className={`rail ${caseId ? "rail--filled" : ""}`}>
            <div className="rail__head">
              <span className="rail__step rail__step--optional">B</span>
              <h3>Case</h3>
              <span className="rail__optional">optional</span>
              {caseId ? (
                <CircleCheck className="rail__done" size={17} aria-label="Chosen" />
              ) : null}
            </div>
            {/* Optional, and saying so is the point. A case is what separates a boundary
                that earns its place from one that does not, and it is also the reason
                nobody got as far as a first verdict — so the review runs without one and
                asks for what it lacked instead (master plan §6C.1). */}
            <p className="rail__hint">
              Skip this and the review runs on the repository alone, then asks what it could
              not weigh — your answers become the case. Pick or write one here only if you
              already know what this software has to do.
            </p>

            {cases.isLoading ? <Loading label="Reading cases…" /> : null}
            {cases.isError ? <ErrorPanel error={cases.error} /> : null}
            {cases.data?.length ? (
              <div className="repository-list">
                {cases.data.map((item) => (
                  <button
                    type="button"
                    key={item.case_id}
                    aria-pressed={caseId === item.case_id}
                    onClick={() => chooseCase(item)}
                    className={`repository-card ${
                      caseId === item.case_id ? "repository-card--active" : ""
                    }`}
                  >
                    <span className="repo-glyph">
                      <FileSearch size={17} aria-hidden />
                    </span>
                    <span>
                      <strong>{item.title}</strong>
                      <small>{item.problem_statement}</small>
                    </span>
                    <Badge tone="neutral">rev {item.revision}</Badge>
                  </button>
                ))}
              </div>
            ) : (
              <p className="rail__empty">
                No cases yet. Write one below, or load a bundled example above to see what
                a filled-in case looks like.
              </p>
            )}

            <div className="rail__actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setEditor({ mode: "form" })}
              >
                <FilePlus2 size={15} aria-hidden /> New case
              </button>
              {caseId ? (
                <>
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => setEditor({ mode: "revise", caseId })}
                  >
                    <PencilLine size={15} aria-hidden /> Revise this case
                  </button>
                  <button
                    type="button"
                    className="button button--quiet"
                    onClick={() => setEditor({ mode: "view", caseId })}
                  >
                    <Eye size={15} aria-hidden /> View
                  </button>
                </>
              ) : null}
              {/* The escape hatch stays: a case someone already has as YAML, or a field the
                  form does not ask for, goes in this way. */}
              <button
                type="button"
                className="button button--quiet"
                onClick={() => setEditor({ mode: "yaml" })}
              >
                <FileCode2 size={15} aria-hidden /> Paste YAML
              </button>
            </div>
          </div>
        </div>

        {/* Full width rather than inside the rail: a case is prose, and half a rail is not
            enough of a line to write it on. */}
        {editor?.mode === "form" ? (
          <CaseForm
            heading="Write a case"
            initial={undefined}
            submitLabel="Create the case"
            pendingLabel="Creating…"
            pending={write.isPending}
            error={write.error}
            onSubmit={(values) => write.mutate(values)}
            onClose={() => setEditor(null)}
          />
        ) : null}
        {editor?.mode === "revise" ? (
          <CaseForm
            // Keyed by revision so the form re-mounts with the loaded case as its defaults
            // rather than holding the empty values it was first built with.
            key={`${editor.caseId}:${viewed.data?.revision ?? "loading"}`}
            heading="Revise this case"
            initial={viewed.data?.snapshot}
            submitLabel="Save as a new revision"
            pendingLabel="Saving…"
            pending={revise.isPending}
            loading={viewed.isLoading}
            error={viewed.error || revise.error}
            onSubmit={(values) => revise.mutate(values)}
            onClose={() => setEditor(null)}
            note={
              <p className="case-editor__warning">
                <strong>Earlier reviews are not affected.</strong> This writes revision{" "}
                {(viewed.data?.revision ?? 0) + 1}; every review that has already run stays
                pinned to the revision it judged.
              </p>
            }
          />
        ) : null}
        {editor?.mode === "yaml" ? (
          <CaseEditor
            pending={create.isPending}
            error={create.error}
            onCreate={(source) => create.mutate(source)}
            onClose={() => setEditor(null)}
          />
        ) : null}
        {editor?.mode === "view" ? (
          <CaseView
            snapshot={viewed.data?.snapshot}
            loading={viewed.isLoading}
            error={viewed.error}
            onClose={() => setEditor(null)}
          />
        ) : null}

        <div className="start__run">
          <button
            type="button"
            className="button button--primary"
            disabled={!ready || busy}
            onClick={() => {
              // One run, two ways in, decided in one place rather than re-derived here: a
              // chosen case is reviewed against, and no case opens an empty one about this
              // repository first.
              const intent = runIntent(selection);
              if (intent === null) return;
              if (intent.kind === "against-case") {
                run.start(intent.caseId, intent.repositoryRoot);
              } else {
                reviewRepository.mutate(intent.repositoryRoot);
              }
            }}
          >
            <Play size={16} aria-hidden />
            {busy ? "Starting…" : "Run review"}
          </button>
          <p>
            {!ready ? (
              <>Choose or index a repository to run. A case is optional.</>
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
        </div>
        {/* A failure before the stream opens never reaches the review's page, because there
            is no review to reach. It is reported where the run was asked for. */}
        {run.error ? <ErrorPanel error={run.error} /> : null}
      </section>

      {/* A pointer, not a listing. Past reviews are a standing record with its own place in
          the navigation; what belongs here is the way back to them after a run, in one
          line that cannot grow. */}
      {reviews.data?.length ? (
        <Link className="text-link home__record" to="/reviews">
          <ClipboardList size={15} aria-hidden />
          {reviews.data.length} {reviews.data.length === 1 ? "review" : "reviews"} in this
          workspace <ArrowRight size={14} aria-hidden />
        </Link>
      ) : null}
    </div>
  );
}
