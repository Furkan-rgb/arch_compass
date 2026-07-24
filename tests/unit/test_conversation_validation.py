from archcompass.application.conversation_validation import (
    validate_conversation_summary,
)
from archcompass.domain.conversation import (
    ConversationSummary,
    ConversationSummaryItem,
)


def test_conversation_summary_rejects_new_evidence_references() -> None:
    errors = validate_conversation_summary(
        ConversationSummary(
            narrative="The discussion mentioned FIND-999 and claim-invented.",
            discussed_finding_ids=["FIND-999"],
            discussed_evidence_ids=["claim-invented"],
            unresolved_questions=[
                ConversationSummaryItem(
                    text="Does policy_invented apply?",
                    source_ordinals=[1],
                    evidence_ids=["policy_invented"],
                )
            ],
        ),
        allowed_finding_ids={"FIND-001"},
        allowed_claim_ids={"claim-supported"},
        allowed_evidence_ids={"node-supported"},
        allowed_policy_ids={"known-policy"},
        allowed_source_ordinals={1},
        user_source_ordinals={1},
    )

    assert any("unknown finding IDs" in error for error in errors)
    assert any("unknown evidence IDs" in error for error in errors)
    assert any("unknown evidence" in error for error in errors)


def test_conversation_summary_accepts_known_additional_evidence() -> None:
    assert (
        validate_conversation_summary(
            ConversationSummary(
                narrative="FIND-001 cites node-additional.",
                discussed_finding_ids=["FIND-001"],
                discussed_evidence_ids=["node-additional"],
                user_corrections=[
                    ConversationSummaryItem(
                        text="The user corrected the scope of FIND-001.",
                        source_ordinals=[3],
                        finding_ids=["FIND-001"],
                        evidence_ids=["node-additional"],
                    )
                ],
            ),
            allowed_finding_ids={"FIND-001"},
            allowed_claim_ids=set(),
            allowed_evidence_ids={"node-additional"},
            allowed_policy_ids={"known-policy"},
            allowed_source_ordinals={1, 2, 3},
            user_source_ordinals={1, 3},
        )
        == []
    )


def test_conversation_summary_items_must_link_to_user_message_ordinals() -> None:
    errors = validate_conversation_summary(
        ConversationSummary(
            narrative="A correction was discussed.",
            user_corrections=[
                ConversationSummaryItem(
                    text="The correction came from an assistant turn.",
                    source_ordinals=[2],
                )
            ],
        ),
        allowed_finding_ids=set(),
        allowed_claim_ids=set(),
        allowed_evidence_ids=set(),
        allowed_policy_ids=set(),
        allowed_source_ordinals={1, 2},
        user_source_ordinals={1},
    )

    assert errors == [
        "Conversation summary item must cite user-message ordinals: [2]"
    ]
