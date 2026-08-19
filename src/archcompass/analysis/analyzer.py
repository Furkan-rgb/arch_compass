"""Boundary codecs for the deterministic analyzer and detector catalogue."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from archcompass.analysis.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    FindingCandidate,
    MetricProfile,
    ModuleFacts,
    ObscuritySignal,
)
from archcompass.analysis.detectors import detect_finding_candidates
from archcompass.domain import (
    Candidate,
    Evidence,
    Participant,
    RepositoryAtlas,
    RepositoryRef,
    SourceLocation,
)
from archcompass.ports.atlas import RepositoryAnalyzer as AnalyzerRecordSource


def _documents(values: Sequence[BaseModel]) -> tuple[str, ...]:
    return tuple(value.model_dump_json() for value in values)


class DataclassRepositoryAnalyzer:
    def __init__(self, analyzer: AnalyzerRecordSource) -> None:
        self._analyzer = analyzer

    def analyze(self, repository: RepositoryRef) -> RepositoryAtlas:
        atlas = self._analyzer.analyze(repository.path)
        version = atlas.version
        current = RepositoryRef(
            id=repository.id,
            path=repository.path,
            branch_id=repository.branch_id,
            content_id=version.content_fingerprint,
            remote_url=repository.remote_url,
            branch=version.branch_name or repository.branch,
            commit=version.git_commit_sha,
        )
        return RepositoryAtlas(
            id=version.version_id,
            repository=current,
            nodes=_documents(atlas.nodes),
            edges=_documents(atlas.edges),
            metrics=_documents(atlas.metrics),
            facts=_documents(atlas.module_facts),
            signals=_documents(atlas.signals),
            parser_configuration=(
                ("parser", version.parser_version),
                ("analysis", version.analysis_config_hash),
            ),
        )


class DataclassCandidateDetector:
    """Run the characterized detectors after validating the atlas boundary records."""

    def detect(self, atlas: RepositoryAtlas) -> tuple[Candidate, ...]:
        old = Atlas(
            version=AtlasVersion(
                version_id=atlas.id,
                repository_identity=atlas.repository.id,
                root_path=str(atlas.repository.path),
                git_commit_sha=atlas.repository.commit,
                branch_name=atlas.repository.branch,
                repo_id=atlas.repository.id,
                branch_id=atlas.repository.branch_id,
                content_fingerprint=atlas.repository.content_id,
                parser_version=dict(atlas.parser_configuration).get("parser", "unknown"),
                analysis_config_hash=dict(atlas.parser_configuration).get(
                    "analysis", "unknown"
                ),
            ),
            nodes=[AtlasNode.model_validate_json(item) for item in atlas.nodes],
            edges=[AtlasEdge.model_validate_json(item) for item in atlas.edges],
            metrics=[MetricProfile.model_validate_json(item) for item in atlas.metrics],
            module_facts=[ModuleFacts.model_validate_json(item) for item in atlas.facts],
            signals=[ObscuritySignal.model_validate_json(item) for item in atlas.signals],
        )
        return tuple(
            self._candidate(item, atlas.repository.path)
            for item in detect_finding_candidates(old)
        )

    @staticmethod
    def _candidate(item: FindingCandidate, root: Path) -> Candidate:
        participants = tuple(
            Participant(participant.qualified_name, participant.role)
            for participant in item.participants
        )
        evidence = tuple(
            Evidence(
                participant.role,
                None
                if participant.location is None
                else SourceLocation(
                    participant.location.path,
                    participant.location.start_line,
                    participant.location.end_line,
                ),
                None
                if participant.location is None
                else _source_excerpt(
                    root,
                    participant.location.path,
                    participant.location.start_line,
                    participant.location.end_line,
                ),
            )
            for participant in item.participants
        )
        participant_fingerprint = sha256(
            chr(0).join(participant.qualified_name for participant in participants).encode()
        ).hexdigest()
        return Candidate.identified(
            pattern=item.pattern.value,
            summary=item.summary,
            participants=participants,
            evidence=evidence,
            measurements=tuple(
                (measurement.name, f"{measurement.value:g} {measurement.unit}".strip())
                for measurement in item.measurements
            ),
            detection_rationale=(
                "Detected deterministically from the repository atlas; participant "
                f"fingerprint {participant_fingerprint}."
            ),
            limitations=item.limitations,
        )


def _source_excerpt(root: Path, relative: str, start: int, end: int) -> str | None:
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError):
        return None
    # Evidence is deliberately bounded even if a malformed analyzer record names a huge span.
    last = min(end, start + 199)
    return "\n".join(lines[start - 1 : last]) or None
