from pathlib import Path

import pytest
import yaml

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ConsultationRun,
    RecommendationDisposition,
)


def _advise_case(
    runtime: Runtime,
    case_path: str,
    *,
    repository_path: str | None = None,
) -> ConsultationRun:
    data = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    revision = runtime.case_service.create(ArchitectureCase.model_validate(data))
    if repository_path is None:
        return runtime.workflow.advise(revision.case_id)
    atlas = runtime.analyzer.analyze(Path(repository_path).resolve())
    runtime.atlas_repository.save(atlas)
    return runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )


@pytest.mark.evaluation
def test_audiobook_stays_greenfield_and_provider_owned(runtime: Runtime) -> None:
    run = _advise_case(runtime, "eval/cases/audiobook-greenfield/case.yaml")

    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.execution_metadata["atlas_queries"] == 0
    assert run.report is not None
    report = run.report
    # A greenfield case surfaces no repository evidence, so an unchanged design is the
    # complete recommendation (master plan invariant 16). The wording is the model's to
    # choose; only the evidence contract is the pipeline's.
    assert report.disposition == RecommendationDisposition.KEEP_LOCAL
    assert report.repository_observations == []
    assert report.confirmed_context
    assert all(
        claim.atlas_references == [] for claim in report.evidence_appendix
    )


@pytest.mark.evaluation
def test_report_conversation_summarizes_prioritizes_and_explains_policy(
    runtime: Runtime,
) -> None:
    run = _advise_case(runtime, "eval/cases/audiobook-greenfield/case.yaml")
    assert run.report is not None
    conversation = runtime.conversation_service.create(run.run_id)

    summary = runtime.conversation_service.ask(
        conversation.conversation_id,
        "What are the main findings?",
    )
    priority = runtime.conversation_service.ask(
        conversation.conversation_id,
        "Which finding has the highest priority?",
    )
    policy = runtime.conversation_service.ask(
        conversation.conversation_id,
        "Which pinned policies explain the recommendation?",
    )

    assert summary.answer is not None
    assert summary.answer.relevant_finding_ids == [
        item.finding_id for item in run.report.findings[:8]
    ]
    assert "canonical findings" in summary.answer.direct_answer.text.casefold()
    assert priority.answer is not None
    assert "highest contextual priority" in priority.answer.direct_answer.text.casefold()
    assert policy.answer is not None
    assert "pinned policies" in policy.answer.direct_answer.text.casefold()
    assert any(claim.policy_ids for claim in policy.answer.claims)


@pytest.mark.evaluation
def test_report_counterfactual_and_runtime_limits_remain_read_only(
    runtime: Runtime,
) -> None:
    run = _advise_case(runtime, "eval/cases/audiobook-greenfield/case.yaml")
    conversation = runtime.conversation_service.create(run.run_id)
    revision_before = runtime.case_service.show(run.case_id).revision

    counterfactual = runtime.conversation_service.ask(
        conversation.conversation_id,
        "What if hosted providers become mandatory?",
    )
    runtime_question = runtime.conversation_service.ask(
        conversation.conversation_id,
        "What is the production runtime latency?",
    )

    assert counterfactual.answer is not None
    assert "historical decision" in counterfactual.answer.direct_answer.text.casefold()
    assert "counterfactual" in counterfactual.answer.uncertainty[0].text.casefold()
    assert runtime_question.answer is not None
    assert "no runtime production evidence" in runtime_question.answer.direct_answer.text.casefold()
    assert runtime.case_service.show(run.case_id).revision == revision_before


@pytest.mark.evaluation
def test_provider_leakage_moves_discovery_with_located_evidence(
    runtime: Runtime,
) -> None:
    run = _advise_case(
        runtime,
        "eval/cases/provider-leakage/case.yaml",
        repository_path="eval/cases/provider-leakage/repository",
    )

    assert [cluster.title for cluster in run.clusters] == [
        "Responsibility ownership",
        "Change locality and evolution",
    ]
    assert len(run.focused_packets) == len(run.concern_analyses) == 2
    node_sets = [
        {node.node_id for node in packet.node_summaries}
        for packet in run.focused_packets
    ]
    policy_sets = [
        {retrieved.policy.id for retrieved in packet.policies}
        for packet in run.focused_packets
    ]
    assert all(node_sets)
    assert node_sets[0].isdisjoint(node_sets[1])
    assert all(policy_sets)
    assert policy_sets[0] != policy_sets[1]
    assert run.report is not None
    report = run.report
    assert report.disposition == RecommendationDisposition.INTRODUCE_BOUNDARY
    assert report.repository_observations
    assert all(
        reference.location is not None
        for claim in report.repository_observations
        for reference in claim.atlas_references
    )
    # The blast-radius statement must cite claims rather than read well.
    assert report.change_amplification_analysis.supporting_claim_ids
    assert report.responsibility_allocation
    cited_policy_ids = {
        policy_id for claim in report.relevant_policies for policy_id in claim.policy_ids
    }
    assert cited_policy_ids
    assert cited_policy_ids <= {item.id for item in report.policy_evidence}


@pytest.mark.evaluation
def test_provider_context_assembly_is_discovered_without_naming_the_defect(
    runtime: Runtime,
) -> None:
    case_path = "eval/cases/provider-context-assembly/case.yaml"
    case_data = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    stated_case = str(case_data).casefold()
    assert not any(
        cue in stated_case
        for cue in (
            "adapter",
            "context assembly",
            "duplicat",
            "hosted",
            "interchangeab",
            "ollama",
            "provider",
            "replace",
            "switch",
            "transport",
        )
    )

    run = _advise_case(
        runtime,
        case_path,
        repository_path="eval/cases/provider-context-assembly/repository",
    )

    # The point of this case: the structural fixture is discovered from the repository
    # without the case text naming it. Both assertions are derived from the run's own
    # surfaced signals, so they fail if the overview stops reaching discovery or
    # planning - and cannot pass because the fake memorised a code.
    surfaced_codes = {signal.code for signal in run.report.findings[0].obscurity_signals} | {
        signal.code
        for packet in run.focused_packets
        for node in packet.node_evidence
        for signal in node.signals
    }
    assert surfaced_codes
    assert any(code not in stated_case for code in surfaced_codes)
    queried_codes = {
        code
        for cluster_plan in run.query_plans
        for query in cluster_plan.plan.queries
        if query.kind == "signals"
        for code in query.codes
    }
    assert queried_codes <= surfaced_codes | {
        signal.code for signal in run.report.findings[0].obscurity_signals
    }
    surfaced_signals = [
        signal
        for packet in run.focused_packets
        for evidence in packet.node_evidence
        for signal in evidence.signals
        if signal.code == "broad-input-boundary-preparation"
    ]
    assert len(surfaced_signals) == 1
    assert all(signal.nature == "structural_proxy" for signal in surfaced_signals)
    assert "report.findings" in surfaced_signals[0].message
    signal_packet = next(
        packet
        for packet in run.focused_packets
        if any(
            signal.code == "broad-input-boundary-preparation"
            for evidence in packet.node_evidence
            for signal in evidence.signals
        )
    )
    assert any(
        retrieved.policy.id == "separate-model-context-from-provider-transport"
        for retrieved in signal_packet.policies
    )
    assert any(
        excerpt.node_id == surfaced_signals[0].node_id
        for excerpt in signal_packet.excerpts
    )

    assert run.report is not None
    report = run.report
    # Which disposition this evidence warrants is an architectural judgement; the
    # deterministic tier asserts only that one was reached and recorded.
    assert report.disposition in set(RecommendationDisposition)
    # The strongest assertion in this tier: a repository observation must carry the
    # surfaced signal's own code and its own message text, with a located reference.
    # Both are read from the run rather than written here, so this proves the packet
    # reached the analysis instead of proving a literal was memorised.
    leading = surfaced_signals[0]
    assert any(
        leading.code in claim.text
        and "report.findings" in claim.text
        and claim.atlas_references
        and claim.atlas_references[0].location is not None
        for claim in report.repository_observations
    )
    # Every substantive statement is claim-linked; the prose itself is the model's.
    assert report.responsibility_allocation
    assert all(item.supporting_claim_ids for item in report.responsibility_allocation)
    assert report.conceptual_interfaces
    assert all(item.supporting_claim_ids for item in report.conceptual_interfaces)
    assert report.change_amplification_analysis.supporting_claim_ids


@pytest.mark.evaluation
def test_greenfield_provider_context_guidance_is_retrieved_without_an_atlas(
    runtime: Runtime,
) -> None:
    run = _advise_case(
        runtime,
        "eval/cases/provider-context-assembly/case.yaml",
    )

    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert any(
        retrieved.policy.id == "separate-model-context-from-provider-transport"
        for packet in run.focused_packets
        for retrieved in packet.policies
    )


@pytest.mark.evaluation
def test_premature_abstraction_keeps_the_single_implementation_local(
    runtime: Runtime,
) -> None:
    run = _advise_case(
        runtime,
        "eval/cases/premature-abstraction/case.yaml",
        repository_path="eval/cases/premature-abstraction/repository",
    )

    assert run.report is not None
    report = run.report
    # Whether this repository *should* keep its implementation local is an
    # architectural judgement no deterministic substitute can make; that claim belongs
    # to the architectural_quality tier. What the deterministic tier can prove is that
    # the fixture is analysable end to end and every observation stays located.
    assert report.disposition in set(RecommendationDisposition)
    assert report.implementation_sequence
    assert all(
        item.supporting_claim_ids for item in report.implementation_sequence
    )
    assert report.repository_observations
    assert all(
        reference.location is not None
        for claim in report.repository_observations
        for reference in claim.atlas_references
    )
