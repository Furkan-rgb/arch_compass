"""When a verdict has already been reached, and what it is keyed by.

A boundary's fingerprint says which structure was judged. It does not say whether the
*judgement* still stands, because a verdict is a function of more than the structure: the
code under it, the case it was weighed against, the policies it was weighed under, and the
model and prompt that did the weighing. Change any one of them and the same boundary
deserves a fresh answer. Leave all of them alone and asking again can only produce a
different wording of the same conclusion — or, worse, a different conclusion, which is the
failure this exists to make impossible (docs/plans/company-readiness.md §2).

So the key is the whole question, not the subject of it — the boundary's **inputs
identity**, and the delta rule is stated directly in terms of it: a boundary whose inputs
identity is what it was in the branch's previous revision carries, verdict and standing and
silence together, with no model call and no question. Every component is content derived —
hashes, a revision number, a model identity, a prompt identity — and all of them are known
before the model is called, which is what makes the lookup free and unconditional. There is
no partial key and therefore no case where the cache has to be skipped because something was
not determined yet.

Two terms are worth explaining, because the reasoning behind them has changed.

**The content fingerprint** is new, and it closes a gap the earlier key had. A shape
fingerprint is participant names and a pattern, so rewriting a class body without renaming
anything left the key identical and carried the old verdict for ever. The advisor would have
gone on reporting a judgement about code that no longer existed, and nothing in the record
would have said so. Content is therefore an input; shape stays identity.

**`case_id` has left the key, and the case revision has stayed.** The id was load-bearing
only because every visit to a repository used to mint a fresh case: two runs a week apart
were two `case_id`s, so without it in the key the second would have carried verdicts reached
under a case the reader had since replaced. Continuity removed that — a branch has one living
case, iterated through answers — and a random id in the key then had one remaining effect,
which was to make a re-run miss on everything for no reason anybody could name. What the
verdict actually rests on is what the case *says*, so that is what is hashed, with the
revision beside it: answering a clarifying question appends a revision and moves the content,
so a second pass misses on every boundary and re-judges the lot — which is exactly what the
second pass is for. It also means a deliberate "start clean" is a different case fingerprint
and gets its own judgements, rather than silently inheriting the conversation it was asked to
leave behind.

What is deliberately *not* in the key: `repo_id`, `branch_id`, the atlas version, the review
that produced the verdict. The first three are about where the structure was seen, and the
same structure, under the same code and the same question, has the same answer wherever it
was found — that is what makes a cached verdict useful to CI, which checks out somewhere new
every time, and what will let a branch read through to its base. The last is provenance,
recorded on the row and reported to the reader, never consulted to decide whether the row
applies.

The key prefix moved from `vc` to `vc2` when the shape of the key changed. Old rows are not
migrated and not deleted: they simply stop being addressable, which is the cheapest honest
outcome — a stale row that can never be looked up cannot serve a wrong verdict, and the
first run after the change pays for its judgements exactly as a first run always does.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import Field

from archcompass.domain.base import DomainModel, canonical_json, stable_id, utc_now
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import CandidateVerdict


def policy_corpus_fingerprint(policies: Iterable[PolicyDocument]) -> str:
    """Identify the corpus a judgement was made under, by content rather than by count.

    Sorted by policy id, so the answer is a property of the set and not of the order it
    arrived in — a caller that has not sorted its policies yet still computes the same
    corpus as one that has. What is hashed is each policy's `content_hash`: editing the
    wording of one policy is a different corpus, because it is a different thing to have
    been judged under, and adding or removing one is a different corpus for the same
    reason.
    """

    return stable_id(
        "corpus",
        *[policy.content_hash for policy in sorted(policies, key=lambda policy: policy.id)],
    )


#: What a case says that no verdict turns on. `case_id` is a random identifier, the two
#: timestamps and `revision` are bookkeeping, and `repository` names where a checkout happens
#: to sit — the same argument that keeps `repo_id` out of the key, since CI clones somewhere
#: new every run and a verdict about a structure does not depend on the folder holding it.
_CASE_FIELDS_THAT_ARE_NOT_WHAT_THE_CASE_SAYS = frozenset(
    {"case_id", "created_at", "updated_at", "revision", "repository"}
)


def case_fingerprint(case: ArchitectureCase) -> str:
    """Identify a case by what it states, rather than by which case object it is.

    Everything the judgement stage is shown, minus the fields that are about the record
    rather than about the architecture. Canonical JSON so key order cannot make one case two.
    """

    stated = {
        field: value
        for field, value in case.model_dump(mode="json").items()
        if field not in _CASE_FIELDS_THAT_ARE_NOT_WHAT_THE_CASE_SAYS
    }
    return stable_id("case", canonical_json(stated))


def verdict_cache_key(
    *,
    boundary: str,
    content: str,
    policy_corpus: str,
    case: str,
    case_revision: int,
    model_identity: str,
    prompt_identity: str,
) -> str:
    """One boundary's inputs identity: this structure, this code, this corpus, this case.

    `boundary` is a `boundary_fingerprint`, `content` a `content_fingerprint`, `policy_corpus`
    a `policy_corpus_fingerprint` and `case` a `case_fingerprint`. All are passed already
    computed: the corpus and the case are the same for every candidate in a run, and hashing
    either once per boundary would be work with no answer to show for it.

    The value is stored on the reviewed boundary as well as used to look a verdict up, which
    is what lets the next revision decide in one comparison whether a boundary carries — the
    delta is a question about inputs, and this is the whole of the inputs in one string.
    """

    return stable_id(
        "vc2",
        boundary,
        content,
        policy_corpus,
        case,
        str(case_revision),
        model_identity,
        prompt_identity,
    )


class CachedVerdict(DomainModel):
    """A verdict kept verbatim, and the run that first reached it.

    The verdict is stored whole rather than summarised: reuse means the reader sees the
    same words and the same policy bearings as the run that produced them, which is the
    only version of reuse that is honest to present as the same finding.
    """

    cache_key: str = Field(min_length=1)
    #: Kept beside the key although the key already covers it. The key is a hash of six
    #: things and cannot be taken apart; this column is what lets everything a boundary has
    #: ever been judged as be found — the baseline and triage work of §3 and §4 asks that
    #: question, and a cache that could only be probed one full key at a time could not
    #: answer it.
    boundary_fingerprint: str = Field(min_length=1)
    verdict: CandidateVerdict
    #: The review that first reached this verdict. Provenance for the reader, never a
    #: condition on the reuse: the verdict remains true about the structure it judged
    #: whether or not the run that produced it is still stored.
    review_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
