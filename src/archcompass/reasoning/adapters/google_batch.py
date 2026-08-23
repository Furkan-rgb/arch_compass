"""Judging a whole review in one submission to Google's Batch API.

An interactive free tier meters requests per minute, and a review of a modest repository
asks for one judgement per candidate as fast as the graph can produce them — which is how a
review that has already spent minutes indexing fails on its fourth verdict. The Batch API
meters separately, costs half, and takes the same request: the same prompt, the same JSON
schema, one submission holding every candidate.

What it costs is synchrony. A batch is promised within 24 hours and usually returns much
sooner, so this blocks on a poll rather than pretending to be interactive. That is only
tolerable because the review it belongs to no longer runs inside an HTTP request — see
`ReviewWorkflowService.start_background`.

Deliberately not LangChain. The chat integration has no batch surface, so this speaks to
`google.genai` directly and shares the prompt and the response parsing with the interactive
path rather than restating them.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from google import genai
from google.genai import types
from langchain_core.embeddings import Embeddings
from pydantic import ValidationError

from archcompass.domain import Finding
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.ports.capabilities import BatchOutcome, JudgementRequest
from archcompass.reasoning.adapters.langchain import (
    FindingOutput,
    finding_from_output,
    judgement_prompt,
)
from archcompass.reasoning.adapters.providers import google_thinking_level
from archcompass.reasoning.records import JUDGE_PROMPT_IDENTITY
from archcompass.records import ThinkingMode
from archcompass.retrying import call_with_retry

_log = logging.getLogger("archcompass.batch")

#: The key a response is correlated back to its candidate by. Positional rather than the
#: candidate id, because the id is long and the API's own examples key on a short label —
#: and the position is what the inline API preserves anyway.
_KEY: Final = "candidate-{index}"

class BatchUnavailableError(ProviderError):
    """The provider will not take a batch from this key, and never will today.

    Its own type because it is the one batch failure with an obvious remedy that is not
    "wait": judge interactively instead. The Gemini Batch API is refused outright on a key
    without billing enabled, and it answers `400 FAILED_PRECONDITION` with no detail — which
    is a useless thing to fail a review with when the interactive path was working.
    """


#: What a refusal of the whole batch facility looks like, as opposed to a refusal of this
#: particular batch. `FAILED_PRECONDITION` on submission is the documented answer for a
#: project that is not eligible; a 403 is a key that is not permitted to use it at all.
_UNAVAILABLE_STATUSES: Final = frozenset({400, 403})
_UNAVAILABLE_PHRASES: Final = (
    "failed_precondition",
    "precondition check failed",
    "billing",
    "not supported",
    "not enabled",
)

_TERMINAL_SUCCESS: Final = "JOB_STATE_SUCCEEDED"
_TERMINAL_FAILURE: Final = frozenset(
    {"JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
)


@dataclass(frozen=True, slots=True)
class BatchPolling:
    """How patiently to wait for a submitted batch.

    The first poll is quick because most small batches come back in well under a minute;
    the interval then grows so that a job which really is going to take an hour is not
    asked about two thousand times. `deadline_seconds` is a refusal rather than the API's
    promise: a review that has been waiting six hours is a review someone should be told
    about.
    """

    first_interval_seconds: float = 5.0
    multiplier: float = 1.6
    maximum_interval_seconds: float = 120.0
    deadline_seconds: float = 6 * 60 * 60


DEFAULT_POLLING: Final = BatchPolling()


def await_batch(
    client: genai.Client,
    job: Any,
    *,
    polling: BatchPolling,
    sleep: Callable[[float], None],
) -> Any:
    """Poll a submitted job until it has an answer, or until waiting stops being sensible.

    Shared by judgements and embeddings because waiting is the same problem whatever the
    job holds: a name, a state that is not yet terminal, and a growing interval so that a
    job which really will take an hour is not asked about two thousand times.
    """

    name = getattr(job, "name", None)
    if not name:
        raise ProviderError("The batch was accepted without a job name to poll.")
    waited = 0.0
    interval = polling.first_interval_seconds
    current = job
    while True:
        state = str(getattr(getattr(current, "state", None), "name", "") or "")
        if state == _TERMINAL_SUCCESS:
            return current
        if state in _TERMINAL_FAILURE:
            raise ProviderError(
                f"Batch {name} ended as {state}. "
                f"{getattr(current, 'error', '') or ''}".strip()
            )
        if waited >= polling.deadline_seconds:
            raise ProviderError(
                f"Batch {name} was still {state or 'pending'} after "
                f"{waited / 3600:.1f} hours. The work was not abandoned — the job can be "
                "collected later — but this run stopped waiting."
            )
        sleep(interval)
        waited += interval
        interval = min(interval * polling.multiplier, polling.maximum_interval_seconds)
        current = call_with_retry(
            lambda: client.batches.get(name=name),
            subject=f"Reading batch {name}",
        )


class GoogleBatchJudge:
    """Every candidate in one submission, correlated back by request key."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        thinking: ThinkingMode = None,
        prompt_identity: str = JUDGE_PROMPT_IDENTITY,
        polling: BatchPolling = DEFAULT_POLLING,
        sleep: Callable[[float], None] = time.sleep,
        client: genai.Client | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model
        # Carried because this path builds its own request rather than going through
        # LangChain, and a batched judgement is not allowed to be a different judgement: a
        # review submitted as a batch must be thinking as hard as one judged interactively.
        self._thinking = google_thinking_level(thinking)
        self._prompt_identity = prompt_identity
        self._polling = polling
        self._sleep = sleep

    def judge_all(
        self,
        requests: Sequence[JudgementRequest],
        *,
        model_identity: str,
        observe: Callable[[BatchOutcome], None] | None = None,
    ) -> tuple[Finding, ...]:
        if not requests:
            return ()

        # `_submit` is the only thing that can answer whether this project may batch at all,
        # and it answers by raising. So nothing is told a batch is queued until the line
        # after it returns — a review that announced one on the strength of being routed
        # here kept announcing it through the whole interactive fallback of a refusal.
        job = self._submit(requests)
        if observe is not None:
            observe("queued")
        _log.info(
            "submitted %d judgements as batch %s", len(requests), getattr(job, "name", "?")
        )
        finished = await_batch(
            self._client, job, polling=self._polling, sleep=self._sleep
        )
        responses = self._responses(finished, expected=len(requests))
        return tuple(
            self._finding(responses[index], requests[index], model_identity)
            for index in range(len(requests))
        )

    # ── submission ────────────────────────────────────────────────────────────────────

    def _submit(self, requests: Sequence[JudgementRequest]) -> Any:
        # The response schema is `FindingOutput`'s own, so a batched judgement is held to
        # exactly the shape the interactive path validates against.
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FindingOutput,
            thinking_config=(
                None
                if self._thinking is None
                else types.ThinkingConfig(
                    # Spelled into the SDK's own enum rather than left as the word. The
                    # client coerces either way; naming the enum is what makes a level this
                    # SDK stops offering a type error here instead of a rejected batch.
                    thinking_level=types.ThinkingLevel(self._thinking.upper())
                )
            ),
        )
        inline = [
            types.InlinedRequest(
                model=self._model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=judgement_prompt(
                                    item.candidate, item.case, item.policies
                                )
                            )
                        ],
                    )
                ],
                config=config,
                # The key that correlates a response back to the candidate that asked.
                metadata={"key": _KEY.format(index=index)},
            )
            for index, item in enumerate(requests)
        ]
        try:
            return call_with_retry(
                lambda: self._client.batches.create(
                    model=self._model,
                    src=inline,
                    config=types.CreateBatchJobConfig(display_name="archcompass-judgements"),
                ),
                subject=f"Submitting {len(requests)} judgements as a batch",
            )
        except Exception as error:
            raise _submission_refusal(error, self._model) from error

    # ── collection ────────────────────────────────────────────────────────────────────

    def _responses(self, job: Any, *, expected: int) -> list[Any]:
        destination = getattr(job, "dest", None)
        inlined = getattr(destination, "inlined_responses", None)
        if inlined is None:
            raise ProviderError(
                f"Batch {getattr(job, 'name', '?')} succeeded without inline responses. "
                "A file destination is only produced for file-sourced batches, and this "
                "one was submitted inline."
            )
        responses = list(inlined)
        if len(responses) != expected:
            raise ProviderError(
                f"The batch answered {len(responses)} of {expected} judgements. A partial "
                "batch is not composed into a review, because a missing verdict would read "
                "as a cleared one."
            )
        return responses

    def _finding(
        self,
        response: Any,
        request: JudgementRequest,
        model_identity: str,
    ) -> Finding:
        error = getattr(response, "error", None)
        if error:
            raise ProviderError(
                f"The batch refused one judgement: {error}. The review is not composed "
                "from a partial batch."
            )
        text = _text_of(response)
        try:
            output = FindingOutput.model_validate_json(text)
        except ValidationError as invalid:
            preview = " ".join(text.split())[:240]
            raise ModelOutputValidationError(
                f"Batch model {model_identity} returned output that did not match the "
                f"required JSON schema for a review finding. The parser reported: "
                f"{' '.join(str(invalid).split())[:400]} Response started with: {preview!r}."
            ) from invalid
        return finding_from_output(
            output,
            request.candidate,
            request.policies,
            model_identity=model_identity,
            prompt_identity=self._prompt_identity,
        )


def _submission_refusal(error: Exception, model: str) -> Exception:
    """Turn a bare refusal into something that says what to do about it.

    `400 FAILED_PRECONDITION. {'error': {'message': 'Precondition check failed.'}}` is all
    the API says, and on its own it fails a review with nothing a reader can act on.
    """

    if isinstance(error, BatchUnavailableError):
        return error
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    text = str(error).lower()
    refused = (isinstance(status, int) and status in _UNAVAILABLE_STATUSES) and any(
        phrase in text for phrase in _UNAVAILABLE_PHRASES
    )
    if not refused:
        return error
    return BatchUnavailableError(
        f"The Batch API refused this key for {model}. Batch jobs need billing enabled on "
        "the Google Cloud project behind the key — a free-tier key is turned away with "
        "'FAILED_PRECONDITION' and no further detail. Judging will continue one request at "
        "a time instead, which is metered per minute; set ARCHCOMPASS_GOOGLE_BATCH=0 to "
        f"stop trying. The provider said: {error}"
    )


def _text_of(response: Any) -> str:
    """The one text part of a batched `GenerateContentResponse`.

    Read defensively: the batch destination hands back the same response shape as an
    interactive call, but wrapped, and a `response` attribute may or may not be the layer
    holding the candidates depending on how the job was submitted.
    """

    inner = getattr(response, "response", None) or response
    text = getattr(inner, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    candidates = getattr(inner, "candidates", None) or ()
    for candidate in candidates:
        parts = getattr(getattr(candidate, "content", None), "parts", None) or ()
        joined = "".join(
            part.text for part in parts if isinstance(getattr(part, "text", None), str)
        )
        if joined.strip():
            return joined
    raise ModelOutputValidationError(
        "A batched judgement came back with no text to parse: "
        f"{json.dumps(str(response)[:200])}"
    )


class GoogleBatchEmbeddings:
    """The whole policy corpus embedded in one submission.

    Indexing is the other place a hosted free tier refuses: the corpus is 486 chunks and the
    free tier allows a hundred embedded texts a minute, so a cold workspace spends five
    minutes mostly waiting before the first verdict is even asked for. The embeddings batch
    is metered separately and costs half, and nobody is waiting on an index being built.

    Only documents. A search embeds one text to answer a retrieval that is happening now, and
    a job promised within a day is not an answer to that — `embed_query` stays interactive
    whatever the quota says.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        polling: BatchPolling = DEFAULT_POLLING,
        sleep: Callable[[float], None] = time.sleep,
        client: genai.Client | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model
        self._dimensions = dimensions
        self._polling = polling
        self._sleep = sleep

    def embed_documents_batched(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        config = types.EmbedContentConfig(
            output_dimensionality=self._dimensions,
            task_type="RETRIEVAL_DOCUMENT",
        )
        # One batch holding every chunk, rather than one batch per chunk: the source takes
        # a single `EmbedContentBatch` whose `contents` is the whole submission.
        source = types.EmbeddingsBatchJobSource(
            inlined_requests=types.EmbedContentBatch(
                contents=[
                    types.Content(parts=[types.Part(text=text)], role="user")
                    for text in texts
                ],
                config=config,
            )
        )
        try:
            job = call_with_retry(
                lambda: self._client.batches.create_embeddings(
                    model=self._model,
                    src=source,
                    config=types.CreateEmbeddingsBatchJobConfig(
                        display_name="archcompass-policy-corpus"
                    ),
                ),
                subject=f"Submitting {len(texts)} policy chunks as an embedding batch",
            )
        except Exception as error:
            raise _submission_refusal(error, self._model) from error
        _log.info(
            "submitted %d policy chunks as batch %s", len(texts), getattr(job, "name", "?")
        )
        finished = await_batch(
            self._client, job, polling=self._polling, sleep=self._sleep
        )
        return self._vectors(finished, expected=len(texts))

    def _vectors(self, job: Any, *, expected: int) -> list[list[float]]:
        destination = getattr(job, "dest", None)
        answers = getattr(destination, "inlined_embed_content_responses", None)
        if answers is None:
            raise ProviderError(
                f"Embedding batch {getattr(job, 'name', '?')} succeeded without inline "
                "responses, and this one was submitted inline."
            )
        vectors: list[list[float]] = []
        for answer in answers:
            error = getattr(answer, "error", None)
            if error:
                raise ProviderError(f"The embedding batch refused one chunk: {error}")
            embedding = getattr(getattr(answer, "response", None), "embedding", None)
            values = getattr(embedding, "values", None)
            if not values:
                raise ProviderError(
                    "The embedding batch answered a chunk with no vector, and a chunk "
                    "without one is a policy that cannot be retrieved."
                )
            vectors.append([float(value) for value in values])
        if len(vectors) != expected:
            # A short batch would silently index part of the corpus, and a policy missing
            # from the index is a policy that never bears on a judgement.
            raise ProviderError(
                f"The embedding batch answered {len(vectors)} of {expected} chunks."
            )
        return vectors


class GoogleEmbeddings(Embeddings):
    """The interactive embeddings, with a batch behind them for bulk indexing.

    It is a LangChain `Embeddings` because everything that has to answer now still goes
    through one, and it delegates rather than inherits the Google implementation so that
    interactive behaviour is exactly what it was. The extra method is for the single caller
    that is building an index and has nobody waiting on it.
    """

    def __init__(
        self,
        interactive: Embeddings,
        batched: GoogleBatchEmbeddings,
    ) -> None:
        self._interactive = interactive
        self._batched = batched

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._interactive.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._interactive.embed_query(text)

    def supports_batch(self) -> bool:
        return True

    def embed_documents_batched(self, texts: Sequence[str]) -> list[list[float]]:
        return self._batched.embed_documents_batched(texts)
