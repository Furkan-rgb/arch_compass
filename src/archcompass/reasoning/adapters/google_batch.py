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
from pydantic import ValidationError

from archcompass.domain import Finding
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.ports.capabilities import JudgementRequest
from archcompass.reasoning.adapters.langchain import (
    FindingOutput,
    finding_from_output,
    judgement_prompt,
)
from archcompass.retrying import call_with_retry

_log = logging.getLogger("archcompass.batch")

#: The key a response is correlated back to its candidate by. Positional rather than the
#: candidate id, because the id is long and the API's own examples key on a short label —
#: and the position is what the inline API preserves anyway.
_KEY: Final = "candidate-{index}"

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


class GoogleBatchJudge:
    """Every candidate in one submission, correlated back by request key."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_identity: str = "judge:v2",
        polling: BatchPolling = DEFAULT_POLLING,
        sleep: Callable[[float], None] = time.sleep,
        client: genai.Client | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model
        self._prompt_identity = prompt_identity
        self._polling = polling
        self._sleep = sleep

    def judge_all(
        self,
        requests: Sequence[JudgementRequest],
        *,
        model_identity: str,
    ) -> tuple[Finding, ...]:
        if not requests:
            return ()

        job = self._submit(requests)
        _log.info(
            "submitted %d judgements as batch %s", len(requests), getattr(job, "name", "?")
        )
        finished = self._await(job)
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
        return call_with_retry(
            lambda: self._client.batches.create(
                model=self._model,
                src=inline,
                config=types.CreateBatchJobConfig(display_name="archcompass-judgements"),
            ),
            subject=f"Submitting {len(requests)} judgements as a batch",
        )

    # ── waiting ───────────────────────────────────────────────────────────────────────

    def _await(self, job: Any) -> Any:
        name = getattr(job, "name", None)
        if not name:
            raise ProviderError("The batch was accepted without a job name to poll.")
        waited = 0.0
        interval = self._polling.first_interval_seconds
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
            if waited >= self._polling.deadline_seconds:
                raise ProviderError(
                    f"Batch {name} was still {state or 'pending'} after "
                    f"{waited / 3600:.1f} hours. The judgements were not abandoned — the "
                    "job can be collected later — but this run stopped waiting."
                )
            self._sleep(interval)
            waited += interval
            interval = min(
                interval * self._polling.multiplier,
                self._polling.maximum_interval_seconds,
            )
            current = call_with_retry(
                lambda: self._client.batches.get(name=name),
                subject=f"Reading batch {name}",
            )

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
