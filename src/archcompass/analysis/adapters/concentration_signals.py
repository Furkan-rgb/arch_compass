"""Where one module has become the place several parts of the repository go through.

Nothing here parses anything. The concentration question is asked entirely of metrics the
analyser has already computed — how many names a module declares, which modules import it,
how far a change to it reaches — because the fact worth reporting is about the repository's
shape rather than about any line of code, and a second pass over the trees would only find
the same shape again more slowly.

The signal is a proxy and is labelled as one. A count of names and dependants cannot see
whether they belong together, which is exactly the judgement the
`judge-concentration-by-who-pays` policy asks a reader to make. This says where to look.
"""

from __future__ import annotations

from archcompass.analysis.atlas import (
    AtlasNode,
    MetricNature,
    MetricProfile,
    NodeType,
    ObscuritySignal,
    SourceLocation,
)

#: Packages other than the module's own that import it directly. Three rather than two
#: because two neighbouring packages sharing something is how a shared thing is supposed to
#: look; the third is where "shared by its neighbours" turns into "reached from everywhere".
_MINIMUM_DEPENDANT_PACKAGES = 3

#: Public top-level names the module declares. The count that separates a module reached
#: through one narrow seam from one whose callers each pull their own thing out: a deep
#: module can be any size behind a small surface, and this fires on the surface.
_MINIMUM_PUBLIC_SYMBOLS = 8

#: Modules under it in the reverse import-and-call impact graph. The cost half of the
#: judgement — a wide surface nobody depends on taxes nobody.
_MINIMUM_AFFECTED_MODULES = 8


def concentrated_scope_signals(
    nodes: dict[str, AtlasNode],
    profiles: list[MetricProfile],
) -> list[ObscuritySignal]:
    """Report modules whose public surface is pulled on from several packages at once.

    The rule is three absolute structural statements and not a percentile, deliberately.
    A percentile always has a top: run against a repository whose decomposition is in good
    order and it reports the least bad module in it, and run against one that is genuinely
    tangled and it hides everything below the cut. It also makes the same module fire or
    not depending on what else happens to be in the checkout, which would mean a review of
    one directory and a review of its parent disagreed about the same file. An absolute
    statement is answerable — a reader can check every number in the message against the
    code — and a repository in good order can honestly report nothing.

    The three have to hold together, because each alone is something healthy. A wide public
    surface is what a library module is for. Many dependants is what a well-used abstraction
    earns. A long reverse impact reach is what being depended upon means. What none of them
    is on its own, and all three are together, is a module where several packages each reach
    for a different name and every change lands on all of them.

    A test module is neither a subject nor a dependant here. A test imports whatever it
    exercises, so counting tests as dependants would make the best-covered module in a
    repository look like the most concentrated one, and a test file's own surface is its
    cases. Impact reach is the metric as computed and does count test modules — that is what
    `likely_affected_modules` means everywhere else, and a signal that quietly used a
    different number than the one shown beside it would be worse than a generous one.
    """

    profile_by_node = {profile.node_id: profile for profile in profiles}
    signals: list[ObscuritySignal] = []
    for node in sorted(nodes.values(), key=lambda item: item.atlas_id):
        if node.node_type != NodeType.MODULE:
            continue
        profile = profile_by_node.get(node.atlas_id)
        if profile is None:
            continue
        public_symbols = profile.local.public_symbol_count
        affected = profile.change_amplification.likely_affected_modules
        packages = _dependant_packages(node, profile, nodes)
        if (
            public_symbols < _MINIMUM_PUBLIC_SYMBOLS
            or len(packages) < _MINIMUM_DEPENDANT_PACKAGES
            or affected < _MINIMUM_AFFECTED_MODULES
        ):
            continue
        signals.append(
            ObscuritySignal(
                code="concentrated-scope",
                message=(
                    f"{node.qualified_name} declares {public_symbols} public names and is "
                    f"imported from {len(packages)} other packages "
                    f"({', '.join(sorted(packages))}); a change to it reaches "
                    f"{affected} modules."
                ),
                node_id=node.atlas_id,
                location=(
                    SourceLocation(
                        path=node.path,
                        start_line=node.start_line,
                        end_line=node.end_line,
                    )
                    if node.start_line is not None and node.end_line is not None
                    else None
                ),
                nature=MetricNature.STRUCTURAL_PROXY,
                definition=(
                    f"A module declaring at least {_MINIMUM_PUBLIC_SYMBOLS} public top-level "
                    f"names, imported directly by non-test modules in at least "
                    f"{_MINIMUM_DEPENDANT_PACKAGES} packages other than its own, and sitting "
                    f"under at least {_MINIMUM_AFFECTED_MODULES} modules in the reverse "
                    "resolved import-and-call impact graph."
                ),
                limitations=(
                    "Counting names and dependants cannot tell whether they belong together. "
                    "A cohesive module with a wide but coherent surface, a facade that "
                    "deliberately gathers a subsystem behind one import, generated code, and "
                    "a module already mid-split all count the same. Splitting has its own "
                    "cost, and this is not a recommendation to split: read what the module "
                    "holds, and which of its concerns change for different reasons, first."
                ),
            )
        )
    return signals


def _dependant_packages(
    node: AtlasNode,
    profile: MetricProfile,
    nodes: dict[str, AtlasNode],
) -> set[str]:
    """The packages, other than this module's own, that import it directly."""

    packages: set[str] = set()
    for dependant_id in profile.dependency.direct_dependants:
        dependant = nodes.get(dependant_id)
        if dependant is None or dependant.node_type != NodeType.MODULE:
            continue
        if dependant.parent_id is None or dependant.parent_id == node.parent_id:
            continue
        package = nodes.get(dependant.parent_id)
        if package is not None:
            packages.add(package.qualified_name)
    return packages
