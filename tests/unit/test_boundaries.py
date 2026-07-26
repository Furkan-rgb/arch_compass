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
        "report_writer",
        "run_repository",
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
        "review": "review_service",
        "review_show": "review_repository",
        "review_list": "review_repository",
        "review_ask": "review_conversation_service",
        "review_history": "review_conversation_service",
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
    }
    used_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)
    assert {
        "atlas_service",
        "case_service",
        "policy_service",
            "repository_service",
                } <= used_attributes


def test_review_answers_are_assembled_before_model_adapters() -> None:
    """The stage receives typed domain objects; it does not fetch or choose evidence.

    Its parameters are the whole pinned review, the history, and the question. Nothing it
    is given is a handle it would have to resolve, and there is nothing for it to retrieve,
    so a model adapter cannot become the thing that decides what evidence an answer rests on.
    """

    for path in (
        SOURCE_ROOT / "ports" / "reasoning.py",
        SOURCE_ROOT / "adapters" / "models" / "deterministic.py",
        SOURCE_ROOT / "adapters" / "models" / "structured.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "answer_review_question"
        ]
        assert len(methods) == 1, path
        assert [argument.arg for argument in methods[0].args.args] == [
            "self",
            "review",
            "history",
            "question",
        ], path

    adapters = ast.parse(
        (SOURCE_ROOT / "adapters" / "models" / "structured.py").read_text(encoding="utf-8")
    )
    imported = {
        node.module or ""
        for node in ast.walk(adapters)
        if isinstance(node, ast.ImportFrom)
    }
    # A model adapter that could reach the application could choose its own evidence.
    assert not any(name.startswith("archcompass.application") for name in imported)

def test_model_adapters_do_not_import_application_or_workflow_layers() -> None:
    """Adapters own transport and schema constraint, never application policy.

    `docs/architecture.md` states that model adapters "do not choose evidence,
    history, citation, or truncation rules". This pins the import direction that
    makes the statement enforceable rather than aspirational.
    """

    forbidden = ("archcompass.application", "archcompass.workflows")
    for path in (SOURCE_ROOT / "adapters" / "models").rglob("*.py"):
        imports = _imports(path)
        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in forbidden
        ), f"{path.relative_to(SOURCE_ROOT)} imports the application or workflow layer"


def test_the_deterministic_provider_contains_no_evaluation_vocabulary() -> None:
    """The test double must relay its inputs, not recognise the evaluation fixtures.

    It previously branched on tokens taken from the evaluation cases - down to the literal
    filenames of the brownfield fixture's modules - so the deterministic tier partly
    asserted what the double remembered rather than what the pipeline did. Any output that
    depends on case wording is unfalsifiable evidence.
    """

    source = (SOURCE_ROOT / "adapters" / "models" / "deterministic.py").read_text(
        encoding="utf-8"
    )
    borrowed = [
        token
        for token in (
            # `speech-vendor`.
            "qwen",
            "voice",
            "vendor",
            "preflight",
            "frontend",
            "narration",
            "speech",
            # `boundary-review`.
            "scheduler",
            "reminder",
            "sms",
            # Either.
            "one implementation",
        )
        if token in source.casefold()
    ]
    assert borrowed == [], (
        f"deterministic.py branches on evaluation-case vocabulary: {borrowed}"
    )
