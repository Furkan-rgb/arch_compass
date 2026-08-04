"""When a verdict has already been reached, and what it is keyed by.

A boundary's fingerprint says which structure was judged. It does not say whether the
*judgement* still stands, because a verdict is a function of more than the structure: the
case it was weighed against, the policies it was weighed under, and the model and prompt
that did the weighing. Change any one of them and the same boundary deserves a fresh
answer. Leave all of them alone and asking again can only produce a different wording of
the same conclusion — or, worse, a different conclusion, which is the failure this exists
to make impossible (docs/plans/company-readiness.md §2).

So the key is the whole question, not the subject of it. Every component is content
derived — a hash, an id, a revision number, a model identity, a prompt identity — and all
of them are known before the model is called, which is what makes the lookup free and
unconditional. There is no partial key and therefore no case where the cache has to be
skipped because something was not determined yet.

The case *revision* rather than the case's text is deliberate and load-bearing. Answering
a clarifying question appends a revision, so a second pass misses on every boundary and
re-judges the lot — which is exactly what the second pass is for: the movement between the
two passes is attributed to the answers, and attribution over reused verdicts would be a
claim about a judgement nobody made twice. An unchanged re-run, by contrast, pins the same
revision and hits on everything.

What is deliberately *not* in the key: `repo_id`, `branch_id`, the atlas version, the
review that produced the verdict. The first three are about where the structure was seen,
and the same structure judged under the same question has the same answer wherever it was
found — that is what makes a cached verdict useful to CI, which checks out somewhere new
every time. The last is provenance, recorded on the row and reported to the reader, never
consulted to decide whether the row applies.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import Field

from archcompass.domain.base import DomainModel, stable_id, utc_now
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


def verdict_cache_key(
    *,
    boundary: str,
    policy_corpus: str,
    case_id: str,
    case_revision: int,
    model_identity: str,
    prompt_identity: str,
) -> str:
    """The identity of one question: this boundary, under this corpus, for this case.

    `boundary` is a `boundary_fingerprint` and `policy_corpus` a `policy_corpus_fingerprint`;
    both are passed already computed because the corpus is the same for every candidate in a
    run and hashing it once per boundary would be work with no answer to show for it.
    """

    return stable_id(
        "vc",
        boundary,
        policy_corpus,
        case_id,
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
