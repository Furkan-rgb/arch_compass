import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, type Review } from "../../api";
import { cn } from "../../lib/cn";
import { plural, repositoryName } from "../../lib/format";
import { Button, ButtonLink } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Spinner } from "../../ui/states";
import { RepositoryPicker } from "./repository-picker";
import { ScopePicker } from "./scope-picker";

/** Graph events, said the way a reader would describe the step. */
const PIPELINE = [
  ["Repository", "Parsed into a deterministic atlas — nodes, edges, metrics, signals."],
  ["Candidates", "Structural patterns detected by rule, not by the model."],
  ["Policies", "Retrieved per candidate, with the retrieval recorded."],
  ["Judgement", "The model decides what the evidence means, inside the policy it was given."],
  ["Clarification", "Only what the repository genuinely cannot answer."],
  ["Review", "Recorded as an immutable revision with its own delta."],
] as const;

export function StartPage() {
  const navigate = useNavigate();
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: api.reviews });
  // `?root=` is how the repositories page hands a repository over: the choice was already made
  // there, and re-picking it here would be the same click twice.
  const [params] = useSearchParams();
  const [root, setRoot] = useState(() => params.get("root") ?? "");
  // Reset with the repository, because a folder chosen in one is meaningless in another —
  // `src/vendor` exists in both and is not the same subtree.
  const [excluded, setExcluded] = useState<string[]>([]);
  const [clean, setClean] = useState(false);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  const reasoning = workspace.data?.models.reasoning;
  const embedding = workspace.data?.models.embedding;
  const ready = Boolean(reasoning && embedding);

  // What this repository already has recorded against it, which is a fact to state and not
  // a question to ask. The charter is explicit that a case starts empty and fills in as
  // reviews ask for what they need — so nothing here asks anyone to confirm one.
  const prior: Review | undefined = root.trim()
    ? [...(reviews.data ?? [])]
        .filter((review) => review.repository.path === root.trim())
        .sort((left, right) => right.sequence - left.sequence)[0]
    : undefined;

  /**
   * Hand the review to the workspace and go and watch it.
   *
   * This page used to hold the whole review inside one streaming response, which made the
   * browser tab the thing keeping it alive: a reload closed the connection and the run was
   * abandoned. Now it asks for a run, gets an id back straight away, and moves to a URL
   * that survives a reload.
   */
  async function start() {
    setRunning(true);
    setFailure(null);
    try {
      // Sent on every run, including as `[]`. Absent would mean "keep whatever this
      // repository was last indexed under", and the reader has the folders on screen in
      // front of them — so what the screen shows is what the review reads.
      const started = await api.startRepository(root.trim(), clean, excluded);
      const run = await api.startReviewRun(started.case_id, root.trim());
      navigate(`/runs/${run.run_id}`);
    } catch (error) {
      setFailure(error);
      setRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="New review"
        title="Review a repository"
        description="ArchCompass indexes the code deterministically, detects architecture candidates, retrieves the policies that bear on them, and judges each one with the evidence attached."
        actions={
          <ButtonLink to="/reviews" variant="secondary">
            Review history
          </ButtonLink>
        }
      />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <div className="grid gap-4">
          <Panel>
            <PanelHeader
              title="1 · Which repository"
              description="Local folders and cloned checkouts are both reviewed the same way."
            />
            <PanelBody>
              <RepositoryPicker
                value={root}
                onChange={(next) => {
                  setRoot(next);
                  setExcluded([]);
                }}
              />
              {root ? (
                <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md border border-rule-strong bg-sunken px-3 py-2.5">
                  <span className="text-xs font-semibold text-ink">Selected</span>
                  <Mono className="min-w-0 flex-1 truncate text-[12px] text-ink">{root}</Mono>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setRoot("");
                      setExcluded([]);
                    }}
                  >
                    Clear
                  </Button>
                </div>
              ) : null}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="2 · How much of it to read"
              description="Left-out folders are not parsed, not detected in, and not judged. The counts are Python files, counted recursively."
            />
            <PanelBody>
              <ScopePicker root={root} excluded={excluded} onChange={setExcluded} />
            </PanelBody>
          </Panel>

          {/* Two steps, not four. "Confirm the architecture case" was a numbered step that
              asked nothing answerable: on a first review there is no case to confirm, and on
              a repeat one continuing it is what anybody would want. So the case is a fact
              stated at the moment of running, with the other choice as a sentence rather
              than a form. */}
          <Panel>
            <PanelHeader
              title="Run"
              description="The run pauses for clarification only when the code genuinely cannot answer."
            />
            <PanelBody>
              <ModelReadiness
                reasoning={reasoning?.model}
                embedding={embedding?.model}
                ready={ready}
              />
              <CaseNote
                root={root.trim()}
                prior={prior}
                clean={clean}
                onCleanChange={setClean}
              />
            </PanelBody>
            <PanelFooter>
              <div className="flex flex-wrap items-center gap-3">
                <Button size="lg" disabled={!root.trim() || running || !ready} onClick={start}>
                  {running ? (
                    <>
                      <Spinner /> Review in progress…
                    </>
                  ) : (
                    "Run review"
                  )}
                </Button>
                <span className="text-xs text-ink-3">
                  {root
                    ? `Reviewing ${repositoryName(root)}`
                    : "Choose a repository to enable the run."}
                </span>
              </div>
              {failure ? (
                <div className="mt-3">
                  <ErrorNotice error={failure} title="The review stopped" />
                </div>
              ) : null}
            </PanelFooter>
          </Panel>
        </div>

        {/* One panel, not two. "What ArchCompass will not do" was charter copy on a form —
            positioning addressed to somebody who has already chosen to use the product and
            is trying to start a job. The landing page carries it, which is where a reader
            who has not decided yet actually is. */}
        <Panel tone="sunken">
          <PanelBody>
            <Label>How a review runs</Label>
            <ol className="mt-3 grid gap-3.5">
              {PIPELINE.map(([title, text], index) => (
                <li key={title} className="flex gap-3">
                  <span className="mt-0.5 font-mono text-[11px] font-bold text-ink">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-ink">{title}</span>
                    <span className="mt-0.5 block text-xs leading-5 text-ink-3">{text}</span>
                  </span>
                </li>
              ))}
            </ol>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

/**
 * What this run will do about the architecture case, said as a sentence.
 *
 * A case carries constraints, decisions and clarification answers, and it is the human half
 * of a review. Continuing the newest one is what a repeat review wants; starting empty is
 * what somebody wants when the next review asks a different question about the same code.
 * Both are one sentence and one link, because neither is a question anyone can answer before
 * they have seen a finding.
 */
function CaseNote({
  root,
  prior,
  clean,
  onCleanChange,
}: {
  root: string;
  prior: Review | undefined;
  clean: boolean;
  onCleanChange: (value: boolean) => void;
}) {
  if (!root) return null;

  const recorded = prior
    ? [
        plural(prior.case.constraints.length, "constraint"),
        plural(prior.case.decisions.length, "recorded decision"),
        plural(prior.case.answers.length, "clarification answer"),
      ].join(", ")
    : null;

  return (
    <p className="mt-3 border-t border-rule pt-3 text-[13px] leading-6 text-ink-2">
      {clean ? (
        <>
          This review starts from an empty architecture case. Nothing recorded on{" "}
          {prior?.repository.branch ? (
            <Mono className="text-ink">{prior.repository.branch}</Mono>
          ) : (
            "this branch"
          )}{" "}
          carries over.{" "}
          <button
            type="button"
            onClick={() => onCleanChange(false)}
            className="font-semibold text-ink underline underline-offset-2 hover:text-ink-2"
          >
            Continue the existing case instead
          </button>
          .
        </>
      ) : prior ? (
        <>
          Continues case revision{" "}
          <span className="font-semibold text-ink">{prior.case.revision}</span>
          {prior.repository.branch ? (
            <>
              {" "}
              on <Mono className="text-ink">{prior.repository.branch}</Mono>
            </>
          ) : null}{" "}
          — {recorded}.{" "}
          <button
            type="button"
            onClick={() => onCleanChange(true)}
            className="font-semibold text-ink underline underline-offset-2 hover:text-ink-2"
          >
            Start from an empty case instead
          </button>
          .
        </>
      ) : (
        <>
          Opens a new architecture case for this repository. It starts empty and fills in as
          reviews ask for what they need — nothing is demanded up front.
        </>
      )}
    </p>
  );
}

function ModelReadiness({
  reasoning,
  embedding,
  ready,
}: {
  reasoning?: string;
  embedding?: string;
  ready: boolean;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {[
        ["Reasoning model", reasoning, "judges candidates"],
        ["Embedding model", embedding, "retrieves policies"],
      ].map(([label, model, role]) => (
        <div
          key={label}
          className={cn(
            "rounded-md border px-3 py-2.5",
            model ? "border-rule bg-surface-2" : "border-rule-strong bg-sunken",
          )}
        >
          <div className="flex items-center gap-2">
            {/* Chosen or not chosen is a step in this flow, not a grade. The verdict hues
                belong to the queue, where green means a candidate came back cleared. */}
            {model ? (
              <CheckIcon className="size-3.5 shrink-0 text-ink-3" aria-hidden="true" />
            ) : (
              <span
                aria-hidden="true"
                className="size-3.5 shrink-0 rounded-full border-2 border-dashed border-ink"
              />
            )}
            <span className="text-xs font-semibold text-ink">{label}</span>
            <span className="text-[11px] text-ink-3">· {role}</span>
          </div>
          <Mono className={cn("mt-1 block truncate text-[12px]", !model && "text-ink")}>
            {model ?? "not chosen yet"}
          </Mono>
        </div>
      ))}
      {!ready ? (
        <p className="text-xs leading-5 text-ink-2 sm:col-span-2">
          Both are needed before a review can run.{" "}
          <Link to="/settings" className="font-semibold text-mark underline underline-offset-2">
            Choose models
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
