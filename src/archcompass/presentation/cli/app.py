"""ArchCompass command-line presentation adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import typer
import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from archcompass.bootstrap import (
    Runtime,
    build_runtime,
    pinned_model,
)
from archcompass.bootstrap import (
    initialize_workspace as initialize_workspace_runtime,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain import (
    AnswerStatus,
    ArchitectureCase,
    PolicyContext,
    Review,
)
from archcompass.domain.errors import ArchCompassError
from archcompass.domain.repository import DEFAULT_BRANCH_NAME
from archcompass.policies.evaluation import (
    RetrievalExample,
    choose_smallest_passing_k,
)
from archcompass.reasoning.ports import ReviewConversation
from archcompass.records import THINKING_LEVELS, ThinkingMode
from archcompass.repositories.safety import (
    validate_repository_directory,
)
from archcompass.workflow.ci import CiRun, FailOn
from archcompass.workflow.service import SubmittedAnswer

app = typer.Typer(
    name="archcompass",
    help="Evidence-grounded software architecture advice.",
    no_args_is_help=True,
)
policies_app = typer.Typer(help="Build and inspect architectural policies.")
policy_sources_app = typer.Typer(help="Register persistent workspace policy sources.")
repo_app = typer.Typer(help="Index a Python repository.")
atlas_app = typer.Typer(help="Query repository atlases.")
case_app = typer.Typer(help="Create and revise architecture cases.")
reviews_app = typer.Typer(help="Inspect immutable boundary reviews.")
retrieval_app = typer.Typer(help="Evaluate policy retriever release configurations.")
app.add_typer(policies_app, name="policies")
policies_app.add_typer(policy_sources_app, name="sources")
app.add_typer(repo_app, name="repo")
app.add_typer(atlas_app, name="atlas")
app.add_typer(case_app, name="case")
app.add_typer(reviews_app, name="reviews")
app.add_typer(retrieval_app, name="retrieval")


class RetrievalExampleFile(BaseModel):
    pattern: str
    expected_policy_ids: list[str]
    selected_policy_ids: list[str]
    required_policy_ids: list[str] = Field(default_factory=lambda: list[str]())
    scoped_policy_ids: list[str] = Field(default_factory=lambda: list[str]())
    reference_material: bool | None = None
    retrieved_material: bool | None = None

    def as_example(self) -> RetrievalExample:
        return RetrievalExample(
            self.pattern,
            frozenset(self.expected_policy_ids),
            tuple(self.selected_policy_ids),
            frozenset(self.required_policy_ids),
            frozenset(self.scoped_policy_ids),
            self.reference_material,
            self.retrieved_material,
        )


class RetrievalEvaluationFile(BaseModel):
    embedding_identity: str
    results: dict[int, list[RetrievalExampleFile]]


class CaseWriteFile(BaseModel):
    """A case file, which is now only a policy scope.

    It carried constraints and decisions, and this was the only way to write one: no screen
    offered it and no review produced it. Intent reaches a case by answering the question a
    judgement raised, which is a thing the product does rather than a file somebody keeps.
    """

    policy_context: PolicyContext = PolicyContext()


@retrieval_app.command("evaluate")
def evaluate_retriever(
    source: Annotated[Path, typer.Option("--from", exists=True, dir_okay=False)],
) -> None:
    """Select the smallest passing K from recorded reference runs."""

    document = RetrievalEvaluationFile.model_validate(_read_yaml(source))
    top_k, evaluation = choose_smallest_passing_k(
        lambda candidate_k: tuple(
            item.as_example() for item in document.results.get(candidate_k, [])
        )
    )
    typer.echo(
        f"dense-scoped evaluation passed for {document.embedding_identity} at K={top_k} "
        f"(macro recall {evaluation.macro_recall:.3f})."
    )


class CLIState:
    def __init__(self, workspace: Path, pin: ReasoningModelConfig | None) -> None:
        self.workspace = workspace
        self.pin = pin
        self._runtime: Runtime | None = None

    @property
    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(self.workspace, pin=self.pin)
        return self._runtime

    def runtime_for_repository(self, repository: Path) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(
                self.workspace,
                pin=self.pin,
                repository=repository,
            )
        else:
            validate_repository_directory(repository)
        return self._runtime

    def set_runtime(self, runtime: Runtime) -> None:
        self._runtime = runtime


@app.callback()
def root_callback(
    context: typer.Context,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            help="Workspace containing state and reports.",
            file_okay=False,
        ),
    ] = Path("."),
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Reason with this provider for this run only."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Reason with this model for this run only."),
    ] = None,
    thinking: Annotated[
        str | None,
        typer.Option(
            "--thinking",
            help=(
                "How hard the model thinks before answering: on, off, or one of minimal, "
                "low, medium, high where the provider has levels. Omitted leaves it to the "
                "model, which is a behaviour of its own rather than the absence of the rest."
            ),
        ),
    ] = None,
) -> None:
    # Both or neither. A provider without a model names no model to run, and a model without
    # a provider names no way to reach it; either alone would have to be completed by a
    # guess, and which model a review runs against decides what it costs and how long it
    # takes. `--thinking` is only meaningful alongside them, so it is refused on its own for
    # the same reason rather than silently ignored.
    if (provider is None) != (model is None):
        raise typer.BadParameter("--provider and --model are given together or not at all")
    if provider is None and thinking is not None:
        raise typer.BadParameter("--thinking needs --provider and --model")
    pin = (
        pinned_model(provider, model, _thinking_mode(thinking))
        if provider is not None and model is not None
        else None
    )
    context.obj = CLIState(workspace.expanduser().resolve(), pin)


def _thinking_mode(given: str | None) -> ThinkingMode:
    """One word off a command line as a thinking mode, refused by name if it is neither.

    `on` and `off` are kept because a switch is what somebody types when they do not care
    which level, and because they were the flag this option replaced. Where the provider has
    levels they are read as its ends.
    """

    if given is None:
        return None
    word = given.strip().casefold()
    if word in {"on", "true", "yes"}:
        return True
    if word in {"off", "false", "no"}:
        return False
    if word in THINKING_LEVELS:
        return cast("ThinkingMode", word)
    raise typer.BadParameter(
        f"--thinking takes on, off, or one of {', '.join(THINKING_LEVELS)}; not {given!r}"
    )


@app.command("init")
def initialize(context: typer.Context) -> None:
    """Create the workspace directory and its database without overwriting anything."""
    state = _state(context)
    runtime = initialize_workspace_runtime(state.workspace, pin=state.pin)
    state.set_runtime(runtime)
    typer.echo(f"Workspace ready: {runtime.workspace}")


@app.command("web")
def web(
    context: typer.Context,
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            help=(
                "Workspace containing state and reports. "
                "Defaults to the current directory (.)."
            ),
            file_okay=False,
        ),
    ] = None,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            min=1,
            max=65535,
            help="Loopback port for the local web workspace.",
        ),
    ] = 8765,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open/--no-open",
            help="Open the local workspace in the default browser.",
        ),
    ] = True,
) -> None:
    """Launch the local Arch Compass browser workspace."""
    import threading
    import webbrowser

    import uvicorn

    from archcompass.presentation.web import create_app

    state = _state(context)
    selected_workspace = (
        workspace.expanduser().resolve() if workspace is not None else state.workspace
    )
    runtime = initialize_workspace_runtime(selected_workspace, pin=state.pin)
    state.set_runtime(runtime)
    url = f"http://127.0.0.1:{port}"
    typer.echo(f"Arch Compass web workspace: {url}")
    if open_browser:
        threading.Timer(0.75, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        create_app(runtime),
        host="127.0.0.1",
        port=port,
        access_log=False,
    )


# No manual `rebuild`. Policies are read from their sources whenever requested, and the
# selected retriever updates its content-hashed derived index incrementally.


@policies_app.command("list")
def policies_list(
    context: typer.Context,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Also read <repo>/.archcompass/policies."),
    ] = None,
) -> None:
    catalog = _state(context).runtime.policy_service.catalog(repository_root=repo)
    for policy in catalog:
        typer.echo(f"{policy.id}\t{policy.scope}\t{policy.strength}\t{policy.title}")


@policies_app.command("show")
def policies_show(
    context: typer.Context,
    policy_id: str,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Also read <repo>/.archcompass/policies."),
    ] = None,
) -> None:
    policy = _state(context).runtime.policy_service.get(policy_id, repository_root=repo)
    typer.echo(policy.model_dump_json(indent=2))


@policy_sources_app.command("add")
def policy_sources_add(context: typer.Context, source: Path) -> None:
    registration = _state(context).runtime.policy_service.add_source(source)
    typer.echo(registration.model_dump_json(indent=2))


@policy_sources_app.command("remove")
def policy_sources_remove(context: typer.Context, source: Path) -> None:
    removed = _state(context).runtime.policy_service.remove_source(source)
    if not removed:
        raise typer.BadParameter(f"Policy source is not registered: {source}")
    typer.echo(f"Removed {source.expanduser().resolve(strict=False)}")


@policy_sources_app.command("list")
def policy_sources_list(context: typer.Context) -> None:
    registrations = _state(context).runtime.policy_service.list_sources()
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in registrations],
            indent=2,
        )
    )


@repo_app.command("index")
def repo_index(context: typer.Context, path: Path) -> None:
    version = _state(context).runtime_for_repository(path).repository_service.index(path)
    typer.echo(version.model_dump_json(indent=2))


@atlas_app.command("summary")
def atlas_summary(context: typer.Context, path: Path) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.summary(path)
    typer.echo(result.model_dump_json(indent=2))


@atlas_app.command("inspect")
def atlas_inspect(
    context: typer.Context,
    path: Path,
    node: Annotated[str, typer.Option("--node", help="Stable atlas node ID.")],
) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.inspect(
        path,
        node,
    )
    typer.echo(result.model_dump_json(indent=2))


@atlas_app.command("hotspots")
def atlas_hotspots(
    context: typer.Context,
    path: Path,
    metric: Annotated[
        str, typer.Option("--metric", help="One documented metric field name.")
    ] = "reverse_dependency_reach",
) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.hotspots(
        path,
        metric,
    )
    typer.echo(result.model_dump_json(indent=2))


@case_app.command("create")
def case_create(
    context: typer.Context,
    source: Annotated[Path, typer.Option("--from", help="ArchitectureCase YAML file.")],
) -> None:
    request = CaseWriteFile.model_validate(_read_yaml(source))
    case = _state(context).runtime.case_service.create(
        policy_context=request.policy_context
    )
    typer.echo(_case_json(case))


@case_app.command("show")
def case_show(context: typer.Context, case_id: str) -> None:
    typer.echo(_case_json(_state(context).runtime.case_service.show(case_id)))


@case_app.command("rescope")
def case_rescope(
    context: typer.Context,
    case_id: str,
    source: Annotated[Path, typer.Option("--from", help="Policy scope YAML file.")],
) -> None:
    """Change which policies this case can retrieve."""

    update = CaseWriteFile.model_validate(_read_yaml(source))
    case = _state(context).runtime.case_service.rescope(
        case_id, policy_context=update.policy_context
    )
    typer.echo(_case_json(case))


@case_app.command("history")
def case_history(context: typer.Context, case_id: str) -> None:
    revisions = _state(context).runtime.case_service.history(case_id)
    typer.echo(
        json.dumps(
            [_case_document(item) for item in revisions],
            indent=2,
        )
    )


def _case_json(case: ArchitectureCase) -> str:
    return json.dumps(_case_document(case), indent=2)


def _case_document(case: ArchitectureCase) -> dict[str, object]:
    document = TypeAdapter(ArchitectureCase).dump_python(case, mode="json")
    case_id = document.pop("id")
    return {"case_id": case_id, **document}


@app.command("review")
def review(
    context: typer.Context,
    case_id: str,
    repo: Annotated[
        Path,
        typer.Option("--repo", help="Repository whose indexed atlas should be reviewed."),
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the stored review instead of its Markdown.")
    ] = False,
) -> None:
    """Judge every boundary the detector finds in a repository against one case."""

    state = _state(context)
    runtime = state.runtime_for_repository(repo)
    try:
        repository_id, branch_id = runtime.atlas_service.repository_identity(repo)
    except ArchCompassError as error:
        raise typer.BadParameter(str(error)) from error
    stored = runtime.review_workflow_service.start(
        repository_id=repository_id,
        branch_id=branch_id,
        case_id=case_id,
    )
    typer.echo(
        TypeAdapter(Review).dump_json(stored, indent=2).decode()
        if as_json
        else stored.markdown_report
    )
    if stored.status.value == "awaiting_answers" and not as_json:
        typer.echo(
            "\nThis review is waiting on answers. Resume it with "
            f"`archcompass reviews answer {stored.id} --from answers.yaml`."
        )


class CLIAnswer(BaseModel):
    question_id: str = Field(min_length=1)
    status: AnswerStatus
    value: str | None = None
    actor: str = "user"


class CLIAnswerRound(BaseModel):
    answers: list[CLIAnswer] = Field(default_factory=lambda: list[CLIAnswer]())
    stop: bool = False


@reviews_app.command("answer")
def review_answer(
    context: typer.Context,
    review_id: str,
    source: Annotated[Path, typer.Option("--from", exists=True, dir_okay=False)],
) -> None:
    """Record answers and skips, then resume the review's graph thread."""

    payload = CLIAnswerRound.model_validate(_read_yaml(source))
    review = _state(context).runtime.review_workflow_service.resume(
        review_id,
        tuple(
            SubmittedAnswer(item.question_id, item.status, item.value, item.actor)
            for item in payload.answers
        ),
        stop=payload.stop,
    )
    typer.echo(TypeAdapter(Review).dump_json(review, indent=2).decode())


@app.command("ci")
def ci(
    context: typer.Context,
    case_id: str,
    repo: Annotated[
        Path,
        typer.Option("--repo", help="The checkout to index and review."),
    ],
    base_branch: Annotated[
        str,
        typer.Option(
            "--base-branch",
            help=(
                "The branch whose standing decisions this run also reads. Worth naming when "
                "the workspace has never indexed the branch this one was cut from, which is "
                "the ordinary shape of a pull request checked out by a pipeline."
            ),
        ),
    ] = DEFAULT_BRANCH_NAME,
    branch: Annotated[
        str | None,
        typer.Option(
            "--branch",
            help=(
                "The branch this checkout is on. Worth stating in CI, where the checkout is "
                "detached and only the environment knows which branch it came from."
            ),
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the machine document instead of the summary."),
    ] = False,
    comment_file: Annotated[
        Path | None,
        typer.Option(
            "--comment-file",
            help="Write the sticky pull-request comment, as Markdown, to this path.",
            dir_okay=False,
        ),
    ] = None,
    workspace_url: Annotated[
        str | None,
        typer.Option(
            "--workspace-url",
            help=(
                "Where this workspace is reachable, so the comment can link each boundary "
                "to it. Omitted, the comment names boundaries without linking them."
            ),
        ),
    ] = None,
    fail_on: Annotated[
        FailOn,
        typer.Option(
            "--fail-on",
            help=(
                "What this run exits nonzero for. `nothing` reports everything and fails "
                "for none of it, which is how a team adopts the check before agreeing "
                "with it."
            ),
        ),
    ] = FailOn.NEW_MATERIAL,
) -> None:
    """Review this checkout without asking anyone anything, and exit on what needs attention.

    The disciplined sibling of `review`: one pass, no questions, and a summary that leads
    with the revision partition — how much carried untouched, how much this revision judged,
    what closed. A run that would have asked reports the held verdicts with their questions
    and does not block on them: nobody is here to answer, and failing a pull request over an
    unasked question is how a check gets switched off.

    What blocks is a boundary this revision judged that is material and that nobody has
    decided about — accepted, waived or parked — read through the branch this one came from.

    Exit codes: 0 when nothing needs accounting for, 1 when something does, 2 for a run that
    could not happen at all.
    """

    state = _state(context)
    document = state.runtime_for_repository(repo).core_ci_service.run(
        case_id,
        repository_root=repo,
        base_branch=base_branch,
        branch_name=branch,
        fail_on=fail_on,
    )
    if comment_file is not None:
        comment_file.parent.mkdir(parents=True, exist_ok=True)
        comment_file.write_text(document.review.markdown_report or "", encoding="utf-8")
    typer.echo(
        TypeAdapter(CiRun).dump_json(document, indent=2).decode()
        if as_json
        else (document.review.markdown_report or "No report was produced.")
    )
    raise typer.Exit(code=document.exit_code)


@reviews_app.command("show")
def review_show(context: typer.Context, review_id: str) -> None:
    stored = _state(context).runtime.review_workflow_service.get(review_id)
    typer.echo(stored.markdown_report or TypeAdapter(Review).dump_json(stored).decode())


@reviews_app.command("ask")
def review_ask(
    context: typer.Context,
    review_id: str,
    question: str,
) -> None:
    """Ask a question about one review, continuing its conversation."""

    service = _state(context).runtime.review_conversation_service
    existing = service.list(review_id)
    conversation = existing[0] if existing else service.create(review_id)
    conversation = service.ask(conversation.id, question)
    message = conversation.messages[-1]
    typer.echo(message.answer.text)
    grounding = message.answer.supporting_candidate_ids
    typer.echo("")
    typer.echo(
        f"Grounded on {', '.join(grounding)}"
        if grounding
        else "Not grounded on any reviewed boundary."
    )


@reviews_app.command("history")
def review_history(context: typer.Context, review_id: str) -> None:
    conversations = _state(context).runtime.review_conversation_service.list(review_id)
    typer.echo(
        TypeAdapter(tuple[ReviewConversation, ...])
        .dump_json(conversations, indent=2)
        .decode()
    )


@reviews_app.command("list")
def review_list(
    context: typer.Context,
    case: Annotated[str | None, typer.Option("--case", help="Filter by case ID.")] = None,
) -> None:
    summaries = _state(context).runtime.review_workflow_service.list(case_id=case)
    typer.echo(TypeAdapter(tuple[Review, ...]).dump_json(summaries, indent=2).decode())


def _state(context: typer.Context) -> CLIState:
    if not isinstance(context.obj, CLIState):
        raise RuntimeError("CLI state was not initialized")
    return context.obj


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise typer.BadParameter(f"Could not read YAML {path}: {error}") from error


def main() -> None:
    try:
        app()
    except (ValidationError, ArchCompassError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(2) from None
