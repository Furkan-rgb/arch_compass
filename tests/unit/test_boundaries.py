from __future__ import annotations

import ast
import dataclasses
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from archcompass.bootstrap import CHECKPOINT_RECORD_TYPES
from archcompass.workflow.state import ReviewState

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "archcompass"

#: The feature packages the tree is navigated by. Each one is asserted to exist wherever it
#: is swept, because `rglob` over a directory that does not exist yields nothing and passes:
#: a guard named after a package can outlive the package and go on reporting success over no
#: files at all. That happened once — `workflows/` was deleted and a guard kept naming it for
#: months — and it is why every sweep below starts with `is_dir()`.
FEATURES = (
    "analysis",
    "policies",
    "reasoning",
    "repositories",
    "workflow",
    "persistence",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _crosses(imported: str, prefix: str) -> bool:
    return imported == prefix or imported.startswith(f"{prefix}.")


def test_the_layer_named_packages_are_gone() -> None:
    """Nothing may reappear beside the feature tree under its old technical-layer name.

    The refactor's whole point is that there is one place to look for a thing. A revived
    `adapters/` or `application/` would not be wrong so much as it would be a second answer
    to "where does this live", which is the failure the tree was reorganised to remove.
    """

    for stale in ("adapters", "application", "boundary"):
        assert not (SOURCE_ROOT / stale).exists(), (
            f"{stale}/ is back; the tree is navigated by feature, not by layer"
        )
    for feature in FEATURES:
        assert (SOURCE_ROOT / feature).is_dir(), f"{feature}/ is gone"


def test_domain_imports_only_the_standard_library_and_itself() -> None:
    """`domain/` is frozen dataclasses and nothing else — no vendor, no feature, no I/O.

    The forbidden list is every feature package plus the libraries a domain record must
    never carry. LangGraph checkpoints serialize these classes by module path, so a domain
    module that grew a Pydantic or SQLite dependency would also be one that a stored
    checkpoint can no longer be read back into.
    """

    forbidden = (
        "pydantic",
        "langchain",
        "langgraph",
        "fastapi",
        "sqlite3",
        "httpx",
        "typer",
        "archcompass.records",
        "archcompass.ports",
        "archcompass.presentation",
        *[f"archcompass.{feature}" for feature in FEATURES],
    )
    root = SOURCE_ROOT / "domain"
    assert root.is_dir(), "domain/ is gone; this guard now sweeps nothing"
    for path in _python_files(root):
        imports = _imports(path)
        assert not any(
            _crosses(imported, prefix) for imported in imports for prefix in forbidden
        ), f"{path.relative_to(SOURCE_ROOT)} crosses the domain boundary"


#: The only modules inside a feature that a port may name. Each is a file of frozen Pydantic
#: records and nothing else — no I/O, no vendor, no service — so a contract stated in their
#: terms still points inward. Anything else in a feature is behaviour, and a port that
#: imported it would be the arrow the ports exist to reverse.
_FEATURE_RECORD_MODULES = frozenset(
    {
        "archcompass.analysis.atlas",
        "archcompass.policies.records",
        "archcompass.reasoning.records",
        "archcompass.repositories.lineage",
        "archcompass.repositories.records",
    }
)


def test_ports_declare_contracts_without_reaching_for_implementations() -> None:
    """A port names what is asked for. It may not know who answers.

    `ports/` may reference `domain/`, `records.py`, and the record modules named above,
    because a contract is stated in those terms. Importing a feature's service or adapter
    would invert the arrow the ports exist to create.
    """

    forbidden = (
        "sqlite3",
        "httpx",
        "typer",
        "langgraph",
        "fastapi",
        "archcompass.presentation",
        *[f"archcompass.{feature}" for feature in FEATURES],
    )
    root = SOURCE_ROOT / "ports"
    assert root.is_dir(), "ports/ is gone; this guard now sweeps nothing"
    for path in _python_files(root):
        offending = [
            imported
            for imported in _imports(path)
            if imported not in _FEATURE_RECORD_MODULES
            and any(_crosses(imported, prefix) for prefix in forbidden)
        ]
        assert not offending, (
            f"{path.relative_to(SOURCE_ROOT)} imports {offending[0]}, which is behaviour "
            "rather than a record its contract can be stated in"
        )


def test_feature_logic_does_not_import_another_features_adapters() -> None:
    """Concrete infrastructure stays inside the `adapters/` of the feature that owns it.

    Every feature keeps its vendor code in one subpackage, and the modules above it are
    reached through ports. The exception is `<feature>/adapters/` itself, which is where
    the vendor is allowed to be named, and `bootstrap.py`, which is the composition root
    and the one module whose job is to choose implementations.
    """

    forbidden = [f"archcompass.{feature}.adapters" for feature in FEATURES]
    for feature in FEATURES:
        root = SOURCE_ROOT / feature
        for path in _python_files(root):
            if "adapters" in path.relative_to(root).parts:
                continue
            imports = _imports(path)
            offending = [
                imported
                for imported in imports
                for prefix in forbidden
                if _crosses(imported, prefix)
            ]
            assert not offending, (
                f"{path.relative_to(SOURCE_ROOT)} imports {offending[0]}, which is "
                "infrastructure it should reach through a port"
            )


def test_langgraph_is_confined_to_the_workflow_package() -> None:
    """The orchestration library is an implementation detail of one package.

    A review is sequenced by LangGraph and nothing else in the product may know that.
    `bootstrap.py` is exempt because it builds the checkpointer the graph is compiled with.
    """

    allowed = {SOURCE_ROOT / "bootstrap.py"}
    for path in _python_files(SOURCE_ROOT):
        if path in allowed or path.relative_to(SOURCE_ROOT).parts[0] == "workflow":
            continue
        assert not any(_crosses(imported, "langgraph") for imported in _imports(path)), (
            f"{path.relative_to(SOURCE_ROOT)} imports LangGraph outside workflow/"
        )


def test_langchain_and_provider_sdks_stay_in_reasoning_and_policy_adapters() -> None:
    """The model vendors are named in two places, both of them adapter packages.

    `langchain_core` is deliberately absent from the list: it is LangGraph's own package,
    and `workflow/service.py` types the graph's config with `RunnableConfig` from it. That
    is the orchestration library, already confined by the guard above, not a provider SDK.
    """

    vendors = ("langchain", "langchain_google_genai", "google", "ollama")
    allowed_roots = (
        SOURCE_ROOT / "reasoning" / "adapters",
        SOURCE_ROOT / "policies" / "adapters",
    )
    for path in _python_files(SOURCE_ROOT):
        if any(path.is_relative_to(root) for root in allowed_roots):
            continue
        offending = [
            imported
            for imported in _imports(path)
            for vendor in vendors
            if _crosses(imported, vendor)
        ]
        assert not offending, (
            f"{path.relative_to(SOURCE_ROOT)} imports {offending[0]}; provider SDKs "
            "belong in reasoning/adapters or policies/adapters"
        )


def test_cli_commands_use_application_services_only() -> None:
    path = SOURCE_ROOT / "presentation" / "cli" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = [f"archcompass.{feature}.adapters" for feature in FEATURES]
    assert not any(
        _crosses(imported, prefix) for imported in _imports(path) for prefix in forbidden
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
    used_attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
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
        "case_rescope": "case_service",
        "case_history": "case_service",
        "review": "review_workflow_service",
        "review_show": "review_workflow_service",
        "review_list": "review_workflow_service",
        "review_ask": "review_conversation_service",
        "review_history": "review_conversation_service",
    }
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for command, service in expected_service_by_command.items():
        attributes = {
            node.attr for node in ast.walk(functions[command]) if isinstance(node, ast.Attribute)
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

    forbidden = [f"archcompass.{feature}.adapters" for feature in FEATURES]
    swept = [path for path in _python_files(web_root) if path.name not in _WEB_RUNTIME_BUILDERS]
    assert swept, "the web package is gone; this guard now sweeps nothing"
    for path in swept:
        assert not any(
            _crosses(imported, prefix) for imported in _imports(path) for prefix in forbidden
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
    for path in _python_files(routes_root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used_attributes |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert used_attributes.isdisjoint(forbidden_runtime_attributes)
    assert {
        "atlas_service",
        "case_service",
        "policy_service",
        "repository_service",
    } <= used_attributes


def test_reasoning_adapters_do_not_import_the_services_above_them() -> None:
    """Adapters own transport and schema constraint, never application policy.

    `docs/architecture.md` states that model adapters "do not choose evidence, history,
    citation, or truncation rules". This pins the import direction that makes the statement
    enforceable rather than aspirational: an adapter may know its port and the domain, and
    may not know the service that calls it.
    """

    root = SOURCE_ROOT / "reasoning" / "adapters"
    assert root.is_dir(), "reasoning/adapters is gone; this guard now sweeps nothing"
    service_modules = {
        "archcompass.reasoning.model_catalog",
        "archcompass.reasoning.embedding_models",
        "archcompass.reasoning.conversation",
        "archcompass.reasoning.cache",
        "archcompass.workflow",
    }
    for path in _python_files(root):
        imports = _imports(path)
        assert not any(
            _crosses(imported, prefix) for imported in imports for prefix in service_modules
        ), f"{path.relative_to(SOURCE_ROOT)} imports the service layer above it"


def _checkpointed_records(annotation: object, seen: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Every record type reachable from one `ReviewState` field, named as msgpack names it.

    Recursive because the allowlist is: a checkpoint stores a `Review`, a `Review` holds
    `Finding`s, a `Finding` holds a `Verdict`, and every one of those has to appear by name.
    """

    origin = get_origin(annotation)
    if origin is not None:
        for argument in get_args(annotation):
            _checkpointed_records(argument, seen)
        return seen
    if not isinstance(annotation, type):
        return seen
    if not (dataclasses.is_dataclass(annotation) or issubclass(annotation, Enum)):
        return seen
    name = (annotation.__module__, annotation.__qualname__)
    if name in seen:
        return seen
    seen.add(name)
    if dataclasses.is_dataclass(annotation):
        hints = get_type_hints(annotation)
        for field in dataclasses.fields(annotation):
            _checkpointed_records(hints[field.name], seen)
    return seen


def test_every_record_a_checkpoint_can_hold_is_named_in_the_allowlist() -> None:
    """The one boundary a unit test cannot reach by running the graph.

    A resumed review is deserialized by `JsonPlusSerializer`, which revives an unlisted
    dataclass as a raw dict instead of refusing it — so the omission shows up much later, as
    an attribute error in a node that has nothing to do with the type that was dropped, and
    only ever against the real SQLite checkpointer. Every workflow test compiles the graph
    with `InMemorySaver`, which does not consult the allowlist at all, so nothing in the
    suite touches it. This walks the state instead: whatever `ReviewState` can hold today is
    what the list has to name.

    Both directions, because a name that no longer matches a type is not harmless — it reads
    as coverage while covering nothing, which is exactly how the gap it replaces was missed.
    """

    reachable: set[tuple[str, str]] = set()
    for annotation in get_type_hints(ReviewState, include_extras=False).values():
        _checkpointed_records(annotation, reachable)

    listed = set(CHECKPOINT_RECORD_TYPES)
    assert reachable, "no records were found in ReviewState; this guard sweeps nothing"
    assert not reachable - listed, "a resumed review would revive these as dicts: " + str(
        sorted(reachable - listed)
    )
    assert not listed - reachable, "these are allowlisted but no longer reachable: " + str(
        sorted(listed - reachable)
    )
