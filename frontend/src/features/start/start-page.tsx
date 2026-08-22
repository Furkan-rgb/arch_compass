import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, type RepositorySummary, type ReviewRun, type ReviewSummary } from "../../api";
import { cn } from "../../lib/cn";
import { useRunsBecomeReviews } from "../../lib/runs";
import { plural, repositoryName } from "../../lib/format";
import { Button, ButtonLink } from "../../ui/button";
import { CheckIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { PageHeader } from "../../ui/page";
import { Label, Panel, PanelBody, PanelFooter, PanelHeader } from "../../ui/panel";
import { ErrorNotice, Skeleton, Spinner } from "../../ui/states";
import { RepositoryPicker } from "./repository-picker";
import { ScopePicker, filesInScope, useRepositoryTree } from "./scope-picker";

/** Graph events, said the way a reader would describe the step. */
const PIPELINE = [
  ["Repository", "Parsed into a deterministic atlas — nodes, edges, metrics, signals."],
  ["Candidates", "Structural patterns detected by rule, not by the model."],
  ["Policies", "Retrieved per candidate, with the retrieval recorded."],
  ["Judgement", "The model decides what the evidence means, inside the policy it was given."],
  ["Clarification", "Only what the repository genuinely cannot answer."],
  ["Review", "Recorded as an immutable revision with its own delta."],
] as const;

/**
 * Two spellings of one path, as far as this page can tell.
 *
 * The workspace canonicalises with `expanduser().resolve()` and nothing in a browser can
 * reproduce that, so a trailing slash is the one difference worth collapsing here and every
 * other difference is left standing as one. Where that leaves no confident match the page
 * says so rather than guessing — see `caseMatch`.
 */
const samePath = (left: string | null | undefined, right: string) =>
  Boolean(left) && left!.replace(/\/+$/, "") === right.replace(/\/+$/, "");

/**
 * What the run button is doing, in the two phases the click actually has.
 *
 * `startRepository` indexes the whole repository before it answers, and on a large codebase
 * that is the longest single wait in the product — behind a button that read "Review in
 * progress…", which was not yet true of anything. The review does not exist until the second
 * call returns.
 *
 * The better fix is for the run to accept a root and index inside itself, so parsing becomes
 * the first visible stage on the run page and this page hands over immediately. That needs
 * the workspace to change; this is the honest label until it does.
 */
type Phase = "idle" | "indexing" | "starting";

const PHASE_LABEL: Record<Exclude<Phase, "idle">, string> = {
  indexing: "Indexing the repository…",
  starting: "Starting the review…",
};

/**
 * What this run will do about the architecture case — as much of it as this page can actually
 * know, which is less than it used to claim.
 *
 * The old answer matched the newest review by exact string on the path, and did not look at
 * the branch at all. So a trailing slash produced "opens a new architecture case" while the
 * workspace went on to continue revision 4, and a feature branch was told `main`'s revision
 * and `main`'s answer count. Both are the same mistake: a fact stated with more confidence
 * than the data supports, under a link somebody clicks because of it.
 */
type CaseMatch =
  | { kind: "asking" }
  | { kind: "continues"; prior: ReviewSummary }
  | { kind: "new" }
  | { kind: "unknown" };

function caseMatch(
  picked: RepositorySummary | undefined,
  reviews: ReviewSummary[] | undefined,
  asking: boolean,
): CaseMatch {
  if (asking) return { kind: "asking" };
  // A path this workspace has never indexed is a path with no branch attached to it here, so
  // there is nothing to key a lineage off and nothing honest to say about which case it is.
  if (!picked) return { kind: "unknown" };
  const prior = [...(reviews ?? [])]
    .filter(
      (review) =>
        samePath(review.repository.path, picked.root_path) &&
        (review.repository.branch ?? null) === (picked.branch_name ?? null),
    )
    .sort((left, right) => right.sequence - left.sequence)[0];
  return prior ? { kind: "continues", prior } : { kind: "new" };
}

/**
 * What the last review of this repository cost, in the units a review is actually spent in.
 *
 * Step 2 measures Python files, and a review does not spend files — it spends candidates and
 * minutes, and neither of those was named anywhere on this page. Both are recorded on the
 * previous review of this branch, so this is read off the record rather than estimated, and
 * it is omitted where there is no prior review to read.
 */
function lastReviewNote(match: CaseMatch): string | null {
  if (match.kind !== "continues") return null;
  const prior = match.prior;
  if (!prior.finished_at) return null;
  const minutes = Math.round(
    (Date.parse(prior.finished_at) - Date.parse(prior.started_at)) / 60_000,
  );
  if (!Number.isFinite(minutes) || minutes < 0) return null;
  const took = minutes < 1 ? "under a minute" : plural(minutes, "minute");
  return `Review ${prior.sequence} of this branch judged ${plural(
    prior.finding_count,
    "candidate",
  )} and took ${took}.`;
}

export function StartPage() {
  const navigate = useNavigate();
  const workspace = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });
  /**
   * The listing, not the reviews. All this page reads off a prior review is a path, a
   * branch, two numbers and two timestamps — and a stored review carries the repository's
   * whole atlas, so the full list was megabytes a row to print one sentence.
   *
   * It read the full list for one reason: the case sentence prints how many answers the case
   * it will continue already carries, and the projection had `case_revision` and no answers.
   * It has `answer_count` now, which is the whole of what was missing.
   *
   * Filed under `["reviews", …]` so that the invalidations already written across this
   * application, which are keyed on the prefix, reach this list too.
   */
  const reviews = useQuery({ queryKey: ["reviews", "summary"], queryFn: api.reviewSummaries });
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  /**
   * What is already running, on the same query key the shell's run indicator uses so the two
   * share one request rather than each polling for itself.
   *
   * Nothing else stopped a second run of the same repository. `phase` guards a double-click
   * and nothing more, so going back to this page, opening a second tab, or arriving from the
   * repositories page with `?root=` all left the button live for a repository already being
   * reviewed — two runs judging the same branch and the same case, spending the model budget
   * twice for two reviews of one commit.
   */
  const runs = useQuery({
    queryKey: ["review-runs"],
    queryFn: api.reviewRuns,
    refetchInterval: (query) => (query.state.data?.length ? 4000 : false),
  });
  // A run leaving that list is a review arriving. Polling it and not acting on the change is
  // what left a finished background run invisible until a reload.
  useRunsBecomeReviews(runs.data);

  // `?root=` is how the repositories page hands a repository over: the choice was already made
  // there, and re-picking it here would be the same click twice.
  const [params] = useSearchParams();
  const [root, setRoot] = useState(() => params.get("root") ?? "");
  /**
   * The folders the arriving link named, and nothing where it named none.
   *
   * `?exclude=` is the other half of the same hand-off, and the run page is what sends it:
   * "Start again" after a failed run used to carry the repository and drop the scope, so ten
   * minutes of ticking folders was lost to a run that broke on its first stage. One parameter
   * per folder rather than one delimited string, because a path may contain a comma and an
   * escaping rule invented here would be a second way to spell one scope.
   *
   * Read once, at mount, and then owned by the picker. Reset with the repository, because a
   * folder chosen in one is meaningless in another — `src/vendor` exists in both and is not
   * the same subtree.
   */
  const [excluded, setExcluded] = useState<string[]>(() => params.getAll("exclude"));
  const [clean, setClean] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [failure, setFailure] = useState<unknown>(null);
  const reasonId = useId();

  const chosen = root.trim();
  const tree = useRepositoryTree(chosen);
  const inScope = filesInScope(tree.data, excluded);

  const reasoning = workspace.data?.models.reasoning;
  const embedding = workspace.data?.models.embedding;
  const ready = Boolean(reasoning && embedding);

  // The indexed checkout this path names, which is what turns the case sentence below from a
  // string comparison into a fact about a branch.
  const picked = chosen
    ? repositories.data?.find((repository) => samePath(repository.root_path, chosen))
    : undefined;
  const match = caseMatch(
    picked,
    reviews.data,
    Boolean(chosen) && (repositories.isPending || reviews.isPending),
  );

  const lastReview = lastReviewNote(match);

  const running: ReviewRun | undefined = chosen
    ? runs.data?.find((run) => run.status === "running" && samePath(run.repository_root, chosen))
    : undefined;

  // The tree's failure belongs here too. The button used to stay enabled and red beside a
  // notice reading "That repository could not be read", offering to review something the
  // workspace has already said it cannot open.
  const blocked = !chosen || phase !== "idle" || !ready || tree.isError;

  /**
   * Hand the review to the workspace and go and watch it.
   *
   * This page used to hold the whole review inside one streaming response, which made the
   * browser tab the thing keeping it alive: a reload closed the connection and the run was
   * abandoned. Now it asks for a run, gets an id back straight away, and moves to a URL
   * that survives a reload.
   */
  async function start() {
    setPhase("indexing");
    setFailure(null);
    try {
      // Sent on every run, including as `[]`. Absent would mean "keep whatever this
      // repository was last indexed under", and the reader has the folders on screen in
      // front of them — so what the screen shows is what the review reads.
      const started = await api.startRepository(chosen, clean, excluded);
      setPhase("starting");
      const run = await api.startReviewRun(started.case_id, chosen);
      navigate(`/runs/${run.run_id}`);
    } catch (error) {
      setFailure(error);
      setPhase("idle");
    }
  }

  const reading = inScope === null ? null : plural(inScope, "Python file");
  const reason = !chosen ? (
    "Choose a repository to enable the run."
  ) : phase === "indexing" ? (
    reading ? `Reading ${reading}. Nothing is judged until this finishes.` : "Nothing is judged until this finishes."
  ) : phase === "starting" ? (
    "The repository is indexed. Handing the review to the workspace."
  ) : tree.isError ? (
    "That repository could not be read, so there is nothing to review."
  ) : workspace.isPending ? (
    "Reading which models this workspace is set to."
  ) : !ready ? (
    "Both models must be chosen before a review can run."
  ) : running ? (
    <>
      A review of {repositoryName(chosen)} is already running.{" "}
      <Link
        to={`/runs/${running.run_id}`}
        className="font-semibold text-ink underline underline-offset-2"
      >
        Watch it
      </Link>
      .
    </>
  ) : (
    `Reviewing ${repositoryName(chosen)}${reading ? ` · ${reading}` : ""}`
  );

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
              <ScopePicker root={chosen} excluded={excluded} onChange={setExcluded} />
              {lastReview ? (
                <p className="mt-3 border-t border-rule pt-3 text-xs leading-5 text-ink-3">
                  {lastReview}
                </p>
              ) : null}
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
              description="A review takes several minutes and keeps running in the workspace if you close this tab. It pauses for clarification only when the code genuinely cannot answer."
            />
            <PanelBody>
              <ModelReadiness
                asking={workspace.isPending}
                reasoning={reasoning?.model}
                embedding={embedding?.model}
                ready={ready}
              />
              {chosen ? (
                <CaseNote match={match} clean={clean} onCleanChange={setClean} />
              ) : null}
            </PanelBody>
            <PanelFooter>
              <div className="flex flex-wrap items-center gap-3">
                {/* Demoted rather than removed where one is already running. Reviewing the
                    same commit twice is occasionally what somebody means, and refusing it
                    would be this page deciding that for them — but it must not be the
                    unlabelled default click. */}
                <Button
                  size="lg"
                  variant={running ? "secondary" : "primary"}
                  inactive={blocked}
                  aria-describedby={reasonId}
                  onClick={start}
                >
                  {phase === "idle" ? (
                    running ? (
                      "Run another anyway"
                    ) : (
                      "Run review"
                    )
                  ) : (
                    <>
                      <Spinner label="" /> {PHASE_LABEL[phase]}
                    </>
                  )}
                </Button>
                {/* The reason the button cannot run is the button's description, not a
                    sentence that happens to sit beside it. It had no `id` and nothing
                    pointed at it, so the one thing that explains the page's primary action
                    was reachable only by looking. */}
                <span id={reasonId} className="text-xs leading-5 text-ink-3">
                  {reason}
                </span>
              </div>
              {failure ? (
                <div className="mt-3">
                  <ErrorNotice
                    error={failure}
                    title="The review stopped"
                    action={
                      <Button variant="secondary" size="sm" onClick={start}>
                        Try again
                      </Button>
                    }
                  />
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
 * A case carries what people have answered when a judgement stopped to ask, and it is the
 * human half of a review. Continuing the newest one is what a repeat review wants; starting
 * empty is what somebody wants when the next review asks a different question about the same
 * code. Both are one sentence and one link, because neither is a question anyone can answer
 * before they have seen a finding.
 */
function CaseNote({
  match,
  clean,
  onCleanChange,
}: {
  match: CaseMatch;
  clean: boolean;
  onCleanChange: (value: boolean) => void;
}) {
  // Nothing at all while the workspace is still being asked. A sentence that names a case
  // revision is a claim, and a claim made before the answer arrives is the defect this
  // component was rewritten for.
  if (match.kind === "asking") return null;

  const prior = match.kind === "continues" ? match.prior : undefined;
  const empty = (
    <button
      type="button"
      onClick={() => onCleanChange(true)}
      className="font-semibold text-ink underline underline-offset-2 hover:text-ink-2"
    >
      Start from an empty case instead
    </button>
  );

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
      ) : match.kind === "continues" ? (
        <>
          Continues case revision{" "}
          <span className="font-semibold text-ink">{match.prior.case_revision}</span>
          {match.prior.repository.branch ? (
            <>
              {" "}
              on <Mono className="text-ink">{match.prior.repository.branch}</Mono>
            </>
          ) : null}{" "}
          — {plural(match.prior.answer_count, "answer")}. {empty}.
        </>
      ) : match.kind === "new" ? (
        <>
          Opens a new architecture case for this repository. It starts empty and fills in as
          reviews ask for what they need — nothing is demanded up front.
        </>
      ) : (
        <>
          This path has not been indexed in this workspace, so which case it belongs to is not
          known here yet. The review continues the newest case on the branch it finds, and
          opens an empty one where there is none. {empty}.
        </>
      )}
    </p>
  );
}

function ModelReadiness({
  asking,
  reasoning,
  embedding,
  ready,
}: {
  asking: boolean;
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
            model || asking ? "border-rule bg-surface-2" : "border-rule-strong bg-sunken",
          )}
        >
          <div className="flex items-center gap-2">
            {/* Chosen or not chosen is a step in this flow, not a grade. The verdict hues
                belong to the queue, where green means a candidate came back cleared.

                Pending is not a third position on that step either — it is the page not
                knowing yet, which is the treatment the shell's model chips already give it.
                Two cards reading "not chosen yet" in full ink while the request is still out
                tell a correctly configured workspace that it is unconfigured, and point it
                at Settings to fix nothing. */}
            {asking ? (
              <span
                aria-hidden="true"
                className="size-3.5 shrink-0 animate-breathe rounded-full border-2 border-rule-strong"
              />
            ) : model ? (
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
          {asking ? (
            <Skeleton className="mt-1.5 h-3 w-32" />
          ) : (
            <Mono className={cn("mt-1 block truncate text-[12px]", !model && "text-ink")}>
              {model ?? "not chosen yet"}
            </Mono>
          )}
        </div>
      ))}
      {!ready && !asking ? (
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
