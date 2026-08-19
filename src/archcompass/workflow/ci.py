"""Headless use of the same clean-break review graph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from archcompass.domain import Review, Verdict
from archcompass.domain.repository import DEFAULT_BRANCH_NAME, derive_branch_id
from archcompass.repositories.service import RepositoryIndexService
from archcompass.workflow.decisions import StandingDecisionService
from archcompass.workflow.service import ReviewWorkflowService


class FailOn(StrEnum):
    NEW_MATERIAL = "new-material"
    NOTHING = "nothing"


@dataclass(frozen=True, slots=True)
class CiFinding:
    candidate_id: str
    summary: str
    verdict: str
    reasoning: str
    newly_judged: bool
    holding: bool
    decided: bool
    blocking: bool


@dataclass(frozen=True, slots=True)
class CleanBreakCiRun:
    review: Review
    findings: tuple[CiFinding, ...]
    blocking_candidate_ids: tuple[str, ...]
    fail_on: FailOn
    exit_code: int


class CleanBreakCiRunService:
    def __init__(
        self,
        *,
        repositories: RepositoryIndexService,
        workflow: ReviewWorkflowService,
        decisions: StandingDecisionService,
    ) -> None:
        self._repositories = repositories
        self._workflow = workflow
        self._decisions = decisions

    def run(
        self,
        case_id: str,
        *,
        repository_root: Path,
        base_branch: str = DEFAULT_BRANCH_NAME,
        branch_name: str | None = None,
        fail_on: FailOn = FailOn.NEW_MATERIAL,
    ) -> CleanBreakCiRun:
        version = self._repositories.index(repository_root, branch_name=branch_name)
        if version.repo_id is None or version.branch_id is None:
            raise ValueError("CI indexing did not establish repository lineage")
        review = self._workflow.start(
            repository_id=version.repo_id,
            branch_id=version.branch_id,
            case_id=case_id,
            ci=True,
        )
        base_id = derive_branch_id(version.repo_id, base_branch)
        standings = self._decisions.standings(base_id, version.branch_id)
        judged = {str(item.id) for item in review.delta.new} | {
            str(item.candidate.id) for item in review.delta.changed
        }
        predecessors = {
            str(item.candidate.id): str(item.predecessor_id)
            for item in review.delta.changed
            if item.predecessor_id is not None
        }
        entries: list[CiFinding] = []
        blocking: list[str] = []
        for finding in review.findings:
            candidate_id = str(finding.candidate.id)
            newly_judged = candidate_id in judged
            holding = finding.verdict is Verdict.HELD
            decided = candidate_id in standings or predecessors.get(candidate_id) in standings
            blocks = (
                newly_judged
                and finding.verdict is Verdict.MATERIAL
                and not holding
                and not decided
            )
            if blocks:
                blocking.append(candidate_id)
            entries.append(
                CiFinding(
                    candidate_id,
                    finding.candidate.summary,
                    finding.verdict.value,
                    finding.reasoning,
                    newly_judged,
                    holding,
                    decided,
                    blocks,
                )
            )
        return CleanBreakCiRun(
            review,
            tuple(entries),
            tuple(blocking),
            fail_on,
            1 if blocking and fail_on is FailOn.NEW_MATERIAL else 0,
        )
