"""Resolving what this workspace reasons with, without asking a real provider anything."""

from __future__ import annotations

import pytest

from archcompass.domain.errors import ConfigurationError
from archcompass.ports.model_catalog import (
    CONCURRENT_REQUESTS_VARIABLE,
    MAX_CONCURRENT_REQUESTS,
    ProviderDefaults,
    ProviderDescriptor,
    ReasoningModelProbe,
)
from archcompass.reasoning.model_catalog import ModelCatalogService, reasoning_config
from archcompass.reasoning.records import (
    AvailableModel,
    ProbeResult,
    ReasoningModelSelection,
)

_GOOGLE_DEFAULTS = ProviderDefaults(
    api_key_env="GOOGLE_API_KEY",
    context_window_tokens=131072,
    max_output_tokens=16384,
    max_output_tokens_thinking=32768,
)
_OLLAMA_DEFAULTS = ProviderDefaults(
    base_url="http://127.0.0.1:11434",
    base_url_env="ARCHCOMPASS_TEST_OLLAMA_URL",
)
#: A hosted provider as its descriptor states it: several judgements at once, because there
#: is a fleet behind the endpoint rather than one GPU.
_PARALLEL_DEFAULTS = ProviderDefaults(api_key_env="GOOGLE_API_KEY", concurrent_requests=4)


class _Selections:
    """The persisted row, in memory."""

    def __init__(self) -> None:
        self.stored: ReasoningModelSelection | None = None

    def get(self) -> ReasoningModelSelection | None:
        return self.stored

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection:
        self.stored = selection
        return selection

    def clear(self) -> None:
        self.stored = None

    def record_failure(self, detail: str) -> None:
        if self.stored is not None:
            self.stored = self.stored.model_copy(update={"failure_detail": detail})

    def clear_failure(self) -> None:
        if self.stored is not None:
            self.stored = self.stored.model_copy(update={"failure_detail": ""})


def _answering(*models: AvailableModel) -> ReasoningModelProbe:
    def probe(defaults: ProviderDefaults) -> ProbeResult:
        del defaults
        return ProbeResult(available=True, models=list(models))

    return probe


def _silent(detail: str) -> ReasoningModelProbe:
    def probe(defaults: ProviderDefaults) -> ProbeResult:
        del defaults
        return ProbeResult(available=False, detail=detail)

    return probe


def _descriptor(
    name: str,
    probe: ReasoningModelProbe,
    defaults: ProviderDefaults | None = None,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        name=name,
        probe=probe,
        defaults=defaults or ProviderDefaults(),
    )


def _service(
    *descriptors: ProviderDescriptor,
    selections: _Selections | None = None,
    pin: str | None = None,
) -> ModelCatalogService:
    registry = {item.name: item for item in descriptors}
    return ModelCatalogService(
        registry=registry,
        selections=selections or _Selections(),  # pyright: ignore[reportArgumentType]
        pin=(
            reasoning_config(registry[pin], "pinned-model", True)
            if pin is not None
            else None
        ),
    )


def test_a_workspace_that_has_chosen_nothing_reasons_with_nothing() -> None:
    """Reported as an absence rather than raised: everything a review does not need a model
    for still works, and the one thing that does can ask for one where it is needed."""

    service = _service(
        _descriptor("google", _answering(), _GOOGLE_DEFAULTS),
        _descriptor("ollama", _answering(), _OLLAMA_DEFAULTS),
    )

    assert service.current() is None
    status = service.status()
    assert status.selection is None
    assert (status.provider, status.model) == ("", "")


def test_a_choice_resolves_through_its_providers_own_defaults() -> None:
    """Nothing about reaching a provider is stored with the choice, so nothing can drift."""

    service = _service(_descriptor("google", _answering(), _GOOGLE_DEFAULTS))

    service.select("google", "gemini-3.6-flash", False)

    resolved = service.current()
    assert resolved is not None
    assert (resolved.provider, resolved.model) == ("google", "gemini-3.6-flash")
    assert resolved.api_key_env == "GOOGLE_API_KEY"
    assert resolved.timeout_seconds == 360
    assert resolved.thinking is False


def test_a_thinking_selection_is_given_the_larger_output_budget() -> None:
    """Thinking tokens are spent from the same allowance as the answer.

    A budget written for a response alone leaves a reasoning run truncated mid-JSON, which
    surfaces as a validation failure rather than as a wrong answer — and giving every
    selection the larger number instead would raise the ceiling for the runs that cannot
    use it, which is the direction that truncates rather than refuses.
    """

    service = _service(_descriptor("google", _answering(), _GOOGLE_DEFAULTS))

    service.select("google", "gemini-3.6-flash", False)
    without = service.current()
    service.select("google", "gemini-3.6-flash", True)
    thinking = service.current()

    assert without is not None and without.max_output_tokens == 16384
    assert thinking is not None and thinking.max_output_tokens == 32768


def test_the_same_model_chosen_both_ways_is_two_different_configurations() -> None:
    """The memo is keyed by the thinking mode too, or the second choice returns the first."""

    service = _service(_descriptor("ollama", _answering(), _OLLAMA_DEFAULTS))

    service.select("ollama", "qwen3.6:35b", True)
    assert (config := service.current()) is not None and config.thinking is True

    service.select("ollama", "qwen3.6:35b", False)
    assert (config := service.current()) is not None and config.thinking is False


def test_the_environment_may_move_a_self_hosted_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one field a deployment genuinely varies: loopback is right for the machine the
    models are pulled on and wrong for a server reaching one over a network."""

    monkeypatch.setenv("ARCHCOMPASS_TEST_OLLAMA_URL", "http://models.internal:11434")
    service = _service(_descriptor("ollama", _answering(), _OLLAMA_DEFAULTS))

    service.select("ollama", "gemma4:26b")

    resolved = service.current()
    assert resolved is not None and resolved.base_url == "http://models.internal:11434"


def test_a_providers_own_concurrency_reaches_the_resolved_configuration() -> None:
    """How many judgements may overlap is the provider's answer, not the review's.

    A hosted API answers several at once; a self-hosted one serves a single model on a
    single GPU and would only queue. So the number travels with the configuration, and a
    descriptor that says nothing means one — the sequential behaviour every run had.
    """

    hosted = _service(_descriptor("google", _answering(), _PARALLEL_DEFAULTS))
    hosted.select("google", "gemini-3.6-flash")
    local = _service(_descriptor("ollama", _answering(), _OLLAMA_DEFAULTS))
    local.select("ollama", "gemma4:26b")

    assert (config := hosted.current()) is not None and config.concurrent_requests == 4
    assert (config := local.current()) is not None and config.concurrent_requests == 1


def test_the_environment_overrides_a_providers_concurrency_in_both_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The knob an operator reaches for when a provider starts refusing parallel requests.

    Both directions, because the two things it is for are opposite: `1` puts a hosted
    provider back on the sequential path without a redeploy, and a larger number lets a
    self-hosted endpoint that is really a load balancer say so.
    """

    monkeypatch.setenv(CONCURRENT_REQUESTS_VARIABLE, "1")
    hosted = _service(_descriptor("google", _answering(), _PARALLEL_DEFAULTS))
    hosted.select("google", "gemini-3.6-flash")
    assert (config := hosted.current()) is not None and config.concurrent_requests == 1

    monkeypatch.setenv(CONCURRENT_REQUESTS_VARIABLE, "3")
    local = _service(_descriptor("ollama", _answering(), _OLLAMA_DEFAULTS))
    local.select("ollama", "gemma4:26b")
    assert (config := local.current()) is not None and config.concurrent_requests == 3


def test_an_oversized_concurrency_is_clamped_rather_than_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling is a judgement about what is worth having in flight, not a rule about
    what the operator was allowed to type, so it lands on the ceiling and runs."""

    monkeypatch.setenv(CONCURRENT_REQUESTS_VARIABLE, "500")
    service = _service(_descriptor("google", _answering(), _PARALLEL_DEFAULTS))

    service.select("google", "gemini-3.6-flash")

    assert (config := service.current()) is not None
    assert config.concurrent_requests == MAX_CONCURRENT_REQUESTS


@pytest.mark.parametrize("value", ["0", "-2", "two", "1.5"])
def test_a_concurrency_that_is_not_a_count_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Refused where it is read, naming the variable: a run that silently ignored it would
    judge sequentially while the deployment believed it had asked for four."""

    monkeypatch.setenv(CONCURRENT_REQUESTS_VARIABLE, value)
    service = _service(_descriptor("google", _answering(), _PARALLEL_DEFAULTS))
    service.select("google", "gemini-3.6-flash")

    with pytest.raises(ConfigurationError, match=CONCURRENT_REQUESTS_VARIABLE):
        service.current()


def test_a_pinned_run_reports_its_model_and_refuses_to_be_changed() -> None:
    """`--provider` and `--model` say which provider this run costs against.

    A stored selection overriding them would make the flags mean nothing — `make web-google`
    would run whichever model was last clicked.
    """

    selections = _Selections()
    selections.set(ReasoningModelSelection(provider="ollama", model="gemma4:26b"))
    service = _service(
        _descriptor("google", _answering(), _GOOGLE_DEFAULTS),
        _descriptor("ollama", _answering(), _OLLAMA_DEFAULTS),
        selections=selections,
        pin="google",
    )

    status = service.status()
    assert status.pinned
    assert (status.provider, status.model, status.thinking) == ("google", "pinned-model", True)
    resolved = service.current()
    assert resolved is not None and resolved.provider == "google"
    with pytest.raises(ConfigurationError, match="not this workspace's to choose"):
        service.select("ollama", "gemma4:26b")


def test_a_choice_naming_a_provider_this_deployment_lacks_reads_as_no_choice() -> None:
    """A hosted deployment reaches no local Ollama, and a workspace carrying that selection
    has the same thing to do about it as one that never chose: choose something reachable."""

    selections = _Selections()
    selections.set(ReasoningModelSelection(provider="ollama", model="gemma4:26b"))
    service = _service(
        _descriptor("google", _answering(), _GOOGLE_DEFAULTS), selections=selections
    )

    status = service.status()
    assert status.selection is None
    assert (status.provider, status.model) == ("", "")
    assert service.current() is None


def test_budgets_are_clamped_down_to_the_chosen_model_and_never_up() -> None:
    """A provider's numbers are written for the models it usually reaches.

    Choosing a smaller model leaves them generous, which is the direction that lets an
    oversize request through to be truncated rather than refused. Choosing a larger one must
    not raise them: they are deliberately below what the vendor advertises, and
    `max_output_tokens` is capped at 65536 by the schema anyway.
    """

    service = _service(
        _descriptor(
            "google",
            _answering(
                AvailableModel(
                    name="gemini-tiny", input_token_limit=8192, output_token_limit=2048
                ),
                AvailableModel(
                    name="gemini-huge", input_token_limit=1048576, output_token_limit=65536
                ),
            ),
            _GOOGLE_DEFAULTS,
        )
    )

    service.select("google", "gemini-tiny", True)
    small = service.current()
    assert small is not None
    assert (small.context_window_tokens, small.max_output_tokens) == (8192, 2048)

    service.select("google", "gemini-huge", True)
    large = service.current()
    assert large is not None
    assert (large.context_window_tokens, large.max_output_tokens) == (131072, 32768)


def test_google_inherits_a_gemini_sized_context_window() -> None:
    """The 131072 default in `ProviderDefaults` is sized for a self-hosted provider.

    Gemini advertises ~1M input tokens, and holding it to the generic default made every
    stage refuse requests the model would have taken comfortably. The probe-based clamp
    still pulls the number down for a smaller model, so generosity here is safe.
    """

    from archcompass.reasoning.adapters.providers import GOOGLE_DESCRIPTOR

    assert GOOGLE_DESCRIPTOR.defaults.context_window_tokens == 1_048_576

    service = _service(
        _descriptor(
            "google",
            _answering(
                AvailableModel(name="gemini-huge"),
                AvailableModel(name="gemini-small", input_token_limit=131072),
            ),
            GOOGLE_DESCRIPTOR.defaults,
        )
    )

    service.select("google", "gemini-huge", True)
    unclamped = service.current()
    assert unclamped is not None
    assert unclamped.context_window_tokens == 1_048_576

    service.select("google", "gemini-small", True)
    clamped = service.current()
    assert clamped is not None
    assert clamped.context_window_tokens == 131072


def test_the_catalog_reports_an_unreachable_provider_rather_than_hiding_it() -> None:
    """That row is the useful one: it is the only thing on screen naming a cure."""

    service = _service(
        _descriptor("ollama", _answering(AvailableModel(name="gemma4:26b", label="26B"))),
        _descriptor("google", _silent("GOOGLE_API_KEY is unset")),
    )

    catalog = service.catalog()

    assert {(item.provider, item.available) for item in catalog.providers} == {
        ("ollama", True),
        ("google", False),
    }
    unreachable = next(item for item in catalog.providers if item.provider == "google")
    assert unreachable.detail == "GOOGLE_API_KEY is unset"
    assert [item.model for item in catalog.candidates] == ["gemma4:26b"]


def test_a_model_offering_two_thinking_modes_is_listed_as_two_candidates() -> None:
    """They cost differently and answer differently, so they are two choices and not one
    with a switch beside it. A model with one mode stays one row."""

    service = _service(
        _descriptor(
            "ollama",
            _answering(
                AvailableModel(name="qwen3.6:35b", thinking_modes=(True, False)),
                AvailableModel(name="gemma4:26b", thinking_modes=(None,)),
            ),
        )
    )

    catalog = service.catalog()

    assert [(item.model, item.thinking) for item in catalog.candidates] == [
        ("qwen3.6:35b", True),
        ("qwen3.6:35b", False),
        ("gemma4:26b", None),
    ]


def test_only_the_candidate_that_was_chosen_is_marked_selected() -> None:
    """A candidate is (provider, model, thinking), so the same model in the other mode is a
    different row and must not light up beside the chosen one."""

    service = _service(
        _descriptor(
            "ollama", _answering(AvailableModel(name="qwen3.6:35b", thinking_modes=(True, False)))
        )
    )

    service.select("ollama", "qwen3.6:35b", False)

    selected = [item for item in service.catalog().candidates if item.is_selected]
    assert [(item.model, item.thinking) for item in selected] == [("qwen3.6:35b", False)]


def test_choosing_forgets_a_failure_recorded_against_the_model_being_replaced() -> None:
    selections = _Selections()
    service = _service(
        _descriptor("google", _answering(AvailableModel(name="gemini-3.6-flash"))),
        selections=selections,
    )
    service.select("google", "gemini-3.6-flash", True)
    service.record_failure("quota spent")
    assert service.status().selection is not None
    assert service.status().selection.failure_detail == "quota spent"  # pyright: ignore[reportOptionalMemberAccess]

    service.select("google", "gemini-3.6-flash", True)

    assert service.status().selection.failure_detail == ""  # pyright: ignore[reportOptionalMemberAccess]


def test_a_provider_that_answers_clears_a_failure_it_has_outlived() -> None:
    """A recorded failure describes a call, not a model. A later success supersedes it."""

    selections = _Selections()
    service = _service(
        _descriptor("google", _answering(AvailableModel(name="gemini-3.6-flash"))),
        selections=selections,
    )
    service.select("google", "gemini-3.6-flash", True)
    service.record_failure("temporarily unavailable")

    service.catalog()

    assert service.status().selection.failure_detail == ""  # pyright: ignore[reportOptionalMemberAccess]


def test_choosing_a_model_the_probe_did_not_list_is_allowed() -> None:
    """A listing is a snapshot, and a model can go while the chooser is open.

    Refusing here would trade a working selection for a confusing refusal, when the failure
    it guards against arrives from the run itself, named and retryable.
    """

    service = _service(
        _descriptor("ollama", _answering(AvailableModel(name="gemma4:26b")))
    )

    status = service.select("ollama", "a-model-pulled-since")

    assert status.model == "a-model-pulled-since"


def test_a_provider_this_workspace_cannot_reach_is_refused_by_name() -> None:
    service = _service(_descriptor("ollama", _answering()))

    with pytest.raises(ConfigurationError, match="invented"):
        service.select("invented", "gemma4:26b")
