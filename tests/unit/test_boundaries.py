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


def test_review_answers_are_assembled_before_model_adapters() -> None:
    """The stage receives typed domain objects; it does not fetch or choose evidence.

    Its parameters are the whole pinned review, one assembled `ReviewEvidence`, the history,
    the question, and the background the application already retrieved. Nothing it is given
    is a handle it would have to resolve, and there is nothing left for it to retrieve — the
    application decides what an answer may be built from, including which background it
    sees, so a model adapter cannot become the thing that chooses its own evidence.

    Pinned as `evidence` rather than as a list of the things inside it, and that is the point
    of the shape. Three separate parameters were assembled at the call site, and three times
    something the record already held was left out — the code at each span, then the spans of
    a scattered concept, then the round of questions and answers — each of which this stage
    then truthfully reported as missing from the review. A single value moves that omission
    to one method with one test, instead of a signature that grows a parameter per lesson.

    `investigator` is the one thing here the application does not choose the contents of, and
    it is not a hole in the sentence above. Everything the stage may *reason from* is still
    assembled before the call; what this adds is a bounded set of read-only questions the
    stage may put to the repository, every one of them recorded and shown to the person who
    asked. That is §12.0's amendment, and it is why this list may grow by exactly this
    parameter and not by a repository root, an atlas, or a retrieval handle.
    """

    for path in (
        SOURCE_ROOT / "ports" / "reasoning.py",
        SOURCE_ROOT / "adapters" / "models" / "deterministic.py",
        SOURCE_ROOT / "adapters" / "models" / "structured" / "reasoning_stages.py",
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
            "evidence",
            "history",
            "question",
            "knowledge",
            "investigator",
        ], path

    structured = SOURCE_ROOT / "adapters" / "models" / "structured"
    assert structured.is_dir(), "the structured package is gone; this guard sweeps nothing"
    imported = {
        node.module or ""
        for path in structured.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    # A model adapter that could reach the application could choose its own evidence.
    assert not any(name.startswith("archcompass.application") for name in imported)

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
