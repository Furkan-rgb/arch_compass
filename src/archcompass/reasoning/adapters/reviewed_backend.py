"""The reviewed repository, offered to a Deep Agents filesystem as four read-only tools.

A thin adaptation and deliberately nothing more. Everything about *which* snapshot is being
read, and about refusing a working tree that has moved, belongs to `ReviewedSource` and is
tested there; what is here is the vendor's own result shapes and the four method names it
calls.

Only `ls`, `read_file`, `glob` and `grep` are ever exposed — `FilesystemMiddleware` takes an
allowlist, so `write_file`, `edit_file`, `delete` and `execute` are absent from the model's
toolset rather than present and refused. The inherited implementations of those remain on
`BackendProtocol` and are unreachable: nothing can call a tool that was never offered.

`StaleAtlasError` is turned into the result's `error` sentence rather than propagated. That
is the same choice `AtlasInvestigator.call` already makes and for the same reason: the model
has to be told the source could not be read, because an empty answer reads as "there is
nothing there" and would be weighed as evidence of absence.
"""

from __future__ import annotations

from deepagents.backends.protocol import (
    BackendProtocol,
    FileData,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
)
from deepagents.backends.utils import slice_read_response

from archcompass.domain.errors import ArchCompassError
from archcompass.reasoning.ports import ReviewedSource

#: Ceilings on one answer, not on how much a judgement may look at. A pattern matching ten
#: thousand lines is a pattern nobody meant to write, and the whole of it would crowd out the
#: judgement it was meant to inform.
MAX_MATCHES = 200
MAX_PATHS = 400


class ReviewedRevisionBackend(BackendProtocol):
    def __init__(self, source: ReviewedSource) -> None:
        self._source = source

    def ls(self, path: str) -> LsResult:
        try:
            entries = self._source.list_directory(path)
        except ArchCompassError as error:
            return LsResult(error=str(error))
        return LsResult(entries=[FileInfo(path=item) for item in entries])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            # Read whole and sliced by the vendor's own helper, so offset, limit and the
            # "more to come" bookkeeping behave exactly as they do for its other backends.
            text = self._source.read_file(file_path, offset=0, limit=1_000_000)
        except ArchCompassError as error:
            return ReadResult(error=str(error))
        if not text:
            return ReadResult(error=f"'{file_path}' is not in the revision under review.")
        return slice_read_response(FileData(content=text, encoding="utf-8"), offset, limit)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        try:
            found = self._source.find_paths(pattern, within=path, limit=MAX_PATHS + 1)
        except ArchCompassError as error:
            return GlobResult(error=str(error))
        return GlobResult(
            matches=[FileInfo(path=item) for item in found[:MAX_PATHS]],
            truncated=len(found) > MAX_PATHS,
        )

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        limit = min(max_count or MAX_MATCHES, MAX_MATCHES)
        try:
            found = self._source.search_lines(
                pattern, within=path, name_pattern=glob, limit=limit + 1
            )
        except ArchCompassError as error:
            return GrepResult(error=str(error))
        return GrepResult(
            matches=[
                GrepMatch(path=item.path, line=item.line, text=item.text)
                for item in found[:limit]
            ],
            truncated=len(found) > limit,
        )
