from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "archcompass"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]


def test_core_layers_do_not_import_infrastructure_or_presentation() -> None:
    forbidden = (
        "archcompass.adapters",
        "archcompass.presentation",
        "sqlite3",
        "sqlite_vec",
        "httpx",
        "typer",
    )
    for package in ("domain", "application", "workflows", "ports"):
        root = SOURCE_ROOT / package
        for path in root.rglob("*.py"):
            imports = _imports(path)
            assert not any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for imported in imports
                for prefix in forbidden
            ), f"{path.relative_to(SOURCE_ROOT)} imports infrastructure or presentation"


def test_cli_commands_use_application_services_only() -> None:
    path = SOURCE_ROOT / "presentation" / "cli" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(
        imported == "archcompass.adapters"
        or imported.startswith("archcompass.adapters.")
        for imported in _imports(path)
    )

    forbidden_runtime_attributes = {
        "analyzer",
        "atlas_repository",
        "case_repository",
        "database",
        "policy_store",
        "query_service",
        "report_service",
        "report_writer",
        "run_repository",
        "workflow",
    }
    used_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)

    expected_service_by_command = {
        "policies_rebuild": "policy_service",
        "policies_list": "policy_service",
        "policies_show": "policy_service",
        "policy_sources_add": "policy_service",
        "policy_sources_remove": "policy_service",
        "policy_sources_list": "policy_service",
        "repo_index": "repository_service",
        "atlas_summary": "atlas_service",
        "atlas_inspect": "atlas_service",
        "atlas_hotspots": "atlas_service",
        "case_create": "case_service",
        "case_show": "case_service",
        "case_update": "case_service",
        "case_history": "case_service",
        "advise": "advice_service",
        "run_show": "run_service",
    }
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    for command, service in expected_service_by_command.items():
        attributes = {
            node.attr
            for node in ast.walk(functions[command])
            if isinstance(node, ast.Attribute)
        }
        assert service in attributes, f"{command} does not delegate through {service}"


def test_web_routes_use_application_services_only() -> None:
    path = SOURCE_ROOT / "presentation" / "web" / "app.py"
    imports = _imports(path)

    assert not any(
        imported == "archcompass.adapters"
        or imported.startswith("archcompass.adapters.")
        for imported in imports
    )

    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_runtime_attributes = {
        "analyzer",
        "atlas_repository",
        "case_repository",
        "database",
        "job_repository",
        "policy_store",
        "query_service",
        "report_writer",
        "run_repository",
        "workflow",
    }
    used_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)
    assert {
        "atlas_service",
        "case_service",
        "job_service",
        "policy_service",
            "repository_service",
            "run_service",
            "conversation_service",
        } <= used_attributes


def test_report_conversation_context_is_assembled_before_model_adapters() -> None:
    paths = [
        SOURCE_ROOT / "ports" / "reasoning.py",
        SOURCE_ROOT / "adapters" / "models" / "deterministic.py",
        SOURCE_ROOT / "adapters" / "models" / "ollama.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "answer_report_question"
        ]
        assert len(methods) == 1
        assert [argument.arg for argument in methods[0].args.args] == [
            "self",
            "context",
        ]

    builder = SOURCE_ROOT / "application" / "conversation_context.py"
    imported_names = {
        alias.name
        for node in ast.walk(ast.parse(builder.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert {
        "ConsultationRun",
        "ConversationMessage",
        "ReportConversation",
        "ReportConversationContext",
    } <= imported_names
