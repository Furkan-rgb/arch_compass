from __future__ import annotations

import typer

from archcompass.presentation.cli.app import (
    app,
    atlas_app,
    case_app,
    policies_app,
    policy_sources_app,
    repo_app,
    run_app,
)


def _commands(application: typer.Typer) -> set[str]:
    return {
        command.name
        for command in application.registered_commands
        if command.name is not None
    }


def _groups(application: typer.Typer) -> set[str]:
    return {
        group.name
        for group in application.registered_groups
        if group.name is not None
    }


def test_existing_cli_command_names_remain_registered() -> None:
    assert {"init", "advise"} <= _commands(app)
    assert {"policies", "repo", "atlas", "case", "run"} <= _groups(app)
    assert {"rebuild", "list", "show"} <= _commands(policies_app)
    assert {"sources"} <= _groups(policies_app)
    assert {"add", "remove", "list"} <= _commands(policy_sources_app)
    assert {"index"} <= _commands(repo_app)
    assert {"summary", "inspect", "hotspots"} <= _commands(atlas_app)
    assert {"create", "show", "update", "history"} <= _commands(case_app)
    assert {"show"} <= _commands(run_app)
