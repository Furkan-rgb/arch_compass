from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from archcompass.adapters.models import ollama as ollama_adapters
from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.models.ollama import (
    AlternativeList,
    OllamaEmbeddingProvider,
    OllamaReasoningProvider,
    ScenarioList,
)
from archcompass.application.synthesis import build_claim_pool
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ClaimClassification,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    GlobalContext,
    ScenarioEvaluation,
)
from archcompass.domain.conversation import (
    AnswerClaim,
    AnswerStatement,
    AnswerStatementKind,
    ConversationAnswer,
)
from archcompass.domain.diagnostics import FailureDiagnosticCode
from archcompass.domain.errors import (
    ClusterPartitionError,
    ModelOutputValidationError,
    PromptBudgetExceededError,
    ProviderError,
)
from archcompass.ports.reasoning import ReasoningTask


def test_conversation_answer_repair_is_one_allowlist_constrained_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    repaired_claim = AnswerClaim(
        text="The repaired answer uses a supplied report claim.",
        classification=ClaimClassification.ADVISOR_INFERENCE,
        report_claim_ids=["claim-known"],
    )
    repaired = ConversationAnswer(
        direct_answer=AnswerStatement(
            text="Unsupported citations were removed.",
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=[repaired_claim.claim_id],
        ),
        claims=[repaired_claim],
    )
    initial_claim = AnswerClaim(
        text="The initial answer cites an unknown policy.",
        classification=ClaimClassification.POLICY_GUIDANCE,
        policy_ids=["policy-unknown"],
    )
    initial = ConversationAnswer(
        direct_answer=AnswerStatement(
            text="Initial answer",
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=[initial_claim.claim_id],
        ),
        claims=[initial_claim],
    )

    def post(url: str, **kwargs: object) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return _http_response(
            {"message": {"role": "assistant", "content": repaired.model_dump_json()}}
        )

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    result = provider.repair_conversation_answer(
        initial,
        ["Unknown policy citation"],
        {"FIND-001"},
        {"claim-known"},
        {"node-known"},
        {"policy-known"},
    )

    assert result == repaired
    assert len(calls) == 1
    payload = calls[0]["json"]
    assert isinstance(payload, dict)
    request_text = json.dumps(payload)
    assert "policy-known" in request_text
    assert "sole repair attempt" in request_text


def _embedding_config(*, dimensions: int = 3) -> EmbeddingModelConfig:
    return EmbeddingModelConfig(
        provider="ollama",
        model="embedding-test",
        base_url="http://ollama.test/",
        dimensions=dimensions,
        timeout_seconds=5,
    )


def _reasoning_config() -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="ollama",
        model="reasoning-test",
        base_url="http://ollama.test/",
        timeout_seconds=10,
    )


def _context() -> GlobalContext:
    return GlobalContext(
        case_id="case-test",
        revision=1,
        title="Provider ownership",
        problem="Provider-specific capabilities leak into orchestration.",
        desired_outcome="Keep orchestration provider-neutral.",
        goals=["Clear ownership"],
        constraints=["Local-first"],
        future_changes=["A second provider"],
        non_goals=["A universal plugin platform"],
        confirmed_facts=["One provider exists"],
        assumptions=[],
    )


def _http_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://ollama.test/api")
    if isinstance(payload, bytes):
        return httpx.Response(status_code, content=payload, request=request)
    return httpx.Response(status_code, json=payload, request=request)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    """Stub the HTTP layer beneath the real Ollama client.

    Patching `httpx.Client.request` rather than a module-level function keeps the
    library's own request building, response parsing and error mapping in the path, so
    these tests exercise the transport we actually ship.
    """

    def request(
        _self: object, _method: str, url: str, **kwargs: object
    ) -> httpx.Response:
        # Present the same (url, **kwargs) shape the stubs were written against.
        return handler(url, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(httpx.Client, "request", request)


def test_embedding_provider_sends_batch_and_validates_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _http_response({"embeddings": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]})

    _patch_transport(monkeypatch, post)
    provider = OllamaEmbeddingProvider(_embedding_config())

    vectors = provider.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert captured["url"] == "/api/embed"
    assert captured["json"] == {
        "model": "embedding-test",
        "input": ["first", "second"],
    }
    # The timeout now belongs to the client rather than the request, and is asserted
    # per task class in the timeout tests below.


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"embeddings": [[1.0, 0.0, 0.0]]}, "1 embeddings for 2 inputs"),
        (
            {"embeddings": [[1.0, 0.0], [0.0, 1.0, 0.0]]},
            "embedding 0 has 2 dimensions",
        ),
        (
            b'{"embeddings":[[NaN,0.0,0.0],[0.0,1.0,0.0]]}',
            "embedding 0 contains a non-finite value",
        ),
    ],
)
def test_embedding_provider_rejects_contract_violations(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    message: str,
) -> None:
    _patch_transport(monkeypatch, lambda *args, **kwargs: _http_response(payload))
    provider = OllamaEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match=message):
        provider.embed(["first", "second"])


def test_scenario_evaluation_repairs_closed_set_alternative_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alternatives = [
        CaseAlternative(
            id="alt-local",
            title="Keep behavior local",
            summary="Retain the current ownership.",
        ),
        CaseAlternative(
            id="alt-boundary",
            title="Introduce a focused boundary",
            summary="Move changing provider knowledge behind one owner.",
        ),
    ]
    invalid = ScenarioEvaluation(
        scenario="A second provider is required.",
        assumptions=["Provider capabilities differ."],
        alternative_results={
            "A1": "Requires coordinated changes.",
            "invented-alternative": "Was not supplied.",
        },
        conclusion="A focused boundary contains the change.",
    )
    repaired = invalid.model_copy(
        update={
            "alternative_results": {
                "A1": "Requires coordinated changes.",
                "A2": "Contains provider-specific variation.",
            }
        }
    )
    outputs = [
        json.dumps([invalid.model_dump(mode="json")]),
        json.dumps([repaired.model_dump(mode="json")]),
    ]
    requests: list[dict[str, object]] = []

    def post(url: str, **kwargs: object) -> httpx.Response:
        requests.append({"url": url, **kwargs})
        return _http_response({"message": {"role": "assistant", "content": outputs.pop(0)}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    scenarios = provider.evaluate_scenarios(_context(), alternatives, [])

    assert scenarios == [
        repaired.model_copy(
            update={
                "alternative_results": {
                    "alt-local": "Requires coordinated changes.",
                    "alt-boundary": "Contains provider-specific variation.",
                }
            }
        )
    ]
    assert len(requests) == 2
    repair_request = requests[-1]["json"]
    assert isinstance(repair_request, dict)
    assert "omits alternative IDs" in json.dumps(repair_request)
    assert "invents alternative IDs" in json.dumps(repair_request)


def test_reasoning_provider_sends_schema_and_parses_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    content = json.dumps(
        [
            {
                "title": "Provider ownership",
                "description": "Changing capability knowledge needs one owner.",
                "importance": "high",
            }
        ]
    )

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _http_response({"message": {"role": "assistant", "content": content}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    forces = provider.discover_design_forces(_context())

    assert [force.title for force in forces] == ["Provider ownership"]
    assert forces[0].force_id.startswith("force_")
    assert captured["url"] == "/api/chat"
    request = captured["json"]
    assert isinstance(request, dict)
    assert request["model"] == "reasoning-test"
    assert request["stream"] is False
    assert isinstance(request["format"], dict)
    assert "force_id" not in json.dumps(request["format"])
    assert request["options"] == {
        "num_ctx": 32768,
        "num_predict": 16384,
    }


def test_reasoning_provider_distinguishes_invalid_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(
        monkeypatch,
        lambda *args, **kwargs: _http_response({"message": {"role": "assistant", "content": "{}"}}),
    )
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ModelOutputValidationError, match="invalid structured output"):
        provider.discover_design_forces(_context())


def test_reasoning_provider_repairs_invalid_structured_output_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = [
        "{}",
        json.dumps(
            [
                {
                    "title": "Provider ownership",
                    "description": "Changing capability knowledge needs one owner.",
                    "importance": "high",
                }
            ]
        ),
    ]
    requests: list[dict[str, object]] = []

    def post(*args: object, **kwargs: object) -> httpx.Response:
        del args
        request = kwargs["json"]
        assert isinstance(request, dict)
        requests.append(request)
        return _http_response({"message": {"role": "assistant", "content": outputs.pop(0)}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    forces = provider.discover_design_forces(_context())

    assert len(forces) == 1
    assert forces[0].force_id.startswith("force_")
    assert len(requests) == 2
    repair_messages = requests[1]["messages"]
    assert isinstance(repair_messages, list)
    assert "failed validation" in repair_messages[-1]["content"]


def test_reasoning_provider_mints_unique_force_ids_for_duplicate_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = json.dumps(
        [
            {
                "title": "Provider ownership",
                "description": "Changing capability knowledge needs one owner.",
                "importance": "high",
            },
            {
                "title": "Provider ownership",
                "description": "Changing capability knowledge needs one owner.",
                "importance": "high",
            },
        ]
    )
    _patch_transport(
        monkeypatch,
        lambda *args, **kwargs: _http_response(
            {"message": {"role": "assistant", "content": content}}
        ),
    )

    forces = OllamaReasoningProvider(_reasoning_config()).discover_design_forces(_context())

    assert len({force.force_id for force in forces}) == 2


def test_clustering_uses_closed_set_handles_and_maps_domain_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forces = [
        DesignForce(
            force_id="force-owner",
            title="Provider ownership",
            description="Provider knowledge needs one owner.",
            importance="high",
        ),
        DesignForce(
            force_id="force-change",
            title="Change locality",
            description="Provider changes should stay local.",
            importance="high",
        ),
    ]
    captured: dict[str, object] = {}
    content = json.dumps(
        [
            {
                "title": "Provider boundary",
                "rationale": "Investigate ownership and change locality together.",
                "force_refs": ["F1", "F2"],
            }
        ]
    )

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _http_response({"message": {"role": "assistant", "content": content}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    clusters = provider.cluster_design_forces(_context(), forces)

    assert len(clusters) == 1
    assert clusters[0].cluster_id.startswith("cluster_")
    assert clusters[0].design_force_ids == ["force-owner", "force-change"]
    request = captured["json"]
    assert isinstance(request, dict)
    schema = request["format"]
    assert isinstance(schema, dict)
    schema_text = json.dumps(schema)
    assert "cluster_id" not in schema_text
    assert "design_force_ids" not in schema_text
    assert schema["items"]["properties"]["force_refs"]["items"]["enum"] == [
        "F1",
        "F2",
    ]
    messages = request["messages"]
    assert isinstance(messages, list)
    model_input = messages[-1]["content"]
    assert '"force_ref":"F1"' in model_input
    assert '"force_ref":"F2"' in model_input
    assert "force-owner" not in model_input
    assert "force-change" not in model_input


def test_clustering_rejects_duplicate_canonical_force_ids_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    force = DesignForce(
        force_id="force-duplicate",
        title="Provider ownership",
        description="Provider knowledge needs one owner.",
        importance="high",
    )

    def unexpected_post(*args: object, **kwargs: object) -> httpx.Response:
        del args, kwargs
        pytest.fail("Duplicate canonical force IDs must fail before an Ollama request")

    _patch_transport(monkeypatch, unexpected_post)
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ValueError, match="Design force IDs must be unique"):
        provider.cluster_design_forces(
            _context(),
            [
                force,
                force.model_copy(
                    update={
                        "title": "Change locality",
                        "description": "Provider changes should remain local.",
                    }
                ),
            ],
        )


def test_clustering_rejects_unknown_handle_after_one_correction_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forces = [
        DesignForce(
            force_id="force-owner",
            title="Provider ownership",
            description="Provider knowledge needs one owner.",
            importance="high",
        ),
        DesignForce(
            force_id="force-change",
            title="Change locality",
            description="Provider changes should stay local.",
            importance="high",
        ),
    ]
    invalid = json.dumps(
        [
            {
                "title": "Provider boundary",
                "rationale": "The model corrupted one constrained handle.",
                "force_refs": ["F1", "F9"],
            }
        ]
    )
    requests: list[dict[str, object]] = []

    def post(*args: object, **kwargs: object) -> httpx.Response:
        del args
        request = kwargs["json"]
        assert isinstance(request, dict)
        requests.append(request)
        return _http_response({"message": {"role": "assistant", "content": invalid}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ClusterPartitionError) as caught:
        provider.cluster_design_forces(_context(), forces)

    assert len(requests) == 2
    assert [item.code for item in caught.value.diagnostics] == [
        FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES,
        FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
    ]
    assert caught.value.diagnostics[0].count == 1
    assert caught.value.diagnostics[1].force_handles == ["F2"]
    assert "force-owner" not in str(caught.value)
    assert "force-change" not in str(caught.value)
    repair_messages = requests[1]["messages"]
    assert isinstance(repair_messages, list)
    assert "unrecognized force reference" in repair_messages[-1]["content"]
    assert "Missing force handles: F2" in repair_messages[-1]["content"]


def test_every_reasoning_stage_parses_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    case = ArchitectureCase(
        case_id=context.case_id,
        title=context.title,
        problem_statement=context.problem,
        desired_outcome=context.desired_outcome,
        expected_future_changes=context.future_changes,
    )
    force = DesignForce(
        force_id="force-owner",
        title="Provider ownership",
        description="Provider knowledge needs one owner.",
        importance="high",
    )
    cluster = ConcernCluster(
        cluster_id="cluster-owner",
        title="Provider ownership",
        rationale="Analyze changing provider knowledge.",
        design_force_ids=[force.force_id],
    )
    packet = FocusedAnalysisPacket(
        cluster=cluster,
        uncertainty=["No repository evidence was supplied for this unit fixture."],
    )
    analysis = ConcernAnalysis(
        cluster_id=cluster.cluster_id,
        concern=cluster.title,
        findings=[
            {
                "claim_id": "claim-inference",
                "text": "Ownership follows from the confirmed context.",
                "classification": "advisor_inference",
            }
        ],
        implications=["Keep one owner."],
    )
    alternatives = [
        CaseAlternative(
            id="alt-provider",
            title="Provider-owned",
            summary="Move discovery into the provider.",
        ),
        CaseAlternative(
            id="alt-central",
            title="Central registry",
            summary="Keep discovery in orchestration.",
        ),
    ]
    scenarios = [
        ScenarioEvaluation(
            scenario="A second provider is added.",
            assumptions=["The provider has different capabilities."],
            alternative_results={
                alternative.id: f"Evaluate {alternative.title}" for alternative in alternatives
            },
            conclusion="Provider ownership contains the change.",
        )
    ]
    model_scenarios = [
        scenario.model_copy(
            update={
                "alternative_results": {
                    f"A{ordinal}": result
                    for ordinal, result in enumerate(
                        scenario.alternative_results.values(),
                        start=1,
                    )
                }
            }
        )
        for scenario in scenarios
    ]
    deterministic = DeterministicReasoningProvider()
    pool = build_claim_pool(case=case, clusters=[cluster], analyses=[analysis])
    cluster_refs = {pool.cluster_ref_by_id[cluster.cluster_id]: cluster.title}
    proposal = deterministic.propose_recommendation(
        case,
        context,
        [force],
        [cluster],
        [analysis],
        alternatives,
        scenarios,
        [packet],
        available_claims=pool.available,
        cluster_refs=cluster_refs,
    )
    outputs = [
        json.dumps(
            [
                {
                    "title": cluster.title,
                    "rationale": cluster.rationale,
                    "force_refs": ["F1"],
                }
            ]
        ),
        json.dumps(
            [
                {
                    "cluster_id": cluster.cluster_id,
                    "plan": {
                        "iteration": 1,
                        "rationale": "Inspect the repository.",
                        "queries": [],
                    },
                }
            ]
        ),
        analysis.model_dump_json(),
        json.dumps([item.model_dump(mode="json") for item in alternatives]),
        json.dumps([item.model_dump(mode="json") for item in model_scenarios]),
        proposal.model_dump_json(),
    ]
    requests: list[str] = []

    def post(*args: object, **kwargs: object) -> httpx.Response:
        del args
        requests.append(json.dumps(kwargs.get("json")))
        return _http_response({"message": {"role": "assistant", "content": outputs.pop(0)}})

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_reasoning_config())

    formed_clusters = provider.cluster_design_forces(context, [force])
    assert len(formed_clusters) == 1
    assert formed_clusters[0].title == cluster.title
    assert formed_clusters[0].rationale == cluster.rationale
    assert formed_clusters[0].design_force_ids == [force.force_id]
    assert formed_clusters[0].cluster_id.startswith("cluster_")
    plans = provider.plan_atlas_queries(
        context,
        [force],
        [cluster],
        iteration=1,
        prior_results={cluster.cluster_id: []},
    )
    assert plans[0].cluster_id == cluster.cluster_id
    assert provider.analyze_concern_cluster(context, packet) == analysis
    assert provider.generate_alternatives(context, [analysis]) == alternatives
    assert provider.evaluate_scenarios(context, alternatives, [analysis]) == scenarios
    assert (
        provider.propose_recommendation(
            case,
            context,
            [force],
            [cluster],
            [analysis],
            alternatives,
            scenarios,
            [packet],
            available_claims=pool.available,
            cluster_refs=cluster_refs,
        )
        == proposal
    )
    assert outputs == []
    assert any("never copy claim text" in request for request in requests)
    synthesis_request = next(
        request for request in requests if "ProposedFinding" in request
    )
    synthesis_messages = json.loads(synthesis_request)["messages"]
    synthesis_input = synthesis_messages[-1]["content"]
    assert '"packets":' not in synthesis_input
    assert '"available_claims":' in synthesis_input
    assert '"concern_analyses":' in synthesis_input
    synthesis_schema = json.loads(synthesis_request)["format"]
    statement_refs = synthesis_schema["$defs"]["ProposedStatement"]["properties"]["claim_refs"]
    assert statement_refs["items"]["enum"] == sorted(item.ref for item in pool.available)
    finding_cluster = synthesis_schema["$defs"]["ProposedFinding"]["properties"]["cluster_ref"]
    assert finding_cluster["enum"] == sorted(cluster_refs)


def test_scenario_contract_requires_at_least_one_evaluation() -> None:
    with pytest.raises(ValidationError):
        ScenarioList.model_validate([])


def test_alternative_contract_requires_multiple_candidates() -> None:
    with pytest.raises(ValidationError):
        AlternativeList.model_validate([])
    with pytest.raises(ValidationError):
        AlternativeList.model_validate(
            [{"id": "alt-test", "title": "Only option", "summary": "Not a comparison"}]
        )


@pytest.mark.parametrize(
    "provider_factory",
    [
        lambda: OllamaEmbeddingProvider(_embedding_config()),
        lambda: OllamaReasoningProvider(_reasoning_config()),
    ],
)
def test_ollama_providers_wrap_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
    provider_factory: Callable[[], OllamaEmbeddingProvider | OllamaReasoningProvider],
) -> None:
    """A transient failure is retried to the cap, then surfaced as a ProviderError."""

    attempts = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("offline")

    _patch_transport(monkeypatch, post)
    monkeypatch.setattr(ollama_adapters.time, "sleep", lambda _seconds: None)
    provider = provider_factory()

    # The client substitutes its own guidance for a connect error, so the original
    # detail is gone; what must survive is the ProviderError wrapping and the retry.
    with pytest.raises(ProviderError, match=r"Ollama .* request failed: .*Ollama"):
        if isinstance(provider, OllamaEmbeddingProvider):
            provider.embed(["test"])
        else:
            provider.discover_design_forces(_context())

    assert attempts == ollama_adapters._MAX_TRANSPORT_ATTEMPTS


def test_reasoning_provider_preserves_bounded_http_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def post(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        request = httpx.Request("POST", url)
        return httpx.Response(
            400,
            json={"error": "failed to parse grammar"},
            request=request,
        )

    _patch_transport(monkeypatch, post)

    with pytest.raises(
        ProviderError,
        match=r"HTTP 400.*failed to parse grammar",
    ):
        OllamaReasoningProvider(_reasoning_config()).discover_design_forces(_context())


def _small_window_config() -> ReasoningModelConfig:
    """A window too small for any real stage prompt."""

    return ReasoningModelConfig(
        provider="ollama",
        model="test-model",
        base_url="http://ollama.test",
        timeout_seconds=30,
        context_window_tokens=1024,
        max_output_tokens=512,
    )


def test_reasoning_provider_refuses_an_oversize_prompt_before_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama truncates an oversize prompt from the front, silently losing the system
    prompt. The guard refuses instead, naming the stage and both measured sizes."""

    sent = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise AssertionError("the guard must refuse before any request is sent")

    _patch_transport(monkeypatch, post)
    provider = OllamaReasoningProvider(_small_window_config())

    with pytest.raises(PromptBudgetExceededError) as failure:
        provider.discover_design_forces(_context())

    message = str(failure.value)
    assert "discover_design_forces" in message
    assert "prompt characters" in message
    assert "schema characters" in message
    assert sent == 0


def test_prompt_guard_counts_the_response_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The schema is part of the request, so it is part of the budget.

    Under-counting would let a request through that the model then truncates, which is
    the exact silent failure the guard exists to remove.
    """

    del monkeypatch
    provider = OllamaReasoningProvider(_small_window_config())
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    provider._guard_prompt_budget(  # pyright: ignore[reportPrivateUsage]
        ReasoningTask.DISCOVER_DESIGN_FORCES,
        messages,
        {},
    )

    huge_schema = {"description": "d" * 8_000}
    with pytest.raises(PromptBudgetExceededError, match="schema characters"):
        provider._guard_prompt_budget(  # pyright: ignore[reportPrivateUsage]
            ReasoningTask.DISCOVER_DESIGN_FORCES,
            messages,
            huge_schema,
        )


def test_transport_retry_recovers_from_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("blip")
        return _http_response({"embeddings": [[0.0] * 8]})

    _patch_transport(monkeypatch, post)
    monkeypatch.setattr(ollama_adapters.time, "sleep", lambda _seconds: None)
    provider = OllamaEmbeddingProvider(
        EmbeddingModelConfig(
            provider="ollama",
            model="test-embed",
            base_url="http://ollama.test",
            dimensions=8,
            timeout_seconds=5,
        )
    )

    assert provider.embed(["one"]) == [[0.0] * 8]
    assert attempts == 2


def test_transport_retry_does_not_retry_a_terminal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 fails identically on every attempt; retrying it only wastes time."""

    attempts = 0

    def post(url: str, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        del kwargs
        return httpx.Response(
            400,
            json={"error": "bad request"},
            request=httpx.Request("POST", url),
        )

    _patch_transport(monkeypatch, post)
    monkeypatch.setattr(ollama_adapters.time, "sleep", lambda _seconds: None)
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError):
        provider.discover_design_forces(_context())

    assert attempts == 1


def test_transport_retry_does_not_retry_structured_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid content is a model failure, not a transport one.

    The single sanctioned schema-repair round stays the only second attempt, so a
    stage makes exactly two calls however malformed the responses are.
    """

    attempts = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _http_response({"message": {"role": "assistant", "content": "{}"}})

    _patch_transport(monkeypatch, post)
    monkeypatch.setattr(ollama_adapters.time, "sleep", lambda _seconds: None)
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ModelOutputValidationError):
        provider.discover_design_forces(_context())

    assert attempts == 2


def test_every_reasoning_task_has_a_declared_timeout_class() -> None:
    """A task added later inherits the deep budget deliberately, not by omission."""

    provider = OllamaReasoningProvider(
        _reasoning_config().model_copy(
            update={"fast_timeout_seconds": 5, "deep_timeout_seconds": 50}
        )
    )
    fast = OllamaReasoningProvider._FAST_TASKS  # pyright: ignore[reportPrivateUsage]

    for task in ReasoningTask:
        expected = 5 if task in fast else 50
        assert provider._timeout_for(task) == expected  # pyright: ignore[reportPrivateUsage]

    assert fast == {
        ReasoningTask.CLASSIFY_REPORT_QUESTION,
        ReasoningTask.SUMMARIZE_REPORT_CONVERSATION,
    }


def test_timeout_classes_fall_back_to_the_single_configured_timeout() -> None:
    """A workspace written before the classes existed keeps its exact behaviour."""

    provider = OllamaReasoningProvider(_reasoning_config())

    assert _reasoning_config().fast_timeout_seconds is None
    for task in ReasoningTask:
        assert provider._timeout_for(task) == (  # pyright: ignore[reportPrivateUsage]
            _reasoning_config().timeout_seconds
        )
