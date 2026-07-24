from __future__ import annotations

from archcompass.domain.case import (
    ArchitectureCase,
    CaseStatement,
    CaseUpdate,
    StatementKind,
)


def test_case_revisions_are_append_only(runtime) -> None:
    created = runtime.case_service.create(
        ArchitectureCase(
            title="A case",
            problem_statement="A responsibility is unclear.",
            desired_outcome="Choose an owner.",
            functional_requirements=["First"],
        )
    )
    updated = runtime.case_service.update(
        created.case_id,
        CaseUpdate(title="Updated case", functional_requirements=["Replacement"]),
    )
    assert updated.revision == 2
    assert updated.snapshot.title == "Updated case"
    assert updated.snapshot.functional_requirements == ["Replacement"]
    history = runtime.case_service.history(created.case_id)
    assert [item.revision for item in history] == [1, 2]
    assert history[0].snapshot.title == "A case"


def test_case_update_revalidates_nested_statements(runtime) -> None:
    existing = CaseStatement(
        text="Where should discovery live?",
        kind=StatementKind.QUESTION,
        source="user",
    )
    created = runtime.case_service.create(
        ArchitectureCase(
            title="A case with a follow-up",
            problem_statement="A responsibility is unclear.",
            desired_outcome="Choose an owner.",
            unresolved_questions=[existing],
        )
    )

    updated = runtime.case_service.update(
        created.case_id,
        CaseUpdate(
            unresolved_questions=[
                *created.snapshot.unresolved_questions,
                CaseStatement(
                    text="What if discovery becomes remote?",
                    kind=StatementKind.QUESTION,
                    source="advisor_composer",
                ),
            ]
        ),
    )

    assert updated.revision == 2
    assert [item.text for item in updated.snapshot.unresolved_questions] == [
        "Where should discovery live?",
        "What if discovery becomes remote?",
    ]
    assert all(
        isinstance(item, CaseStatement)
        for item in updated.snapshot.unresolved_questions
    )
