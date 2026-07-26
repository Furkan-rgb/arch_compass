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
  Network,
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

  /**
   * A case that names an indexed repository fills the other rail too. The case already
   * answers the question the repository rail asks, and making the user answer it again
   * would be asking them to repeat themselves. An unindexed path is offered rather than
   * selected: indexing is a real action with its own failure modes.
   */
  function applyRepositoryHint(root: string | null | undefined) {
    if (!root) return;
    if (indexed.some((repository) => repository.root_path === root)) {
      setRepositoryRoot(root);
    } else if (!path.trim()) {
      setPath(root);
    }
  }

  const chooseCase = (item: CaseSummary) => {
    setCaseId(item.case_id);
    applyRepositoryHint(item.repository_root);
  };

  const ready = Boolean(repositoryRoot && caseId);
  const busy = run.running || loadExample.isPending || index.isPending;

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
          Two inputs, in either order: the repository to examine, and the case that says
          what it has to do. The case is what separates a boundary that earns its place
          from one that does not.
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

            {repositoryRoot ? (
              // The graph explorer is not a destination in its own right (workspace-design
              // §4). It is reachable from here, with a question attached, until findings
              // themselves can open onto it.
              <Link
                className="text-link"
                to={`/repositories?root=${encodeURIComponent(repositoryRoot)}`}
              >
                <Network size={15} aria-hidden /> Explore this atlas <ArrowRight size={14} />
              </Link>
            ) : null}
          </div>

          <div className={`rail ${caseId ? "rail--filled" : ""}`}>
            <div className="rail__head">
              <span className="rail__step">B</span>
              <h3>Case</h3>
              {caseId ? (
                <CircleCheck className="rail__done" size={17} aria-label="Chosen" />
              ) : null}
            </div>
            <p className="rail__hint">
              Requirements, constraints and expected future changes for one decision. Each
              case revision is immutable, and a review pins the exact revision it used.
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
            onClick={() =>
              repositoryRoot && caseId && run.start(caseId, repositoryRoot)
            }
          >
            <Play size={16} aria-hidden />
            {run.running ? "Starting…" : "Run review"}
          </button>
          <p>
            {ready ? (
              <>
                Judging every boundary in{" "}
                <strong>{repositoryRoot?.split("/").at(-1)}</strong> against{" "}
                <strong>{chosenCase?.title}</strong>. This opens the review and follows it
                there.
              </>
            ) : (
              <>
                Fill both rails to run: {repositoryRoot ? "a case" : "a repository"} is
                still missing.
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
