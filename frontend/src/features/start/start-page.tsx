import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { cn } from "../../lib/cn";
import { repositoryName } from "../../lib/format";
import { Button, ButtonLink } from "../../ui/button";
import { Checkbox } from "../../ui/field";
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
  // `?root=` is how the repositories page hands a repository over: the choice was already made
  // there, and re-picking it here would be the same click twice.
  const [params] = useSearchParams();
  const [root, setRoot] = useState(() => params.get("root") ?? "");
  // Reset with the repository, because a folder chosen in one is meaningless in another —
  // `src/vendor` exists in both and is not the same subtree.
  const [excluded, setExcluded] = useState<string[]>([]);
  const [clean, setClean] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  const reasoning = workspace.data?.models.reasoning;
  const embedding = workspace.data?.models.embedding;
  const ready = Boolean(reasoning && embedding);

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
              title="1 · Choose the repository"
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
              title="2 · Choose how much of it to read"
              description="Left-out folders are not parsed, not detected in, and not judged. The counts are Python files, counted recursively."
            />
            <PanelBody>
              <ScopePicker root={root} excluded={excluded} onChange={setExcluded} />
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="3 · Confirm the architecture case"
              description="A repeat review continues the case for this branch, so earlier answers still apply."
              actions={
                <Button variant="ghost" size="sm" onClick={() => setAdvanced((open) => !open)}>
                  {advanced ? "Hide options" : "Options"}
                </Button>
              }
            />
            {advanced ? (
              <PanelBody className="animate-expand">
                <Checkbox
                  checked={clean}
                  onChange={setClean}
                  title="Start from a clean architecture case"
                  description="Do not carry the goal, constraints, decisions and clarification answers recorded for this branch. Use this when the next review asks a different question about the same code."
                />
              </PanelBody>
            ) : (
              <PanelBody className="text-sm text-ink-3">
                {clean
                  ? "This review will start from an empty case."
                  : "This review continues the newest case on the repository's branch."}
              </PanelBody>
            )}
          </Panel>

          <Panel>
            <PanelHeader
              title="4 · Run"
              description="The run pauses for clarification only when the code genuinely cannot answer."
            />
            <PanelBody>
              <ModelReadiness
                reasoning={reasoning?.model}
                embedding={embedding?.model}
                ready={ready}
              />
            </PanelBody>
            <PanelFooter>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  size="lg"
                  disabled={!root.trim() || running || !ready}
                  onClick={start}
                >
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

        <div className="grid gap-4">
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

          <Panel>
            <PanelBody>
              <Label>What ArchCompass will not do</Label>
              <ul className="mt-2.5 grid gap-2 text-xs leading-5 text-ink-2">
                <li>It does not edit your code, open branches, or run anything in the repository.</li>
                <li>It does not invent repository identity or policy identity.</li>
                <li>It does not decide on the team's behalf — standing decisions stay yours.</li>
              </ul>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
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
