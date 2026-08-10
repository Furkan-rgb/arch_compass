"""Ollama's hosted models: the same API as a local server, behind a key.

A second descriptor rather than a mode on the first, because the two answer the same
question differently. "Ollama" today means the server on this machine, and a visitor
without one sees nothing from it — correctly, since there is nothing there. The cloud is
reachable from anywhere a key is, so it is offered by default and listed first, and the
local descriptor goes on appearing exactly when a local server does.

Nothing about the request differs, which is why nothing about it is written here: the
transport, its retries and its error mapping are `ollama`'s, and this module contributes an
endpoint, a credential and the list of models the cloud is asked for.
"""

from __future__ import annotations

from typing import Final

from ollama import Client, ResponseError

from archcompass.adapters.models.ollama import (
    PROBE_TIMEOUT_SECONDS,
    REQUEST_FAILURES,
    OllamaChatTransport,
    client_for,
    probe_detail,
    thinking_modes_for,
)
from archcompass.adapters.models.structured import StructuredReasoningProvider
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.domain.model_catalog import AvailableModel, ProbeResult
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor

PROVIDER_NAME: Final = "ollama-cloud"

# ─────────────────────────────────────────────────────────────────────────────────────────
# The hosted models this advisor offers, most preferred first. Edit this list to change what
# the model chooser puts in front of a reader; nothing else in this file needs touching.
#
# Authored for the reason the Google list is: which model a review runs against decides what
# it costs, how long it takes and how good the judgement is. There is the further reason the
# local list gives — Ollama reports nothing that separates a model worth judging with from an
# embedding model — and here it bites harder, because a hosted catalog is the vendor's to
# grow without asking.
#
# One name to begin with. `gpt-oss:20b` is the small open-weights reasoning model this cloud
# serves, it thinks by default, and it is the one that has been tried. A second cloud model
# is a line here and a probe run.
# ─────────────────────────────────────────────────────────────────────────────────────────
OFFERED_MODELS: Final[tuple[str, ...]] = ("gpt-oss:20b",)

#: Where the hosted models are. Ollama's own client speaks to this host with exactly the
#: protocol it speaks to a local server with, which is what makes the transport shared.
CLOUD_BASE_URL: Final = "https://ollama.com"

#: A rejected key is not a fact about the model that happened to be asked for. These two
#: statuses end the probe rather than narrowing its list, so the reader is told to fix the
#: credential instead of being told the cloud serves none of the models it plainly serves.
_AUTH_STATUS_CODES: Final = frozenset({401, 403})


def _offered(client: Client, model: str) -> AvailableModel:
    """One model the cloud was asked for, as the chooser will render it.

    `/api/show` is the request: it authenticates, it says whether this key reaches this exact
    model, and it reports the `capabilities` that decide the thinking modes — the same list
    the local probe reads, so the modes stay the server's answer rather than this file's.
    """

    shown = client.show(model)
    return AvailableModel(
        name=model,
        # As on a local server, Ollama offers no display name and the size is the most useful
        # thing it knows that the tag does not already say.
        label=(shown.details.parameter_size or "") if shown.details else "",
        thinking_modes=thinking_modes_for(shown.capabilities),
    )


def probe_ollama_cloud(defaults: ProviderDefaults) -> ProbeResult:
    """Whether the key works and which of the offered models it reaches.

    Never raises, for the reason `probe_ollama` does not: unavailability is the answer to the
    question, and a probe that raised would take the listing of every other provider with it.

    One `/api/show` per offered model rather than one `/api/tags` for all of them. The
    listing endpoint is what a local server is asked, because it reports what has been
    pulled; a hosted catalog has no such notion, and asking each name directly answers the
    question this probe actually has — does this key reach *this* model — for every catalog
    the cloud might grow. It costs one request per name in this file, which is the same
    budget the local probe already spends on capabilities.

    Deliberately without `_with_retry`, again as the local probe is: a dropdown is waiting.
    """

    base_url = defaults.resolved_base_url() or CLOUD_BASE_URL
    try:
        client = client_for(
            base_url=base_url,
            timeout=PROBE_TIMEOUT_SECONDS,
            api_key_env=defaults.api_key_env,
            provider=PROVIDER_NAME,
        )
    except ConfigurationError as error:
        return ProbeResult(available=False, detail=str(error))
    found: list[AvailableModel] = []
    for name in OFFERED_MODELS:
        try:
            found.append(_offered(client, name))
        except ResponseError as error:
            if error.status_code in _AUTH_STATUS_CODES:
                return ProbeResult(available=False, detail=probe_detail(base_url, error))
            # Any other answer is about this model — a 404 for a name this cloud has
            # retired or never served — and costs it its row, not the provider's.
            continue
        except REQUEST_FAILURES as error:
            # No answer at all: the host is unreachable or the request never completed, which
            # is a fact about the provider rather than about one name.
            return ProbeResult(available=False, detail=probe_detail(base_url, error))
    if not found:
        # The key works and the requests arrived — this cloud simply serves none of the
        # models this advisor offers, which has its own cure: change the list at the top of
        # this file to a name it does serve.
        return ProbeResult(
            available=False,
            detail=(
                f"{base_url} answered but serves none of {', '.join(OFFERED_MODELS)}"
            ),
        )
    return ProbeResult(available=True, models=found)


class OllamaCloudReasoningProvider(StructuredReasoningProvider):
    def __init__(self, config: ReasoningModelConfig) -> None:
        super().__init__(config, OllamaChatTransport(config))


#: How this build reaches Ollama's hosted models, stated once and read by the composition
#: root.
#:
#: No `base_url_env`. The local descriptor has one because the machine holding the models is
#: the thing a deployment varies; there is one ollama.com.
DESCRIPTOR: Final = ProviderDescriptor(
    name=PROVIDER_NAME,
    build=OllamaCloudReasoningProvider,
    probe=probe_ollama_cloud,
    defaults=ProviderDefaults(
        base_url=CLOUD_BASE_URL,
        api_key_env="OLLAMA_API_KEY",
        # The variable the vendor's own client and CLI already read, so a machine signed in
        # to ollama.com needs nothing new set for this to work.
        #
        # `gpt-oss:20b` publishes a 131072-token context window (ollama.com/library/gpt-oss),
        # which is what the generic default already assumes; it is stated rather than
        # inherited so that a second model with a different window is a visible decision. The
        # output budgets stay the shared ones for the reason they are shared: they size a
        # stage's answer, not the model's ceiling, and the catalog clamps them downward to
        # whatever a probe reports.
        context_window_tokens=131072,
        # A fleet, not a GPU. The local descriptor's one-at-a-time default exists because a
        # local server runs one model on one card, where parallel judgements queue behind
        # each other and time out rather than finish sooner; hosted requests are served side
        # by side. Four rather than as many as the review has boundaries, because a hosted
        # account meters requests and a burst of forty meets the limit instead of the answers.
        concurrent_requests=4,
    ),
)
