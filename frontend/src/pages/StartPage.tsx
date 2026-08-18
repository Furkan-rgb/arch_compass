import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { coreApi } from "../api";
import { Button, Card, ErrorNotice, Field, Input, PageTitle, StatusBadge } from "../components/ui";

const stageLabels: Record<string, string> = {
  repository_analyzed: "Repository analyzed",
  candidates_detected: "Candidates detected",
  policies_retrieved: "Relevant policies retrieved",
  candidates_judged: "Architecture candidates judged",
  questions_generated: "Clarifications prepared",
  review_composed: "Review composed",
  review_recorded: "Review recorded",
};

export function StartPage() {
  const navigate = useNavigate();
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: coreApi.repositories });
  const examples = useQuery({ queryKey: ["examples"], queryFn: coreApi.examples });
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: coreApi.workspace });
  const [root, setRoot] = useState("");
  const [clean, setClean] = useState(false);
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<string[]>([]);
  const [failure, setFailure] = useState<unknown>(null);

  const ready = Boolean(workspace.data?.models.reasoning && workspace.data?.models.embedding);

  async function start() {
    setRunning(true);
    setFailure(null);
    setStages(["Preparing repository"]);
    try {
      const started = await coreApi.startRepository(root.trim(), clean);
      let finalId: string | null = null;
      for await (const progress of coreApi.streamReview(started.case_id, root.trim())) {
        const label = stageLabels[progress.event] || progress.event.replaceAll("_", " ");
        setStages((current) => current.at(-1) === label ? current : [...current, label]);
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
      <PageTitle
        eyebrow="New architecture review"
        title="Turn a repository into an architectural decision record."
        description="Choose the codebase. ArchCompass builds a deterministic atlas, identifies structural candidates, and judges them against the policies that matter."
      >
        <Link to="/reviews" className="text-sm font-semibold text-primary hover:underline">View review history</Link>
      </PageTitle>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,.75fr)]">
        <Card className="overflow-hidden p-0 sm:p-0">
          <div className="border-b border-rule bg-canvas-strong/40 px-5 py-4 sm:px-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><div className="font-display text-xl font-semibold">Review setup</div><div className="mt-1 text-sm text-ink-3">Local folders and checked-out Git repositories are supported.</div></div>
              <StatusBadge status={ready ? "ready" : "setup required"} />
            </div>
          </div>
          <div className="p-5 sm:p-7">
            {!ready ? <div className="mb-6 rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm text-warning"><strong className="font-semibold">Model setup is incomplete.</strong> Select both a reasoning and embedding model in <Link to="/settings" className="underline">Models</Link> before starting.</div> : null}
            <Field label="Repository path" htmlFor="repository-root" hint="Use an absolute path. The repository is read and indexed locally.">
              <Input id="repository-root" value={root} onChange={(event) => setRoot(event.target.value)} className="font-mono" placeholder="/absolute/path/to/repository" autoComplete="off" />
            </Field>

            {(repositories.data || []).length ? <div className="mt-5"><div className="text-xs font-bold uppercase tracking-[0.12em] text-ink-3">Recent repositories</div><div className="mt-2 flex flex-wrap gap-2">{repositories.data?.slice(0, 6).map((repository) => <button key={repository.version_id} onClick={() => setRoot(repository.root_path)} title={repository.root_path} className="max-w-full truncate rounded-lg border border-rule-strong bg-surface px-3 py-2 text-left text-xs font-medium text-ink-2 transition hover:border-primary/50 hover:text-ink">{repository.root_path.split("/").pop() || repository.root_path}</button>)}</div></div> : null}

            <label className="mt-6 flex items-start gap-3 rounded-xl border border-rule bg-canvas-strong/45 p-4 text-sm">
              <input type="checkbox" checked={clean} onChange={(event) => setClean(event.target.checked)} className="mt-0.5 size-4 accent-primary" />
              <span><span className="block font-semibold text-ink">Start with a clean ArchitectureCase</span><span className="mt-1 block leading-5 text-ink-3">Do not continue the existing architectural context for this repository branch.</span></span>
            </label>

            <div className="mt-6 flex flex-wrap items-center gap-3"><Button onClick={start} disabled={!root.trim() || running || !ready}>{running ? "Review in progress…" : "Run architecture review"}</Button><span className="text-xs text-ink-3">The review may pause for clarification.</span></div>
            {failure ? <div className="mt-5"><ErrorNotice error={failure} /></div> : null}
          </div>

          {running ? <div className="border-t border-rule bg-canvas-strong/35 px-5 py-5 sm:px-7" aria-live="polite"><div className="flex items-center justify-between"><div className="text-sm font-semibold">Review progress</div><div className="text-xs tabular-nums text-ink-3">{stages.length} stages</div></div><ol aria-label="Review progress" className="mt-4 grid gap-3">{stages.map((stage, index) => <li key={`${stage}-${index}`} className="flex items-center gap-3 text-sm"><span className={index === stages.length - 1 ? "size-2.5 animate-pulse rounded-full bg-primary" : "size-2.5 rounded-full bg-success"} /><span className={index === stages.length - 1 ? "font-semibold text-ink" : "text-ink-2"}>{stage}</span></li>)}</ol></div> : null}
        </Card>

        <div className="grid gap-6">
          <Card tone="subtle">
            <div className="text-xs font-bold uppercase tracking-[0.14em] text-primary">What happens next</div>
            <ol className="mt-5 grid gap-5">{[
              ["01", "Build the atlas", "Parse structure and capture deterministic evidence."],
              ["02", "Judge candidates", "Retrieve applicable policies and assess each candidate."],
              ["03", "Resolve context", "Answer only the questions the repository cannot."],
            ].map(([number, title, text]) => <li key={number} className="flex gap-4"><span className="font-mono text-xs font-bold text-primary">{number}</span><div><div className="font-semibold text-ink">{title}</div><div className="mt-1 text-sm leading-5 text-ink-3">{text}</div></div></li>)}</ol>
          </Card>

          {(examples.data || []).length ? <Card><div className="font-display text-lg font-semibold">Try an example</div><p className="mt-1 text-sm text-ink-3">Load a characterized repository through the same pipeline.</p><div className="mt-4 grid gap-2">{examples.data?.map((example) => <button key={example.name} onClick={() => chooseExample(example.name, example.repository_root)} className="rounded-xl border border-rule p-4 text-left transition hover:border-primary/40 hover:bg-primary-soft"><div className="font-semibold text-ink">{example.title}</div><div className="mt-1 text-sm leading-5 text-ink-3">{example.description}</div></button>)}</div></Card> : null}
        </div>
      </div>
    </div>
  );
}
