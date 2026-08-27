"""What one pass over a review may reach for, assembled per snapshot.

Three sources, one list. The atlas answers resolved-graph questions no search over text can
— what implements this, what reaches it, what it reaches for. The filesystem answers what
the code actually does, at the revision the analysis was made from. The corpus answers with
a principle the deterministic retrieval did not think to send.

The policy tool is the one with a rule attached. A verdict may only cite a policy that was
actually put in front of it, so every policy this returns joins the set the citation check
runs against — and `available` is how that set leaves here. Validating against the corpus
instead would let a judgement cite a principle nobody showed it.

Two callers, one set of bounds. A judgement assembles this per candidate, and a reader's
conversation assembles it per review — the same repository, the same revision, the same
four read-only filesystem tools and the same refusal to offer a write. That is the point of
its being one module: a second toolbox for the second caller would be a second set of
bounds to keep in step, and the one that drifted would be the one nobody was judging with.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from deepagents import FilesystemMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.tools import BaseTool, StructuredTool

from archcompass.domain import Policy, RepositoryAtlas, RepositoryRef
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.reviewed_backend import ReviewedRevisionBackend
from archcompass.reasoning.ports import InvestigatorSource, SourceInvestigator

#: How many policies one search returns. Three, because the judgement already holds the
#: deterministic set and this is for the principle that set missed — a search that answered
#: with ten would be a second retrieval, and a worse one.
MAX_SEARCHED_POLICIES = 3

#: The filesystem tools a judgement is offered. `write_file`, `edit_file`, `delete` and
#: `execute` are not on this list, which is how they are kept from the model: the middleware
#: takes an allowlist, so they are never built rather than built and refused.
READ_ONLY_FILESYSTEM = ("ls", "read_file", "glob", "grep")

#: The atlas relations a judgement may ask for. `known_callers` and `related_tests` are not
#: among them; see `analysis.investigation`.
ATLAS_TOOLS = ("search_code", "describe_code", "related_code")

#: Where the filesystem tools are rooted, said once instead of guessed at once per candidate.
#:
#: This is the vendor's own slot for tool-usage prose — `FilesystemMiddleware(system_prompt=)`
#: — and not the judgement contract, which is about what to decide rather than about where
#: the files are. Nothing here tells a judgement what to conclude.
#:
#: It is here because the alternative was measured. The vendor's tool descriptions promise
#: "absolute paths", so a model with no root in front of it invents one, and every one of
#: them invented `/workspace/`. Rooting what the tools hand back cured the repeats — a path
#: it was given reads back — but not the opening guess, which comes before it has been given
#: anything: 5 of 37 lookups on `speech-vendor` were still a first read into a directory that
#: does not exist. A sentence costs less than the lookup it saves.
FILESYSTEM_ROOT_NOTE = (
    "The filesystem tools read the repository under review, at the revision under review. "
    "Its root is `/`, so `/adapters.py` is a file at the top of the repository. There is no "
    "enclosing directory above it and no checkout path in front of it."
)


@dataclass
class OfferedTools:
    """Everything one pass may reach for, and what it was allowed to cite."""

    tools: tuple[BaseTool, ...] = ()
    #: Typed loosely on purpose: `FilesystemMiddleware` parameterises `AgentMiddleware` over
    #: its own state, and pinning the element type here would refuse the one middleware this
    #: field exists to carry.
    middleware: tuple[AgentMiddleware[Any, Any], ...] = ()
    #: Policies the pass searched out for itself, first-seen order, deduplicated.
    searched: list[Policy] = field(default_factory=list["Policy"])
    withheld: str = ""
    #: The atlas investigator these tools were built over, for a caller that records through
    #: it. A judgement does not — it keeps its trace on the `ReviewedSubject` its middleware
    #: writes to — but a conversation does, and it must be the *same* investigator the atlas
    #: tools answer through or the transcript would be two transcripts of one exchange.
    #:
    #: Carried here rather than fetched beside this, which is the failure it exists to
    #: prevent: `InvestigatorSource.for_review` builds a fresh investigator on every call, so
    #: a caller asking for one separately would record into a transcript nothing answered.
    investigator: SourceInvestigator | None = None

    def available(self, initial: RetrievedPolicySet) -> RetrievedPolicySet:
        """The initial set widened by whatever the judgement went and found.

        Order is first-seen and duplicates are dropped, so two searches returning the same
        principle leave one entry and the record reads the same on every run.
        """

        seen = {policy.id for policy in initial.policies}
        extra: list[Policy] = []
        for policy in self.searched:
            if policy.id in seen:
                continue
            seen.add(policy.id)
            extra.append(policy)
        return initial.widened_by(tuple(extra))


class ReviewToolbox:
    """Builds the tools for one pass, over the snapshot that pass is about."""

    def __init__(self, investigators: InvestigatorSource, corpus: Sequence[Policy]) -> None:
        self._investigators = investigators
        self._corpus = tuple(corpus)

    def for_review(self, repository: RepositoryRef, atlas: RepositoryAtlas) -> OfferedTools:
        """The toolbox for one review's snapshot: the repository, and the atlas of it.

        Keyed on those two rather than on a `ReviewedSubject`, which is a judgement's own
        scratch record — it carries the tool trace back out and the verdict's retrieval set
        with it. A reader's conversation has neither, and asking it to build one to get a
        toolbox would be asking it to fake the thing that record exists to hold.
        """

        offered = self._investigators.for_review(repository, atlas)
        if offered.investigator is None or offered.source is None:
            # Nothing to look at. The judgement still runs; it just runs on the dossier, and
            # the sentence saying why is the caller's to report.
            return OfferedTools(withheld=offered.withheld)
        searched: list[Policy] = []
        return OfferedTools(
            tools=(*_atlas_tools(offered.investigator), policy_tool(self._corpus, searched)),
            middleware=(
                FilesystemMiddleware(
                    backend=ReviewedRevisionBackend(offered.source),
                    tools=list(READ_ONLY_FILESYSTEM),
                    system_prompt=FILESYSTEM_ROOT_NOTE,
                    # Its own context eviction is switched off: one budget owns how much a
                    # pass may carry, and it is the caller's — `deep_judge` for a judgement,
                    # `tool_loop` for a conversation.
                    tool_token_limit_before_evict=None,
                    human_message_token_limit_before_evict=None,
                ),
            ),
            searched=searched,
            investigator=offered.investigator,
        )


def _atlas_tools(investigator: SourceInvestigator) -> tuple[BaseTool, ...]:
    """The atlas toolbox as LangChain tools, described exactly as the toolbox describes them.

    The descriptions are not rewritten here. They say when *not* to call as well as what the
    call does, and a second copy of that prose would drift from the one the toolbox tests.
    """

    def bind(name: str) -> BaseTool:
        def answer(**arguments: object) -> str:
            return investigator.call(name, arguments)

        specification = next(item for item in investigator.tools if item.name == name)
        return StructuredTool.from_function(
            func=answer,
            name=specification.name,
            description=specification.description,
            args_schema=dict(specification.parameters),
        )

    offered = {item.name for item in investigator.tools}
    return tuple(bind(name) for name in ATLAS_TOOLS if name in offered)


def policy_tool(corpus: Sequence[Policy], searched: list[Policy]) -> BaseTool:
    """Search the corpus, and remember what it showed so the citation check can use it.

    Public because `prompt_inventory` builds one to read the name, the description and the
    argument schema off it. Reading them off a built tool rather than quoting them is what
    keeps the digest and the offer from being two copies of the same prose.
    """

    def search_policies(query: str) -> str:
        terms = [term for term in query.casefold().split() if len(term) > 2]
        if not terms:
            return "Name what you are looking for in a few words."
        scored = sorted(
            (
                (sum(f"{p.id} {p.title} {p.body}".casefold().count(t) for t in terms), p)
                for p in corpus
            ),
            key=lambda item: (-item[0], item[1].id),
        )
        found = [policy for hits, policy in scored if hits][:MAX_SEARCHED_POLICIES]
        if not found:
            return "No policy in the corpus is about that."
        searched.extend(found)
        # The same shape the judgement prompt lists policies in, for the same reason.
        return "\n\n".join(
            f"Policy ID: {policy.id}\n{policy.title}\n{policy.body}" for policy in found
        )

    return StructuredTool.from_function(
        func=search_policies,
        name="search_policies",
        description=(
            "Search the policy corpus for a principle bearing on a concern the policies you "
            "were given do not cover. Returns up to three, in full. You may cite a policy "
            "only if it was given to you or returned by this search."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A few words naming the concern, not a whole sentence.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )
