from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from archcompass.adapters.models.ollama import OllamaReasoningProvider
from archcompass.adapters.models.prompt_contracts import (
    ANALYZE_CONCERN_CLUSTER,
    ANSWER_REPORT_QUESTION,
    CLASSIFY_REPORT_QUESTION,
    CLUSTER_DESIGN_FORCES,
    DISCOVER_DESIGN_FORCES,
    LINK_STATEMENT_SUPPORT,
    OLLAMA_STAGE_PROMPTS,
    REPAIR_CONVERSATION_ANSWER,
    SUMMARIZE_REPORT_CONVERSATION,
    SYNTHESIZE_RECOMMENDATION,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.base import canonical_json
from archcompass.domain.consultation import GlobalContext


def _config() -> ReasoningModelConfig:
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


def _response(payload: object) -> httpx.Response:
    request = httpx.Request("POST", "http://ollama.test/api/chat")
    return httpx.Response(200, json=payload, request=request)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def test_canonical_json_uses_one_serializer_for_models_and_prompt_mappings() -> None:
    context = _context()

    assert canonical_json(context) == canonical_json(
        context.model_dump(mode="json")
    )
    nested = canonical_json({"context": context})
    assert nested == canonical_json(
        {"context": context.model_dump(mode="json")}
    )
    assert "'case_id': 'case-test'" not in nested


def test_stage_prompt_identities_are_versioned_unique_and_content_bound() -> None:
    expected_versions = {
        "discover_design_forces": 5,
        "cluster_design_forces": 3,
        "plan_atlas_queries": 5,
        "analyze_concern_cluster": 4,
        "generate_alternatives": 3,
        "evaluate_scenarios": 4,
        "synthesize_recommendation": 3,
        "classify_report_question": 2,
        "answer_report_question": 6,
        "summarize_report_conversation": 2,
        "repair_conversation_answer": 2,
    }

    assert set(OLLAMA_STAGE_PROMPTS) == set(expected_versions)
    identities = []
    for task, version in expected_versions.items():
        contract = OLLAMA_STAGE_PROMPTS[task]
        assert contract.identity.startswith(f"{contract.name}:v{version}:")
        assert len(contract.content_fingerprint) == 12
        identities.append(contract.identity)
    assert len(identities) == len(set(identities))

    changed = replace(
        DISCOVER_DESIGN_FORCES,
        request=DISCOVER_DESIGN_FORCES.request + " Materially changed.",
    )
    assert changed.version == DISCOVER_DESIGN_FORCES.version
    assert changed.identity != DISCOVER_DESIGN_FORCES.identity


def test_prompt_contracts_cover_architectural_judgement_rules() -> None:
    shared = _normalized(DISCOVER_DESIGN_FORCES.system_prompt)
    assert "evidence hierarchy" in shared
    assert "absence of evidence is not evidence of absence" in shared
    assert "policies as reasoning lenses" in shared
    assert "local implementation complexity" in shared
    assert "system-wide complexity" in shared
    assert "minimum architecture" in shared

    force_contract = _normalized(DISCOVER_DESIGN_FORCES.stage_contract)
    for concern in (
        "responsibility ownership",
        "resource lifecycle",
        "data ownership",
        "dependency spread",
    ):
        assert concern in force_contract
    assert "owns force identity" in _normalized(DISCOVER_DESIGN_FORCES.request)

    cluster_contract = _normalized(CLUSTER_DESIGN_FORCES.stage_contract)
    assert "different repository" in cluster_contract
    assert "policies" in cluster_contract
    assert "one generic architecture cluster" in cluster_contract
    cluster_request = _normalized(CLUSTER_DESIGN_FORCES.request)
    assert "request-local constrained reference handles" in cluster_request
    assert "assigns internal cluster ids" in cluster_request

    analysis_contract = _normalized(ANALYZE_CONCERN_CLUSTER.stage_contract)
    assert "call a proxy a proxy" in analysis_contract
    assert "policy exceptions and conflicts" in analysis_contract
    assert "local complexity contains system-wide complexity" in analysis_contract

    synthesis_contract = _normalized(SYNTHESIZE_RECOMMENDATION.stage_contract)
    assert "cross-cluster" in synthesis_contract
    assert "smallest responsibility allocation" in synthesis_contract
    assert "keep-local decision" in synthesis_contract
    assert "canonical architectural findings" in synthesis_contract
    assert "contextual importance" in synthesis_contract

    classification_contract = _normalized(CLASSIFY_REPORT_QUESTION.stage_contract)
    assert "at most eight" in classification_contract
    assert "retrieval action" in classification_contract
    answer_contract = _normalized(ANSWER_REPORT_QUESTION.stage_contract)
    assert "original-run" in answer_contract
    assert "additional conversation" in answer_contract
    assert "historical recommendation" in answer_contract
    summary_contract = _normalized(SUMMARIZE_REPORT_CONVERSATION.stage_contract)
    assert "new evidence" in summary_contract
    assert "6,000" in summary_contract
    repair_contract = _normalized(REPAIR_CONVERSATION_ANSWER.stage_contract)
    assert "allowlist" in repair_contract
    assert "one repair" in repair_contract

    support_contract = _normalized(LINK_STATEMENT_SUPPORT.stage_contract)
    assert "directly support their actual meaning" in support_contract
    assert "general topical relevance is not support" in support_contract


def test_ollama_request_uses_the_stage_contract_and_default_sampling(
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
        return _response({"message": {"content": content}})

    monkeypatch.setattr(httpx, "post", post)
    provider = OllamaReasoningProvider(_config())

    provider.discover_design_forces(_context())

    assert provider.prompt_identity("discover_design_forces") == (DISCOVER_DESIGN_FORCES.identity)
    request = captured["json"]
    assert isinstance(request, dict)
    messages = request["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {
        "role": "system",
        "content": DISCOVER_DESIGN_FORCES.system_prompt,
    }
    assert DISCOVER_DESIGN_FORCES.request in messages[1]["content"]
    assert "Input:" in messages[1]["content"]
    assert '"case_id":"case-test"' in messages[1]["content"]
    assert "'case_id': 'case-test'" not in messages[1]["content"]
    assert request["options"] == {
        "num_ctx": 32768,
        "num_predict": 16384,
    }
    assert "temperature" not in request
    assert "temperature" not in request["options"]
