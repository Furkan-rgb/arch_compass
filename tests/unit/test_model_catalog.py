"""Resolving what this workspace reasons with, without asking a provider anything."""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.application.model_catalog import ModelCatalogService
from archcompass.configuration import (
    AppConfig,
    ReasoningModelConfig,
    load_config,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.domain.model_catalog import (
    AvailableModel,
    ProbeResult,
    ReasoningModelSelection,
)

_OLLAMA = """
models:
  reasoning:
    provider: ollama
    model: gemma4:26b
    base_url: http://127.0.0.1:11434
    timeout_seconds: 360
    context_window_tokens: 131072
    max_output_tokens: 16384
"""

_GOOGLE = """
models:
  reasoning:
    provider: google
    model: gemini-3.6-flash
    api_key_env: GOOGLE_API_KEY
    timeout_seconds: 360
    context_window_tokens: 131072
    max_output_tokens: 32768
    thinking: true
"""


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


def _workspace(tmp_path: Path, **files: str) -> Path:
    directory = tmp_path / "config"
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name.replace("__", ".")).write_text(text, encoding="utf-8")
    return tmp_path


def _probe(**offered: list[AvailableModel]) -> object:
    def probe(config: ReasoningModelConfig) -> ProbeResult:
        models = offered.get(config.provider)
        if models is None:
            return ProbeResult(available=False, detail=f"{config.provider} is not answering")
        return ProbeResult(available=True, models=models)

    return probe


def _service(
    workspace: Path,
    *,
    selections: _Selections | None = None,
    probe: object | None = None,
    configured: AppConfig | None = None,
    pinned: bool = False,
    explicit: Path | None = None,
) -> ModelCatalogService:
    return ModelCatalogService(
        workspace=workspace,
        explicit_config=explicit,
        pinned=pinned,
        selections=selections or _Selections(),  # pyright: ignore[reportArgumentType]
        probe=probe or _probe(),  # pyright: ignore[reportArgumentType]
        configured=configured,
    )


def test_a_workspace_with_two_profiles_and_no_choice_reasons_with_nothing(
    tmp_path: Path,
) -> None:
    """The case that used to refuse to start, and the case the chooser exists for.

    Reported as an absence rather than raised: everything a review does not need a model
    for still works, and the one thing that does can ask for one where it is needed.
    """

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA, models__google__yaml=_GOOGLE)
    service = _service(workspace)

    assert service.current() is None
    status = service.status()
    assert status.selection is None
    assert (status.provider, status.model) == ("", "")
    assert not status.from_configuration


def test_a_stored_choice_wins_over_the_file_a_workspace_would_otherwise_use(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA, models__google__yaml=_GOOGLE)
    selections = _Selections()
    service = _service(workspace, selections=selections)

    service.select("models.google.yaml", "gemini-3.6-pro")

    resolved = service.current()
    assert resolved is not None
    assert (resolved.provider, resolved.model) == ("google", "gemini-3.6-pro")
    # Everything the file was authored to say survives the substitution; only the name moves.
    assert resolved.thinking is True
    assert resolved.api_key_env == "GOOGLE_API_KEY"
    assert resolved.timeout_seconds == 360


def test_a_configuration_stands_in_where_nothing_has_been_chosen(tmp_path: Path) -> None:
    """A workspace holding one profile does not have to be told which one to use."""

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA)
    configured = load_config(workspace / "config" / "models.ollama.yaml")
    service = _service(workspace, configured=configured)

    status = service.status()
    assert status.from_configuration
    assert (status.provider, status.model) == ("ollama", "gemma4:26b")
    resolved = service.current()
    assert resolved is not None and resolved.model == "gemma4:26b"


def test_a_pinned_run_reports_its_configuration_and_refuses_to_be_changed(
    tmp_path: Path,
) -> None:
    """`--models-config` says which provider this run costs money against.

    A stored selection overriding it would make the flag mean nothing — `make web-google`
    would run whichever model was last clicked.
    """

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA, models__google__yaml=_GOOGLE)
    configured = load_config(workspace / "config" / "models.google.yaml")
    selections = _Selections()
    selections.set(
        ReasoningModelSelection(
            profile_id="models.ollama.yaml", provider="ollama", model="gemma4:26b"
        )
    )
    service = _service(workspace, selections=selections, configured=configured, pinned=True)

    status = service.status()
    assert status.pinned
    assert (status.provider, status.model) == ("google", "gemini-3.6-flash")
    resolved = service.current()
    assert resolved is not None and resolved.provider == "google"
    with pytest.raises(ConfigurationError, match="not this workspace's to choose"):
        service.select("models.ollama.yaml", "gemma4:26b")


def test_a_choice_naming_a_configuration_that_has_gone_says_so(tmp_path: Path) -> None:
    """Distinct from having chosen nothing, because the cure is different: a file moved."""

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA)
    selections = _Selections()
    selections.set(
        ReasoningModelSelection(
            profile_id="models.deleted.yaml", provider="google", model="gemini-3.6-flash"
        )
    )
    service = _service(workspace, selections=selections)

    status = service.status()
    assert status.unresolvable
    assert status.selection is not None
    assert service.current() is None


def test_budgets_are_clamped_down_to_the_chosen_model_and_never_up(tmp_path: Path) -> None:
    """A profile's numbers were written for the model its file names.

    Choosing a smaller model through the same profile leaves them generous, which is the
    direction that lets an oversize request through to be truncated rather than refused.
    Choosing a larger one must not raise them: they were deliberately below what the vendor
    advertises, and `max_output_tokens` is capped at 32768 by the schema anyway.
    """

    workspace = _workspace(tmp_path, models__google__yaml=_GOOGLE)
    selections = _Selections()
    service = _service(
        workspace,
        selections=selections,
        probe=_probe(
            google=[
                AvailableModel(
                    name="gemini-tiny", input_token_limit=8192, output_token_limit=2048
                ),
                AvailableModel(
                    name="gemini-huge", input_token_limit=1048576, output_token_limit=65536
                ),
            ]
        ),
    )

    service.select("models.google.yaml", "gemini-tiny")
    small = service.current()
    assert small is not None
    assert (small.context_window_tokens, small.max_output_tokens) == (8192, 2048)

    service.select("models.google.yaml", "gemini-huge")
    large = service.current()
    assert large is not None
    assert (large.context_window_tokens, large.max_output_tokens) == (131072, 32768)


def test_the_catalog_reports_an_unreachable_provider_rather_than_hiding_it(
    tmp_path: Path,
) -> None:
    """That row is the useful one: it is the only thing on screen naming a cure."""

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA, models__google__yaml=_GOOGLE)
    service = _service(
        workspace, probe=_probe(ollama=[AvailableModel(name="gemma4:26b", label="26B")])
    )

    catalog = service.catalog()

    assert {(item.provider, item.available) for item in catalog.providers} == {
        ("ollama", True),
        ("google", False),
    }
    unreachable = next(item for item in catalog.providers if item.provider == "google")
    assert unreachable.detail == "google is not answering"
    assert [item.model for item in catalog.candidates] == ["gemma4:26b"]
    assert catalog.candidates[0].is_configured_default


def test_choosing_forgets_a_failure_recorded_against_the_model_being_replaced(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, models__google__yaml=_GOOGLE)
    selections = _Selections()
    service = _service(
        workspace,
        selections=selections,
        probe=_probe(google=[AvailableModel(name="gemini-3.6-flash")]),
    )
    service.select("models.google.yaml", "gemini-3.6-flash")
    service.record_failure("quota spent")
    assert service.status().selection is not None
    assert service.status().selection.failure_detail == "quota spent"  # pyright: ignore[reportOptionalMemberAccess]

    service.select("models.google.yaml", "gemini-3.6-flash")

    assert service.status().selection.failure_detail == ""  # pyright: ignore[reportOptionalMemberAccess]


def test_a_provider_that_answers_clears_a_failure_it_has_outlived(tmp_path: Path) -> None:
    """A recorded failure describes a call, not a model. A later success supersedes it."""

    workspace = _workspace(tmp_path, models__google__yaml=_GOOGLE)
    selections = _Selections()
    service = _service(
        workspace,
        selections=selections,
        probe=_probe(google=[AvailableModel(name="gemini-3.6-flash")]),
    )
    service.select("models.google.yaml", "gemini-3.6-flash")
    service.record_failure("temporarily unavailable")

    service.catalog()

    assert service.status().selection.failure_detail == ""  # pyright: ignore[reportOptionalMemberAccess]


def test_choosing_a_model_the_probe_did_not_list_is_allowed(tmp_path: Path) -> None:
    """A listing is a snapshot, and a model can go while the chooser is open.

    Refusing here would trade a working selection for a confusing refusal, when the failure
    it guards against arrives from the run itself, named and retryable.
    """

    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA)
    service = _service(workspace, probe=_probe(ollama=[AvailableModel(name="gemma4:26b")]))

    status = service.select("models.ollama.yaml", "a-model-pulled-since")

    assert status.model == "a-model-pulled-since"


def test_a_configuration_this_workspace_does_not_hold_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, models__ollama__yaml=_OLLAMA)
    service = _service(workspace)

    with pytest.raises(ConfigurationError, match=r"models\.invented\.yaml"):
        service.select("models.invented.yaml", "gemma4:26b")
