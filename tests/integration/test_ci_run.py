"""The headless check, end to end and through the command line a pipeline would call.

Real git repositories in `tmp_path`, because the whole of this feature turns on identity
that git supplies: a `repo_id` from the root commit, a branch named by the caller because the
checkout is detached, and a base branch whose standings the run reads through to. A stubbed
git would prove the stub.

What is asserted is the loop and the exit code, never the judgement. The deterministic
substitute reaches the verdicts, so what the advisor says is fixed by construction and the
claims here are about the partition, the blocking set, and what gets written where.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.application.ci import CiRun
from archcompass.application.ci_rendering import COMMENT_MARKER
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.delta import BoundaryState
from archcompass.domain.lineage import derive_branch_id
from archcompass.domain.triage import DecisionState, StandingDecision
from archcompass.presentation.cli.app import app

runner = CliRunner()

EXAMPLE = Path("eval/cases/warehouse-sync/repository").resolve()

#: A case that says what is coming, so no verdict hangs on an unanswered question and the run
#: concludes. The substitute hinges exactly when the case is silent about the future, which is
#: what makes both halves of this suite reachable from the same repository.
_SETTLED_CASE = {
    "title": "Warehouse sync boundaries",
    "problem_statement": (
        "A stock synchroniser declares boundaries with one implementation behind each."
    ),
    "desired_outcome": "A verdict per boundary, including the verdict that nothing changes.",
    "expected_future_changes": ["A second warehouse vendor is planned for this year."],
}

#: The same repository with nothing said about the future, which is what makes the first pass
#: hold: the verdicts that would turn on a coming change cannot be settled from the code.
_THIN_CASE = {
    "title": "Warehouse sync boundaries",
    "problem_statement": (
        "A stock synchroniser declares boundaries with one implementation behind each."
    ),
    "desired_outcome": "A verdict per boundary.",
}


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> Path:
    """The example repository, committed, so it has a root commit to be identified by."""

    repository = tmp_path / "repository"
    shutil.copytree(EXAMPLE, repository)
    _git(repository.parent, "init", "--quiet", "-b", "main", str(repository.name))
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "first")
    return repository


class Harness:
    """One workspace, one repository and one case: what every test here starts from."""

    def __init__(self, workspace: Path, repository: Path, case_id: str) -> None:
        self.workspace = workspace
        self.repository = repository
        self.case_id = case_id

    @property
    def common(self) -> list[str]:
        return [
            "--workspace",
            str(self.workspace),
            "--provider",
            "fake",
            "--model",
            DETERMINISTIC_MODEL,
        ]

    def ci(self, *arguments: str) -> tuple[int, str]:
        result = runner.invoke(
            app,
            [
                *self.common,
                "ci",
                self.case_id,
                "--repo",
                str(self.repository),
                *arguments,
            ],
        )
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        return result.exit_code, result.output

    def document(self, *arguments: str) -> tuple[int, CiRun]:
        code, output = self.ci("--json", *arguments)
        return code, CiRun.model_validate(json.loads(output))

    def runtime(self) -> Runtime:
        return build_runtime(self.workspace, pin=pinned_model("fake", DETERMINISTIC_MODEL))


def _harness(tmp_path: Path, case: dict[str, object]) -> Harness:
    workspace = (tmp_path / "workspace").resolve()
    repository = _checkout(tmp_path)
    initialized = runner.invoke(app, ["--workspace", str(workspace), "init"])
    assert initialized.exit_code == 0, initialized.output
    case_path = tmp_path / "case.yaml"
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    harness = Harness(workspace, repository, "")
    created = runner.invoke(
        app, [*harness.common, "case", "create", "--from", str(case_path)]
    )
    assert created.exit_code == 0, created.output
    harness.case_id = str(json.loads(created.output)["case_id"])
    return harness


@pytest.fixture
def settled(tmp_path: Path) -> Harness:
    return _harness(tmp_path, dict(_SETTLED_CASE))


@pytest.fixture
def thin(tmp_path: Path) -> Harness:
    return _harness(tmp_path, dict(_THIN_CASE))


def _adopt(harness: Harness, run: CiRun, branch_id: str) -> int:
    """Decide, in one act with one author, on everything this run says needs attention.

    The replacement for bulk baselining, and the shape a team adopting a legacy repository
    actually uses. Every boundary gets a real standing decision rather than a row saying
    somebody looked at a list.
    """

    return len(
        harness.runtime().triage_service.decide_many(
            [
                StandingDecision(
                    branch_id=branch_id,
                    boundary_fingerprint=str(item.fingerprint),
                    state=DecisionState.ACCEPTED,
                    author="Deniz",
                    review_id=run.review_id,
                    boundary_reference=item.reference,
                    material=item.material,
                    verdict_label=item.verdict_label,
                )
                for item in run.boundaries
                if item.needs_attention
            ]
        )
    )


def test_a_first_run_on_an_unadopted_repository_judges_everything(
    settled: Harness,
) -> None:
    """No previous revision, so nothing carries, and the undecided material findings block."""

    code, document = settled.document()

    assert document.first_revision is True
    assert document.previous_review_id is None
    assert document.counts.carried == 0
    assert document.counts.judged == len(document.boundaries)
    assert [item.delta_state for item in document.boundaries] == [
        BoundaryState.JUDGED
    ] * len(document.boundaries)
    blocking = [item.reference for item in document.boundaries if item.material]
    assert document.blocking == blocking, "every material boundary is unaccounted for"
    assert document.counts.attention == len(blocking)
    assert blocking, "the example is here to produce something to account for"
    assert code == 1
    assert document.exit_code == 1


def test_a_second_run_over_untouched_code_carries_everything_and_is_clean(
    settled: Harness,
) -> None:
    """Run two is quieter than run one, and not because anybody pressed a button.

    The boundaries are still material and still undecided — nobody has agreed with anything —
    and the check passes because nothing about them moved. That is the delta replacing the
    baseline: quiet by knowing, rather than quiet by declaration.
    """

    first_code, first = settled.document()
    assert first_code == 1

    code, document = settled.document()

    assert document.first_revision is False
    assert document.previous_review_id == first.review_id
    assert document.counts.judged == 0
    assert document.counts.carried == len(document.boundaries)
    assert document.blocking == []
    assert code == 0
    # The verdicts were not reached a second time. Nothing in the repository moved, so the
    # cache answered and the document says so rather than implying a fresh judgement.
    assert document.counts.verdicts_reused == document.counts.verdicts_total


def test_adopting_a_repository_by_deciding_in_bulk_makes_the_check_clean(
    settled: Harness,
) -> None:
    """The replacement for bulk baselining, asserted where it matters: through the check.

    Every boundary the first run blocked on is accepted in one act with one author, and the
    next run has nothing to account for — with a name behind every silence, which is what the
    baseline could never supply.
    """

    _, first = settled.document()
    assert first.blocking
    assert first.branch_id is not None

    assert _adopt(settled, first, first.branch_id) == first.counts.attention

    code, document = settled.document()

    assert document.counts.attention == 0
    assert document.blocking == []
    assert code == 0
    assert all(
        item.decision is not None and item.decision.author == "Deniz"
        for item in document.boundaries
        if item.material
    ), "the silence names who bought it"


def test_a_waiver_on_the_base_branch_silences_a_new_boundary_without_hiding_it(
    settled: Harness,
) -> None:
    """The team's recorded disagreement is an outcome, not a deletion."""

    _, first = settled.document()
    waived = first.blocking[0]
    boundary = next(item for item in first.boundaries if item.reference == waived)
    assert boundary.fingerprint is not None
    runtime = settled.runtime()
    assert first.base_branch_id is not None
    runtime.triage_service.decide(
        StandingDecision(
            branch_id=first.base_branch_id,
            boundary_fingerprint=boundary.fingerprint,
            state=DecisionState.WAIVED,
            author="Deniz",
            reason="Intentional seam for the billing split.",
            review_id=first.review_id,
            boundary_reference=boundary.reference,
            material=boundary.material,
            verdict_label=boundary.verdict_label,
        )
    )

    code, document = settled.document()

    after = next(item for item in document.boundaries if item.reference == waived)
    assert after.needs_attention is False, "a decision is what makes a boundary quiet"
    assert after.blocking is False
    assert waived not in document.blocking
    assert after.decision is not None
    assert after.decision.state is DecisionState.WAIVED
    assert after.decision.author == "Deniz"
    assert after.decision.taken_on_this_verdict is True
    assert code == (1 if document.blocking else 0)


def test_failing_for_nothing_reports_the_same_findings_and_exits_clean(
    settled: Harness,
) -> None:
    """Adoption mode: the whole document, none of the consequences."""

    code, document = settled.document("--fail-on", "nothing")

    assert document.blocking, "the findings are still reported"
    assert document.fail_on.value == "nothing"
    assert document.exit_code == 0
    assert code == 0


def test_a_run_that_would_have_asked_reports_the_questions_and_does_not_block_on_them(
    thin: Harness,
) -> None:
    """Nobody is here to answer, so a held verdict is information rather than a failure."""

    _, document = thin.document()

    held = [item for item in document.boundaries if item.holding]
    assert held, "the thin case is here to leave verdicts hanging"
    assert document.counts.holding == len(held)
    assert document.status.value == "awaiting_answers"
    for item in held:
        assert item.blocking is False
        assert item.reference not in document.blocking
        assert item.questions, "a held boundary carries what would settle it"
        assert all(question.question for question in item.questions)


def test_the_comment_file_carries_the_marker_and_the_verdicts_verbatim(
    settled: Harness, tmp_path: Path
) -> None:
    """One comment an Action can find and edit, quoting the review rather than retelling it."""

    comment_path = tmp_path / "comments" / "archcompass.md"
    code, document = settled.document("--comment-file", str(comment_path))

    assert code == 1
    comment = comment_path.read_text(encoding="utf-8")
    assert comment.splitlines()[0] == COMMENT_MARKER
    surfaced = [
        item
        for item in document.boundaries
        if item.delta_state is not BoundaryState.CARRIED
    ]
    for item in surfaced:
        assert item.verdict_label in comment
    assert document.review_id in comment
    assert (
        f"{document.counts.verdicts_reused} of {document.counts.verdicts_total} verdicts "
        "reused from earlier runs" in comment
    )


def test_the_json_document_round_trips_through_its_model(settled: Harness) -> None:
    """The document is what a pipeline parses, so it has to survive the trip unchanged."""

    _, output = settled.ci("--json")
    parsed = CiRun.model_validate(json.loads(output))

    assert json.loads(parsed.model_dump_json()) == json.loads(output)


def test_the_run_is_filed_under_the_branch_it_was_told_it_is_on(settled: Harness) -> None:
    """A detached CI checkout knows its commit and not its branch; the caller states it."""

    code, document = settled.document("--branch", "feature/split", "--base-branch", "main")

    assert document.repo_id is not None
    assert document.branch_id == derive_branch_id(document.repo_id, "feature/split")
    assert document.base_branch_id == derive_branch_id(document.repo_id, "main")
    assert document.base_branch_name == "main"
    assert code == 1


def test_a_pull_request_branch_reads_the_base_branch_standings(settled: Harness) -> None:
    """The point of the read-through: a fresh lineage is not a fresh repository.

    The feature branch has decided nothing and has no previous revision of its own, so every
    boundary is judged on it — and none of them blocks, because what `main` accepted applies
    here until this branch says otherwise.
    """

    _, first = settled.document()
    assert first.branch_id is not None
    _adopt(settled, first, first.branch_id)

    code, document = settled.document("--branch", "feature/split")

    assert document.branch_id != document.base_branch_id
    assert document.first_revision is True, "the branch's own line starts here"
    assert document.counts.attention == 0
    assert document.blocking == []
    assert code == 0


def test_the_human_summary_leads_with_the_partition(settled: Harness) -> None:
    """A reader has to be able to tell an adopted repository from an unadopted one at a
    glance, without reading a single finding."""

    code, output = settled.ci()

    assert code == 1
    assert "0 carried, " in output
    assert "needing attention" in output
    assert "held on an open question" in output
