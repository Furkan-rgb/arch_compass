import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Boxes,
  CircleCheck,
  Eye,
  FilePlus2,
  FileSearch,
  FlaskConical,
  Network,
  Play,
  Plus,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { CaseEditor, CaseView } from "../case-editor";
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Loading,
  PageHeader,
  formatDate,
  shortId,
} from "../components";
import { latestPerRepository } from "../repositories";
import { RunProgress, applyProgress, type RunState } from "../run-progress";
import type { BundledCase, CaseSummary } from "../types";

/** Which case surface is open, if any: writing a new one, or reading a stored one. */
type Editor = { mode: "write" } | { mode: "view"; caseId: string } | null;

export function HomePage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [repositoryRoot, setRepositoryRoot] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [editor, setEditor] = useState<Editor>(null);
  const [progress, setProgress] = useState<RunState>(null);

  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: () => api.reviews() });
  const examples = useQuery({ queryKey: ["bundled-cases"], queryFn: api.bundledCases });
  const viewed = useQuery({
    queryKey: ["case", editor?.mode === "view" ? editor.caseId : null],
    queryFn: () => api.case((editor as { caseId: string }).caseId),
    enabled: editor?.mode === "view",
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

  const run = useMutation({
    mutationFn: (chosen: { caseId: string; root: string }) => {
      setProgress(null);
      return api.streamReview(chosen.caseId, chosen.root, (event) =>
        setProgress((current) => applyProgress(current, event)),
      );
    },
    onSuccess: async (review) => {
      await client.invalidateQueries({ queryKey: ["reviews"] });
      navigate(`/reviews/${review.review_id}`);
    },
  });

  const create = useMutation({
    mutationFn: (source: string) => api.importCase(source),
    onSuccess: async (revision) => {
      setEditor(null);
      setCaseId(revision.case_id);
      applyRepositoryHint(revision.snapshot?.repository?.root_path);
      await client.invalidateQueries({ queryKey: ["cases"] });
    },
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
  const busy = run.isPending || loadExample.isPending || index.isPending;

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
                onClick={() => setEditor({ mode: "write" })}
              >
                <FilePlus2 size={15} aria-hidden /> Write a new case
              </button>
              {caseId ? (
                <button
                  type="button"
                  className="button button--quiet"
                  onClick={() => setEditor({ mode: "view", caseId })}
                >
                  <Eye size={15} aria-hidden /> View this case
                </button>
              ) : null}
            </div>
          </div>
        </div>

        {/* Full width rather than inside the rail: a case is prose, and half a rail is not
            enough of a line to write it on. */}
        {editor?.mode === "write" ? (
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
              repositoryRoot &&
              caseId &&
              run.mutate({ caseId, root: repositoryRoot })
            }
          >
            <Play size={16} aria-hidden />
            {run.isPending ? "Reviewing…" : "Run the review"}
          </button>
          {run.isPending ? (
            <RunProgress progress={progress} />
          ) : (
            <p>
              {ready ? (
                <>
                  Judging every boundary in{" "}
                  <strong>{repositoryRoot?.split("/").at(-1)}</strong> against{" "}
                  <strong>{chosenCase?.title}</strong>.
                </>
              ) : (
                <>
                  Fill both rails to run: {repositoryRoot ? "a case" : "a repository"} is
                  still missing.
                </>
              )}
            </p>
          )}
        </div>
        {run.isError ? <ErrorPanel error={run.error} /> : null}
      </section>

      <section className="panel">
        <h2 className="panel__title">Past reviews</h2>
        {reviews.isLoading ? <Loading label="Reading reviews…" /> : null}
        {reviews.isError ? <ErrorPanel error={reviews.error} /> : null}
        {reviews.data && reviews.data.length === 0 ? (
          <EmptyState
            title="No reviews yet"
            description="Run one of the examples above to produce the first."
          />
        ) : null}
        <ul className="card-list">
          {(reviews.data || []).map((review) => (
            <li key={review.review_id} className="card">
              <div className="card__body">
                <div className="card__heading">
                  <strong>{shortId(review.review_id)}</strong>
                  <Badge tone={review.boundaries_material > 0 ? "warning" : "success"}>
                    {review.boundaries_material > 0 ? (
                      <>{review.boundaries_material} material</>
                    ) : (
                      <>
                        <CircleCheck size={13} aria-hidden /> all cleared
                      </>
                    )}
                  </Badge>
                </div>
                {/* The examined count is shown even when nothing was material: a review
                    that cleared six boundaries and one that found none are different
                    results, and only this number tells them apart. */}
                <p className="card__detail">
                  {review.boundaries_reviewed} boundaries examined ·{" "}
                  {formatDate(review.created_at)}
                </p>
              </div>
              <Link className="button" to={`/reviews/${review.review_id}`}>
                Open <ArrowRight size={15} aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
