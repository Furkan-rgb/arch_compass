from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from archcompass.domain._support import freeze_sequences, require_text
from archcompass.domain.candidate import Candidate
from archcompass.domain.policy import Policy
from archcompass.domain.values import Evidence


class Verdict(StrEnum):
    MATERIAL = "material"
    CLEARED = "cleared"
    HELD = "held"


@dataclass(frozen=True, slots=True)
class PolicyBearing:
    policy: Policy
    reasoning: str


@dataclass(frozen=True, slots=True)
class Finding:
    candidate: Candidate
    verdict: Verdict
    reasoning: str
    policies: tuple[PolicyBearing, ...]
    #: The candidate's evidence carried onto the finding, so a finding read on its own is
    #: still answerable. It is not a judged selection — no producer narrows it, and nothing
    #: records which excerpt a verdict rested on. Anything presenting it as the judgement's
    #: own pick is presenting the same list twice.
    evidence: tuple[Evidence, ...]
    hinge: str | None = None
    recommended_response: str | None = None
    reused_from_review_id: str | None = None
    model_identity: str = ""
    #: Which of the gateway's endpoints answered, as the response itself named it — "Google
    #: AI Studio", "Vertex" — comma-joined where more than one did, which a judgement of up
    #: to twenty-six requests can manage.
    #:
    #: The other half of the sentence `model_identity` starts. That one says which model
    #: produced the finding and cannot say which of seven endpoints ran it, and those seven
    #: are not the same silicon, the same quantisation or the same sampler. The charter's
    #: "say where it came from" was satisfied only in name on this path while a verdict could
    #: swing between revisions of an unchanged branch and the record held nothing that could
    #: distinguish a sampler from a route.
    #:
    #: Not called `provider`, which in this codebase means the one a workspace *selected* —
    #: `openrouter`, `ollama`, `fake` — and is already inside `model_identity`. Recording is
    #: also not pinning: nothing chooses a route on the strength of this, and
    #: `openrouter.request_body` says what happened the last time something did.
    #:
    #: Empty is ordinary and has to stay readable. It is what every finding stored before
    #: this field existed carries, what a local Ollama and the deterministic stand-in carry
    #: because neither has an endpoint to name, and what a judgement carries whose requests
    #: were made somewhere the record could not be seen.
    #:
    #: Deliberately not an identity, and in no key that compares one judgement to another:
    #: not in `CachingArchitectureJudge.key`, and so in nothing the finding cache reads, and
    #: in nothing the revision delta reads. Which endpoint answered is what happened to a
    #: judgement, not what the judgement was asked — and making it an identity would re-judge
    #: every candidate in the workspace the first time OpenRouter balanced its load, which is
    #: precisely the shape of the defect this field was added while fixing.
    served_by: str = ""
    prompt_identity: str = ""
    retrieval_identity: str = ""
    #: The `RecordedInvestigation` on the review that checked this finding's hinge,
    #: named by its own content hash. "" where nothing looked, which is every finding
    #: that never had a hinge to check. The transcript itself is on the review: this
    #: record is cached, carried forward and compared, and it stays small enough to be.
    investigation_identity: str = ""
    #: The finding cache's row for this judgement, as the cache handed it back. Never
    #: computed from the fields above it, and the name says so on purpose.
    #:
    #: Those fields are provenance — they say what a reader is looking at, and the revision
    #: delta compares each of them against what this process would produce now. What they are
    #: not is a recipe for "which judgement is this". Twice a second recipe was written from
    #: them — once over the corpus fingerprint, once over the model and prompt identities —
    #: and twice it drifted from the one the cache keys on, because two expressions of one
    #: value are two places to forget a term. The last time, the term forgotten was the
    #: `ArchitectureCase`: the key carries it, a hash of these stamps cannot, and thirteen
    #: pairs of rows in the workspace that found it were two genuinely different judgements
    #: under one name, three of those pairs disagreeing about the verdict.
    #:
    #: So there is no recipe here at all. `SQLiteCoreFindingCache` stamps this with the
    #: primary key of the row it read or wrote, and `record_sources` puts that same string
    #: straight back into a `WHERE cache_key = ?`. A value that is only ever carried cannot
    #: be carried differently.
    #:
    #: Empty is ordinary. It is what every finding stored before this field existed carries,
    #: what a judgement that used a tool carries because that one is never cached, and what
    #: any finding built outside the cache carries. `record_sources` skips those rather than
    #: matching on the empty string, which no row's key can equal.
    cache_key: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "policies", "evidence")
        require_text(self.reasoning, "finding reasoning")
        if self.hinge and self.recommended_response:
            raise ValueError("a finding with an uncertainty hinge cannot recommend a response")
        if self.verdict is not Verdict.MATERIAL and self.recommended_response:
            raise ValueError("only a material finding may recommend a response")
