"""The single rule for whether a cited source span is supported by surfaced evidence.

Repository observations are only as trustworthy as the span they cite. Three layers
need the same answer — the workflow when it accepts a concern analysis, the
application when it validates or repairs a report, and any adapter that must decide
whether a claim can survive repair — so the containment rule lives here rather than
being restated at each site.

Callers keep their own policy about a *missing* location, because that differs
legitimately: a repository observation must carry one, while a claim of another
classification may cite a node without naming a span.
"""

from __future__ import annotations

from archcompass.domain.atlas import AtlasNode, SourceLocation


def node_source_span(node: AtlasNode) -> SourceLocation | None:
    """The span an Atlas node occupies, when the analyzer recorded one."""

    if node.start_line is None or node.end_line is None:
        return None
    return SourceLocation(
        path=node.path,
        start_line=node.start_line,
        end_line=node.end_line,
    )


def location_within(
    container: SourceLocation | None,
    reference: SourceLocation | None,
) -> bool:
    """True when `reference` names the same path and lies inside `container`.

    An absent container or reference is not containment: a span cannot be verified
    against evidence that does not state its own extent.
    """

    if container is None or reference is None:
        return False
    return (
        reference.path == container.path
        and reference.start_line >= container.start_line
        and reference.end_line <= container.end_line
    )
