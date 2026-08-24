"""Provider discovery and health probes, separate from LangChain inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import httpx
from ollama import Client, ResponseError

from archcompass.reasoning.ports import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.records import AvailableModel, ProbeResult

DETERMINISTIC_MODEL = "deterministic-architecture-v4"
TASK_PROMPTED_OLLAMA_MODELS: Final = frozenset({"embeddinggemma"})

#: The strings Google documents for EmbeddingGemma retrieval. The document form takes `none`
#: for the title because a chunk already opens with its policy's title, and naming it twice
#: is not the documented shape either.
EMBEDDINGGEMMA_QUERY_PROMPT: Final = "task: search result | query: {text}"
EMBEDDINGGEMMA_DOCUMENT_PROMPT: Final = "title: none | text: {text}"


def ollama_model_family(model: str) -> str:
    """`embeddinggemma:latest` and `embeddinggemma:300m` are one model with two tags."""

    return model.split(":", 1)[0]


@dataclass(frozen=True, slots=True)
class SupportedOllamaModel:
    """An Ollama model ArchCompass has deliberately approved for reasoning."""

    name: str
    label: str
    recommended: bool = False


OLLAMA_MODELS: Final = (
    SupportedOllamaModel(
        name="qwen3.8:27b",
        label="Qwen 3.8 27B",
        recommended=True,
    ),
    SupportedOllamaModel(
        name="gemma4:26b-mlx",
        label="Gemma 4 26B MLX",
    ),
    SupportedOllamaModel(
        name="gemma4:12b-mlx",
        label="Gemma 4 12B MLX",
    ),
    SupportedOllamaModel(
        name="gemma4:e4b-mlx",
        label="Gemma 4 e4B MLX",
    ),
)


def probe_deterministic(defaults: ProviderDefaults) -> ProbeResult:
    del defaults
    return ProbeResult(
        available=True,
        models=[
            AvailableModel(name=DETERMINISTIC_MODEL, label="deterministic substitute")
        ],
    )
def probe_ollama(defaults: ProviderDefaults) -> ProbeResult:
    base_url = defaults.resolved_base_url()
    if not base_url:
        return ProbeResult(
            available=False,
            detail="this provider sets no base URL",
        )

    client = Client(host=base_url, timeout=2.0)

    try:
        listed = client.list()
    except (ResponseError, httpx.HTTPError, ConnectionError, ValueError) as error:
        return ProbeResult(
            available=False,
            detail=f"{base_url}: {error}",
        )

    supported = {model.name: model for model in OLLAMA_MODELS}
    found: dict[str, AvailableModel] = {}

    for entry in listed.models:
        model_name = entry.model
        if not model_name:
            continue

        support = supported.get(model_name)
        if support is None:
            continue

        try:
            capabilities = client.show(model_name).capabilities or []
        except (ResponseError, httpx.HTTPError, ConnectionError, ValueError):
            capabilities = []

        found[model_name] = AvailableModel(
            name=model_name,
            label=support.label,
            thinking_modes=(True, False) if "thinking" in capabilities else (None,),
        )

    if not found:
        return ProbeResult(
            available=False,
            detail=f"{base_url} has none of the supported Ollama models",
        )

    return ProbeResult(
        available=True,
        models=[found[model.name] for model in OLLAMA_MODELS if model.name in found],
    )


DETERMINISTIC_DESCRIPTOR = ProviderDescriptor(
    name="fake",
    label="Deterministic",
    probe=probe_deterministic,
    defaults=ProviderDefaults(),
)
OLLAMA_DESCRIPTOR = ProviderDescriptor(
    name="ollama",
    label="Ollama",
    probe=probe_ollama,
    defaults=ProviderDefaults(
        base_url="http://127.0.0.1:11434",
        base_url_env="ARCHCOMPASS_OLLAMA_URL",
        # Narrower than the shared default, because here the number is not a budget check —
        # it is `num_ctx`, and a local runner allocates the window it is asked for before it
        # starts. A hosted API is told how long an answer may be; Ollama is told how much
        # memory to take. On a 24 GB card a 27B model at Q4 is about 16.5 GB, and asking for
        # the shared 128k window pushed roughly 5 GB of it back onto the CPU: the judgement
        # that answers in eleven seconds inside the card had not finished in five minutes
        # outside it.
        #
        # 48k is chosen from what this product actually sends, not from what a model can
        # take. A judgement prompt is the candidate plus twenty retrieved policies, and the
        # policies are most of it — which is why it barely moves with the size of the
        # repository: 19,200 tokens on the smallest bundled example, and 20,800 on the
        # largest candidate of a real 16,000-line repository. 48k leaves room for that and
        # for the 16k a thinking selection may spend answering, with a third of the window
        # still spare. Below it a thinking run would overflow, and Ollama does not refuse an
        # oversize prompt — it keeps the tail, so the first thing discarded is the contract
        # at the top and the answer comes back fluent and unrecorded. Well above it the
        # window stops fitting beside the weights.
        context_window_tokens=49152,
        # Both budgets come down with the window, because they are spent from it. A thinking
        # selection asking for the shared 32k would leave 16k for a prompt that needs 19k,
        # and the validator that forbids an output budget larger than the window would let
        # that through — it compares the two numbers, not their sum.
        max_output_tokens=8192,
        max_output_tokens_thinking=16384,
    ),
)
