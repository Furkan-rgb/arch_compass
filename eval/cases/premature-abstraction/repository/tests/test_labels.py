from labels import format_task_label


def test_formats_the_local_task_name() -> None:
    assert format_task_label("prepare_release_notes") == "Prepare Release Notes"


def test_ignores_surrounding_whitespace() -> None:
    assert format_task_label("  review_changes  ") == "Review Changes"
