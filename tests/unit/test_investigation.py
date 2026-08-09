"""The two tools a stage may call before it asks, and everything they refuse to do.

Investigation is the one place a model chooses what to look at, so what is worth defending
here is the boundary rather than the lookup: a query that reaches nothing, a path that
points outside the repository, a tool that does not exist and an argument that is the wrong
shape all have to come back as text the model reads and moves on from. A raised exception
would fail a review over a bad guess, and a review that asked nothing is a far better
outcome than one that failed.

The other half is the record. Every call is kept, including the ones that answered nothing,
because a question composed from a lookup nobody can see is exactly the unverifiable
evidence §12.0 refuses.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.adapters.analysis.source_reader import SafeSourceReader
from archcompass.application.investigation import (
    MAX_READ_LINES,
    MAX_RESULT_CHARACTERS,
    MAX_SEARCH_HITS,
    MAX_SEARCH_LINE_CHARACTERS,
    RepositoryInvestigator,
)


def _investigator(root: Path) -> RepositoryInvestigator:
    return RepositoryInvestigator(root=root, source_reader=SafeSourceReader())


def test_the_toolbox_offers_exactly_the_two_read_only_tools() -> None:
    """Two tools, and both of them read. Nothing here can change a repository."""

    tools = _investigator(Path(".")).tools

    assert [tool.name for tool in tools] == ["search_source", "read_source"]
    for tool in tools:
        assert tool.description
        assert tool.parameters["type"] == "object"


def test_a_search_names_every_file_and_line_the_text_occurs_on(tmp_path: Path) -> None:
    """`path:lineno: text` is the whole format, because it is what a follow-up read needs."""

    (tmp_path / "alpha.py").write_text("SINK = 1\nOTHER = 2\nprint(SINK)\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("value = 3\n", encoding="utf-8")
    (tmp_path / "gamma.toml").write_text('name = "SINK"\n', encoding="utf-8")

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    assert "alpha.py:1: SINK = 1" in result
    assert "alpha.py:3: print(SINK)" in result
    assert 'gamma.toml:1: name = "SINK"' in result
    assert "beta.py" not in result


def test_a_search_is_case_sensitive_and_literal(tmp_path: Path) -> None:
    """A symbol is a symbol. Folding case would answer a question nobody asked."""

    (tmp_path / "alpha.py").write_text("sink = 1\n", encoding="utf-8")

    assert "sink" not in _investigator(tmp_path).call("search_source", {"query": "SINK"})


def test_a_search_that_finds_nothing_says_so(tmp_path: Path) -> None:
    """Silence would read as a failed tool; this is a finding and has to sound like one."""

    (tmp_path / "alpha.py").write_text("value = 1\n", encoding="utf-8")

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    assert "No line" in result
    assert "SINK" in result


def test_a_search_capped_by_its_own_ceiling_says_how_much_it_left_out(
    tmp_path: Path,
) -> None:
    """A truncated result read as a complete one is a count the model would then quote."""

    total = MAX_SEARCH_HITS + 7
    (tmp_path / "many.py").write_text(
        "\n".join(f"SINK_{number} = {number}" for number in range(total)) + "\n",
        encoding="utf-8",
    )

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    assert len([line for line in result.splitlines() if line.startswith("many.py:")]) == (
        MAX_SEARCH_HITS
    )
    assert "7 more matches not shown" in result


def test_a_matched_line_is_clamped_rather_than_carried_whole(tmp_path: Path) -> None:
    """A minified bundle is one line and would spend the whole result on itself."""

    (tmp_path / "wide.py").write_text("SINK = " + "x" * 4000 + "\n", encoding="utf-8")

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    line = next(item for item in result.splitlines() if item.startswith("wide.py:"))
    assert len(line) <= len("wide.py:1: ") + MAX_SEARCH_LINE_CHARACTERS


def test_a_search_skips_what_an_analysis_would_never_read(tmp_path: Path) -> None:
    """The same discipline the analyser applies, because it is the same repository.

    A `.git` directory, a build output and a file that is not source at all are not
    evidence about a boundary; a search that returned them would answer questions about
    the tool's own leavings.
    """

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.toml").write_text("SINK = 1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendor.py").write_text("SINK = 1\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("SINK is discussed here.\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("SINK = 1\n", encoding="utf-8")

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    assert "kept.py:1" in result
    assert ".git" not in result
    assert "node_modules" not in result
    assert "notes.md" not in result


def test_a_search_leaves_out_a_file_too_large_to_be_source(tmp_path: Path) -> None:
    """Measured from the directory entry, so an oversized file is never read at all."""

    (tmp_path / "generated.py").write_text("SINK = 1\n" + "# padding\n" * 200_000, encoding="utf-8")
    (tmp_path / "kept.py").write_text("SINK = 2\n", encoding="utf-8")

    result = _investigator(tmp_path).call("search_source", {"query": "SINK"})

    assert "kept.py:1" in result
    assert "generated.py" not in result


def test_a_read_serves_the_asked_for_span_and_says_which_one_it_served(
    tmp_path: Path,
) -> None:
    """The header is the point: a model that does not know what it got cannot cite it."""

    (tmp_path / "alpha.py").write_text(
        "\n".join(f"line_{number} = {number}" for number in range(1, 21)) + "\n",
        encoding="utf-8",
    )

    result = _investigator(tmp_path).call(
        "read_source", {"path": "alpha.py", "start_line": 3, "end_line": 5}
    )

    assert result.startswith("alpha.py:3-5")
    assert "line_3 = 3" in result
    assert "line_6" not in result


def test_a_read_is_clamped_to_a_span_a_stage_can_actually_use(tmp_path: Path) -> None:
    """A whole module asked for as one span would crowd out the questions it is for."""

    (tmp_path / "long.py").write_text(
        "\n".join(f"line_{number} = {number}" for number in range(1, 501)) + "\n",
        encoding="utf-8",
    )

    result = _investigator(tmp_path).call(
        "read_source", {"path": "long.py", "start_line": 1, "end_line": 500}
    )

    assert result.startswith(f"long.py:1-{MAX_READ_LINES}")
    assert f"line_{MAX_READ_LINES + 1} " not in result


def test_a_path_outside_the_repository_comes_back_as_text(tmp_path: Path) -> None:
    """The refusal already exists in the reader; what matters is that it is not raised.

    A model guessing at a path is ordinary, and a guess that escapes the repository must
    cost it one turn rather than cost the reader their review.
    """

    (tmp_path / "alpha.py").write_text("value = 1\n", encoding="utf-8")

    result = _investigator(tmp_path).call(
        "read_source", {"path": "../secrets.env", "start_line": 1, "end_line": 5}
    )

    assert "could not be read" in result
    assert "secrets.env" in result


def test_a_tool_that_does_not_exist_comes_back_as_text(tmp_path: Path) -> None:
    """Naming the tools it does have, because the next turn is the model's to fix."""

    result = _investigator(tmp_path).call("grep_source", {"query": "SINK"})

    assert "grep_source" in result
    assert "search_source" in result
    assert "read_source" in result


def test_arguments_of_the_wrong_shape_come_back_as_text(tmp_path: Path) -> None:
    """A schema constrains a well-behaved caller and not this one."""

    investigator = _investigator(tmp_path)

    assert "query" in investigator.call("search_source", {})
    assert "query" in investigator.call("search_source", {"query": 7})
    assert "start_line" in investigator.call(
        "read_source", {"path": "alpha.py", "start_line": "three", "end_line": 5}
    )
    assert "path" in investigator.call("read_source", {"start_line": 1, "end_line": 5})


def test_a_result_too_long_to_carry_is_truncated_with_a_note(tmp_path: Path) -> None:
    """Every result is bounded, because the next turn carries all of them at once."""

    (tmp_path / "long.py").write_text(
        "\n".join(f"line_{number} = {'x' * 200}" for number in range(1, 200)) + "\n",
        encoding="utf-8",
    )

    result = _investigator(tmp_path).call(
        "read_source", {"path": "long.py", "start_line": 1, "end_line": 80}
    )

    assert len(result) <= MAX_RESULT_CHARACTERS
    assert "truncated" in result


def test_every_call_is_recorded_in_order_including_the_ones_that_failed(
    tmp_path: Path,
) -> None:
    """A lookup nobody can see is not evidence (§12.0).

    Failures are kept for the same reason the answers are: a question composed after four
    refused reads was composed from nothing, and the transcript is the only place that is
    visible.
    """

    (tmp_path / "alpha.py").write_text("SINK = 1\n", encoding="utf-8")
    investigator = _investigator(tmp_path)

    investigator.call("search_source", {"query": "SINK"})
    investigator.call("nonexistent", {})
    investigator.call("read_source", {"path": "alpha.py", "start_line": 1, "end_line": 1})

    assert [item.tool for item in investigator.transcript] == [
        "search_source",
        "nonexistent",
        "read_source",
    ]
    assert investigator.transcript[0].arguments == {"query": "SINK"}
    assert "alpha.py:1: SINK = 1" in investigator.transcript[0].result
    assert "nonexistent" in investigator.transcript[1].result
    assert investigator.transcript[2].result.startswith("alpha.py:1-1")


def test_an_investigation_that_has_not_ended_has_nothing_to_say_about_how_it_ended(
    tmp_path: Path,
) -> None:
    """The two closing values start empty, so a toolbox nobody drove states nothing.

    They are read whether or not the loop that ends an investigation ever ran — a provider
    without the capability is handed a toolbox and never calls it — and a default of "" is
    what keeps that case saying "no closing prose" rather than inventing one.
    """

    investigator = _investigator(tmp_path)

    assert (investigator.closing, investigator.abandoned) == ("", "")


def test_the_loop_closes_the_record_with_what_the_stage_made_of_it(tmp_path: Path) -> None:
    """The one thing the transcript cannot hold: which of those findings mattered.

    Written by the loop rather than inferred here, because the closing prose is the model's
    and the abandonment note is the loop's own account of why it stopped. Both are kept even
    when the other is empty: an investigation that concluded was not abandoned, and one that
    was abandoned mid-turn never got to say anything.
    """

    investigator = _investigator(tmp_path)

    investigator.conclude("Both copies feed the same client.", "")

    assert investigator.closing == "Both copies feed the same client."
    assert investigator.abandoned == ""


def test_an_investigation_that_never_got_going_still_records_why(tmp_path: Path) -> None:
    """Nothing looked up and a reason for it is a real state, not an empty record.

    The first turn is the one that can fail before any tool runs, and a record showing no
    lookups and no note would read as a stage that decided it had nothing to check — the
    opposite of what happened.
    """

    investigator = _investigator(tmp_path)

    investigator.conclude("", "the model refused the request")

    assert investigator.transcript == ()
    assert investigator.abandoned == "the model refused the request"
