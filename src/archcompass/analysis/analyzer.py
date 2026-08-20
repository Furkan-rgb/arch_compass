"""Boundary codecs for the deterministic analyzer and detector catalogue."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from archcompass.analysis.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    FindingCandidate,
    FindingParticipant,
    MetricProfile,
    ModuleFacts,
    ObscuritySignal,
)
from archcompass.analysis.detectors import detect_finding_candidates
from archcompass.domain import (
    Candidate,
    Evidence,
    Measurement,
    MetricNature,
    Participant,
    Relationship,
    RepositoryAtlas,
    RepositoryRef,
    SourceLocation,
)
from archcompass.ports.atlas import RepositoryAnalyzer as AnalyzerRecordSource
from archcompass.ports.persistence import ScopeSelectionRepository


def _documents(values: Sequence[BaseModel]) -> tuple[str, ...]:
    return tuple(value.model_dump_json() for value in values)


class DataclassRepositoryAnalyzer:
    """The graph's own analysis of a repository, under the scope that repository was given.

    The scope is read here rather than passed in because the graph has no field for one and
    should not grow one: a review is about a repository, and how much of that repository is
    read is a property of the repository rather than of this run. Every other reader of an
    atlas already resolves it the same way — the index that built it, the freshness check
    that validates it — and this was the one that did not, so a review of a repository
    somebody had narrowed re-read the folders they left out and judged boundaries the atlas
    on the repositories page did not contain.
    """

    def __init__(
        self,
        analyzer: AnalyzerRecordSource,
        scope_selections: ScopeSelectionRepository,
    ) -> None:
        self._analyzer = analyzer
        self._scope_selections = scope_selections

    def analyze(self, repository: RepositoryRef) -> RepositoryAtlas:
        # Keyed by the canonical root, which is the string a recorded selection is filed
        # under and the string a stored atlas holds. `strict=False` because a root that is
        # not there is the analyzer's error to report, in its own words, a line below.
        recorded = self._scope_selections.get(
            str(repository.path.expanduser().resolve(strict=False))
        )
        atlas = self._analyzer.analyze(repository.path, excluded_paths=recorded or ())
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
        names = {node.atlas_id: node.qualified_name for node in old.nodes}
        return tuple(
            self._candidate(item, atlas.repository.path, names)
            for item in detect_finding_candidates(old)
        )

    @staticmethod
    def _candidate(
        item: FindingCandidate, root: Path, names: Mapping[str, str]
    ) -> Candidate:
        participants = tuple(
            Participant(participant.qualified_name, participant.role)
            for participant in item.participants
        )
        evidence = tuple(_evidence(participant, root) for participant in item.participants)
        participant_fingerprint = sha256(
            chr(0).join(participant.qualified_name for participant in participants).encode()
        ).hexdigest()
        return Candidate.identified(
            pattern=item.pattern.value,
            summary=item.summary,
            participants=participants,
            evidence=evidence,
            measurements=tuple(
                Measurement(
                    name=measurement.name,
                    value=measurement.value,
                    unit=measurement.unit,
                    nature=MetricNature(measurement.nature.value),
                    definition=measurement.definition,
                    limitations=measurement.limitations,
                )
                for measurement in item.measurements
            ),
            # Edge endpoints are atlas ids in the record and qualified names here. The
            # atlas is in hand at exactly this point and nowhere downstream, so resolving
            # them is free now and impossible later.
            relationships=tuple(
                Relationship(
                    source=names.get(edge.source_id, edge.source_id),
                    target=names.get(edge.target_id, edge.target_id),
                    kind=edge.edge_type.value,
                    resolved_by=edge.resolved_by,
                )
                for edge in item.relationships
            ),
            detection_rationale=(
                "Detected deterministically from the repository atlas; participant "
                f"fingerprint {participant_fingerprint}."
            ),
            limitations=item.limitations,
        )


#: The most lines one participant's excerpt may carry, before its leading comment is added.
#: A detector picks declaration spans — one line for a duplicated constant, a handful for a
#: class — so this is a guard against a pathological span rather than a budget anyone meets.
#: Raising it to 200 did not buy a bigger view: the largest span in this repository is 1,676
#: lines, so the excerpt is a fragment at either ceiling, and all the higher one changed is
#: whether it looks like one.
MAX_EXCERPT_LINES = 60

#: How far above a participant's span the leading comment block may reach. A constant's
#: recorded span is the line that assigns it, and what the constant *means* is written
#: directly above it — which is why the judging stage, shown the assignment alone, was
#: deciding whether two copies state one fact with the sentence answering it out of frame.
#: Bounded because a file that opens with a licence header is not a file whose first
#: constant means forty lines of licence.
MAX_LEADING_COMMENT_LINES = 12


def _evidence(participant: FindingParticipant, root: Path) -> Evidence:
    """One participant as evidence: what it contributes, where, and the code there.

    The recorded location is the span the excerpt actually covers rather than the span the
    detector named, because a reader is shown these line numbers beside these lines. Where
    the two differ the note says so, and says where the declaration itself begins.
    """

    location = participant.location
    if location is None:
        return Evidence(participant.role)
    named = SourceLocation(location.path, location.start_line, location.end_line)
    read = _source_excerpt(root, location.path, location.start_line, location.end_line)
    if read is None:
        return Evidence(participant.role, named)
    text, first, last = read
    notes: list[str] = []
    if first < location.start_line:
        notes.append(
            f"Widened upward over {location.start_line - first} comment line(s); the "
            f"declaration begins at line {location.start_line}."
        )
    if last < location.end_line:
        notes.append(
            f"Truncated to {MAX_EXCERPT_LINES} lines. The full span runs to line "
            f"{location.end_line} — {location.end_line - location.start_line + 1} lines — "
            "so this is an opening fragment, not the whole of it."
        )
    return Evidence(
        participant.role,
        SourceLocation(location.path, first, last),
        text,
        " ".join(notes) or None,
    )


def _source_excerpt(
    root: Path, relative: str, start: int, end: int
) -> tuple[str, int, int] | None:
    """The code at one recorded span, with the span the excerpt ended up covering."""

    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError):
        return None
    first = _with_leading_comment(lines, start)
    # Evidence is deliberately bounded even if a malformed analyzer record names a huge span.
    last = min(end, first + MAX_EXCERPT_LINES - 1)
    text = "\n".join(lines[first - 1 : last])
    return (text, first, last) if text else None


def _with_leading_comment(lines: list[str], start: int) -> int:
    """Widen a span upward over the contiguous comment block immediately above it.

    Contiguous and comments only: a blank line ends the block, so a constant separated from
    the file's licence header by whitespace does not inherit it.
    """

    first = start
    while first > 1 and start - first < MAX_LEADING_COMMENT_LINES:
        if not lines[first - 2].strip().startswith("#"):
            break
        first -= 1
    return first
