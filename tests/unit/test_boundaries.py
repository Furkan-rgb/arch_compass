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
    """The core packages, each one asserted to be there before it is swept.

    `rglob` over a directory that does not exist yields nothing and passes, so a guard named
    after a package can outlive the package and go on reporting success over no files at all.
    That happened: `workflows/` was deleted and this list kept naming it for months. Asserting
    the directory exists is what makes a future deletion fail here instead of going quiet.
    """

    forbidden = (
        "archcompass.adapters",
        "archcompass.presentation",
        "sqlite3",
        "httpx",
        "typer",
    )
    for package in ("domain", "application", "ports"):
        root = SOURCE_ROOT / package
        assert root.is_dir(), f"{package}/ is gone; this guard now sweeps nothing"
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
        "query_service",
        "report_writer",
        "run_repository",
    }
    used_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)

    expected_service_by_command = {
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
        "review": "review_workflow_service",
        "review_show": "review_workflow_service",
        "review_list": "review_workflow_service",
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


#: The two modules under `presentation/web/` that may name an adapter, because building a
#: runtime is what they do: one composes the local and per-session workspaces, the other is
#: the hosted deployment's entry point. Everything else in the package — every router, every
#: dependency, the streams and the error table — reaches the system through `Runtime`.
_WEB_RUNTIME_BUILDERS = {"hosted.py", "runtimes.py"}


def test_web_routes_use_application_services_only() -> None:
    """The whole web package, not just one file, and the routers most of all.

    This used to read `app.py` alone, which was accurate while `app.py` was the whole HTTP
    surface. Now that the routes are a package, a guard aimed at one file would pass over a
    router that imported an adapter — so the sweep is the package, minus the two modules
    whose job is to build a runtime out of adapters in the first place.
    """

    web_root = SOURCE_ROOT / "presentation" / "web"
    routes_root = web_root / "routes"
    assert routes_root.is_dir(), "presentation/web/routes is gone; this guard sweeps nothing"

    swept = [
        path
        for path in web_root.rglob("*.py")
        if path.name not in _WEB_RUNTIME_BUILDERS
    ]
    assert swept, "the web package is gone; this guard now sweeps nothing"
    for path in swept:
        assert not any(
            imported == "archcompass.adapters"
            or imported.startswith("archcompass.adapters.")
            for imported in _imports(path)
        ), f"{path.relative_to(SOURCE_ROOT)} imports an adapter"

    forbidden_runtime_attributes = {
        "analyzer",
        "atlas_repository",
        "case_repository",
        "database",
        "job_repository",
        "query_service",
        "report_writer",
        "run_repository",
    }
    used_attributes: set[str] = set()
    for path in routes_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used_attributes |= {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)
    assert {
        "atlas_service",
        "case_service",
        "policy_service",
        "repository_service",
    } <= used_attributes


def test_model_adapters_do_not_import_the_application_layer() -> None:
    """Adapters own transport and schema constraint, never application policy.

    `docs/architecture.md` states that model adapters "do not choose evidence,
    history, citation, or truncation rules". This pins the import direction that
    makes the statement enforceable rather than aspirational.
    """

    root = SOURCE_ROOT / "adapters" / "models"
    assert root.is_dir(), "adapters/models is gone; this guard now sweeps nothing"
    for path in root.rglob("*.py"):
        imports = _imports(path)
        assert not any(
            imported == "archcompass.application"
            or imported.startswith("archcompass.application.")
            for imported in imports
            ), f"{path.relative_to(SOURCE_ROOT)} imports the application layer"


def test_dataclass_domain_imports_only_the_standard_library_and_itself() -> None:
    forbidden = (
        "pydantic",
        "langchain",
        "langgraph",
        "fastapi",
        "archcompass.adapters",
        "archcompass.application",
        "archcompass.boundary",
    )
    root = SOURCE_ROOT / "domain"
    for path in root.rglob("*.py"):
        imports = _imports(path)
        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in forbidden
        ), f"{path.relative_to(SOURCE_ROOT)} crosses the dataclass-domain boundary"
