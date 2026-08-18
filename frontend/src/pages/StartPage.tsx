import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { coreApi } from "../api";
import { Card, ErrorNotice, PageTitle } from "../components/ui";

export function StartPage() {
  const navigate = useNavigate();
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: coreApi.repositories });
  const examples = useQuery({ queryKey: ["examples"], queryFn: coreApi.examples });
  const [root, setRoot] = useState("");
  const [clean, setClean] = useState(false);
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<string[]>([]);
  const [failure, setFailure] = useState<unknown>(null);

  async function start() {
    setRunning(true);
    setFailure(null);
    setStages(["indexing repository"]);
    try {
      const started = await coreApi.startRepository(root.trim(), clean);
      let finalId: string | null = null;
      for await (const progress of coreApi.streamReview(started.case_id, root.trim())) {
        setStages((current) => [...current, progress.event.replaceAll("_", " ")]);
        if (progress.message) throw new Error(progress.message);
        if (progress.review) finalId = progress.review.id;
      }
      if (!finalId) throw new Error("The review stream ended without a review snapshot");
      navigate(`/reviews/${finalId}`);
    } catch (error) {
      setFailure(error);
      setRunning(false);
    }
  }

  async function chooseExample(name: string, repositoryRoot: string) {
    setFailure(null);
    try {
      await coreApi.loadExample(name);
      setRoot(repositoryRoot);
    } catch (error) {
      setFailure(error);
    }
  }

  return (
    <div>
      <PageTitle eyebrow="Architecture review" title="Choose the code to examine" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(300px,.7fr)]">
        <Card>
          <h2 className="font-display text-xl font-semibold">Repository</h2>
          <p className="mt-2 text-sm text-ink-2">ArchCompass indexes source deterministically before the graph spends any reasoning budget.</p>
          <label className="mt-6 block text-sm font-medium" htmlFor="repository-root">Repository path</label>
          <input id="repository-root" value={root} onChange={(event) => setRoot(event.target.value)} className="mt-2 w-full rounded-md border border-rule bg-canvas px-3 py-2.5 font-mono text-sm" placeholder="/absolute/path/to/repository" />
          {(repositories.data || []).length ? (
            <div className="mt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-ink-3">Recently indexed</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {repositories.data?.slice(0, 6).map((repository) => <button key={repository.version_id} onClick={() => setRoot(repository.root_path)} className="max-w-full truncate rounded-md border border-rule px-3 py-1.5 text-left text-xs hover:border-primary">{repository.root_path}</button>)}
              </div>
            </div>
          ) : null}
          <label className="mt-5 flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={clean} onChange={(event) => setClean(event.target.checked)} /> Start a new ArchitectureCase instead of continuing this branch</label>
          <button onClick={start} disabled={!root.trim() || running} className="mt-6 rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-on-accent disabled:opacity-50">{running ? "Review running…" : "Run review"}</button>
          {failure ? <div className="mt-4"><ErrorNotice error={failure} /></div> : null}
          {running ? <ol aria-label="Review progress" className="mt-5 grid gap-2 text-sm text-ink-2">{stages.map((stage, index) => <li key={`${stage}-${index}`} className="flex gap-3"><span className="text-primary">{index + 1}</span><span>{stage}</span></li>)}</ol> : null}
        </Card>
        <Card>
          <h2 className="font-display text-xl font-semibold">Example repositories</h2>
          <p className="mt-2 text-sm text-ink-2">Load a characterized repository through the same indexing path.</p>
          <div className="mt-5 grid gap-3">
            {(examples.data || []).map((example) => (
              <button key={example.name} onClick={() => chooseExample(example.name, example.repository_root)} className="rounded-lg border border-rule p-4 text-left hover:border-primary">
                <div className="font-medium">{example.title}</div>
                <div className="mt-1 text-sm text-ink-2">{example.description}</div>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
