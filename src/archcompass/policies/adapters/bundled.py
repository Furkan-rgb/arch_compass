"""The shipped corpus, read from disk without opening a workspace.

`DataclassPolicyCorpus` is how a running workspace gets its policies, and it needs a
`PolicyService`, which needs a database, which needs a workspace. The tooling around the
prebuilt policy index needs none of that and cannot have it: the builder runs from a script
and the checker runs in CI, where there is no workspace to open and nothing to open it for.

So this reads the bundled Markdown directly. It is in `adapters/` because that is what it
does — name a directory and parse the files in it — and it returns the same domain policies
the corpus would, through the same conversion, so the two cannot describe the shipped
policies differently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from archcompass.domain import Policy
from archcompass.policies.adapters.markdown import load_policy_sources
from archcompass.policies.corpus import as_policy

#: The corpus ArchCompass ships. Also re-exported from `bootstrap`, which is where the rest
#: of the project already asks for it.
BUNDLED_POLICY_SOURCE: Final = Path(__file__).resolve().parents[1] / "general"


def bundled_corpus() -> tuple[Policy, ...]:
    """The shipped policies, ordered by id.

    The same documents a workspace that added nothing of its own would judge against.
    Ordered for the reason the corpus is ordered: a fingerprint over the result, and an index
    built from it, have to be the same answer twice.
    """

    return tuple(
        sorted(
            (as_policy(item) for item in load_policy_sources([BUNDLED_POLICY_SOURCE])),
            key=lambda policy: policy.id,
        )
    )
