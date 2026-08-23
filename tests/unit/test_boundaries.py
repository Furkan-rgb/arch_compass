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

    # Asked of Python source, not of the directory. A checkout that has ever run the old
    # tree keeps `adapters/__pycache__/` and `application/__pycache__/` on disk for ever —
    # `.pyc` files are gitignored, so nothing removes them and `git status` stays clean —
    # and this test spent a while failing on every such machine over bytecode for modules
    # that no longer exist. What the rule is about is where a module lives.
    for stale in ("adapters", "application", "boundary"):
        revived = sorted((SOURCE_ROOT / stale).rglob("*.py"))
        assert not revived, (
            f"{stale}/ is back; the tree is navigated by feature, not by layer. "
            f"Found {[str(path.relative_to(SOURCE_ROOT)) for path in revived]}"
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
        "google",
        "ollama",
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


def test_ports_are_stated_in_domain_terms_alone() -> None:
    """What is left at top level is the seams the review graph is sequenced out of.

    `ports/` used to hold thirteen modules, six of which named a feature's own record types
    — an interface hoisted one directory up, kept legal by an allowlist. Those moved beside
    what they belong to (`analysis/ports.py`, `policies/ports.py`, `reasoning/ports.py`,
    `repositories/ports.py`, `persistence/ports.py`), so the allowlist is gone and this
    guard is the stronger one it could not be before: nothing here may name a feature at
    all, records included.
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
    # Relative path rather than name: `{path.name for ...}` over an `rglob` is dodged by a
    # subpackage, because `ports/extra/capabilities.py` contributes a name already in the set.
    assert {path.relative_to(root).as_posix() for path in _python_files(root)} == {
        "__init__.py",
        "capabilities.py",
        "policy_retrieval.py",
    }, "a module has appeared in ports/; is it a graph seam, or a feature's own contract?"
    for path in _python_files(root):
        offending = [
            imported
            for imported in _imports(path)
            if any(_crosses(imported, prefix) for prefix in forbidden)
        ]
        assert not offending, (
            f"{path.relative_to(SOURCE_ROOT)} imports {offending[0]}; a graph seam is "
            "stated in domain terms, and a contract that needs a feature's own records "
            f"belongs in that feature's ports.py"
        )


#: What a module may import and still be somewhere a contract can be stated in: the standard
#: library, Pydantic, and the three shared vocabularies. Anything else makes it behaviour.
_RECORD_VOCABULARY = (
    "archcompass.records",
    "archcompass.domain",
    "archcompass.configuration",
)


def _is_record_module(module: str) -> bool:
    """Whether `module` is a file of frozen records rather than something that does work.

    Asked structurally rather than answered by a list. `_FEATURE_RECORD_MODULES` used to name
    the five that `ports/` was allowed to reach for, which meant the rule was maintained by
    hand and said nothing about the sixth. This asks the modules themselves: a record module
    imports the standard library, Pydantic and the shared vocabularies, and nothing that
    could hold behaviour.
    """

    path = SOURCE_ROOT.parent / (module.replace(".", "/") + ".py")
    if not path.is_file():
        return False
    return all(
        not _crosses(imported, "archcompass")
        or any(_crosses(imported, allowed) for allowed in _RECORD_VOCABULARY)
        for imported in _imports(path)
    )


def test_a_features_ports_name_records_and_never_behaviour() -> None:
    """A contract may be stated in another feature's record types. Not in its work.

    When these lived in `ports/`, an allowlist of five module names is what let them name
    `analysis.atlas` and `repositories.lineage`; moving them beside their features took the
    allowlist away and, on its own, would have taken the rule with it — `persistence/ports.py`
    naming `archcompass.reasoning.conversation` would then have been nobody's business.

    The rule is asked of the imported module instead of of a list: it has to be a file of
    records itself. That is stricter than the allowlist was, because the allowlist could not
    notice one of its five growing a service, and it needs no maintenance.
    """

    for feature in FEATURES:
        path = SOURCE_ROOT / feature / "ports.py"
        if not path.is_file():
            continue
        offending = [
            imported
            for imported in _imports(path)
            if _crosses(imported, "archcompass")
            and not any(_crosses(imported, allowed) for allowed in _RECORD_VOCABULARY)
            and not _is_record_module(imported)
        ]
        assert not offending, (
            f"{path.relative_to(SOURCE_ROOT)} imports {offending[0]}, which holds behaviour "
            "rather than records; a contract cannot be stated in terms of what answers it"
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

    # The other half of the rule: a route may ask a *service* for something and may not
    # reach the store behind it. Written as names, and the names rotted — four of the eight
    # this list used to hold (`case_repository`, `job_repository`, `report_writer`,
    # `run_repository`) had not been `Runtime` fields for some time, while
    # `core_review_repository`, which a route does reach, was never on it. A guard that is
    # half ghosts reads as protection and provides none.
    #
    # So every name is now checked against `Runtime` itself before it is enforced. A field
    # that is renamed or removed fails this test rather than quietly stopping being guarded.
    from archcompass.bootstrap import Runtime

    runtime_fields = {field.name for field in dataclasses.fields(Runtime)}
    forbidden_runtime_attributes = {
        "analyzer",
        "atlas_repository",
        "core_review_repository",
        "database",
        "query_service",
    }
    unknown = forbidden_runtime_attributes - runtime_fields
    assert not unknown, (
        f"this guard names {sorted(unknown)}, which are not Runtime fields; either the "
        "field was renamed and the guard did not follow, or the entry is a ghost"
    )
    used_attributes: set[str] = set()
    for path in _python_files(routes_root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used_attributes |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    reached = used_attributes & forbidden_runtime_attributes
    assert not reached, (
        f"a route reaches {sorted(reached)} directly; ask the service that owns it"
    )
    assert {
        "atlas_service",
        "case_service",
        "policy_service",
        "repository_service",
    } <= used_attributes


def test_reasoning_adapters_do_not_import_the_services_above_them() -> None:
    """Adapters own transport and schema constraint, never application policy.

    `docs/architecture.md` puts provider SDKs in two adapter packages and has every feature
    reach the outside world through its own `ports.py`. This pins the import direction that
    makes that enforceable rather than aspirational: an adapter may know its port and the
    domain, and may not know the service that calls it.
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


#: Field names that would put a model's finger on a place in a list the application built.
#:
#: The plain nouns are here as well as the suffixed ones: `positions` was the field that
#: broke, and a rename to `index` would satisfy a suffix-only sweep while changing nothing.
_ORDINAL_NAMES = ("position", "positions", "index", "indexes", "indices", "ordinal")


def _output_schema_fields(path: Path) -> list[tuple[str, str]]:
    """Every annotated field on every Pydantic model in one file, as (class, field)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    fields: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(
            isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases
        ):
            continue
        fields.extend(
            (node.name, statement.target.id)
            for statement in node.body
            if isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
        )
    return fields


def test_no_model_output_schema_asks_for_a_place_in_one_of_our_lists() -> None:
    """A model may name what the application holds. It may never index into it.

    This is the rule in `docs/charter.md`, and it is here because the failure it prevents is
    invisible until a review dies. A judgement listed its policies `[1] [2] [3]` and took an
    ordinal back; a clarification round listed every finding the same way, told the model in
    prose which numbers were forbidden, and raised when it used one — losing a review that
    had already judged every candidate.

    Both halves of the damage come from the same property. An ordinal out of range is fatal,
    and an ordinal in range but wrong resolves to the wrong policy and is recorded for ever
    as a correct citation. A name has neither reading: it matches something the application
    holds or it visibly matches nothing, and matching nothing can be dropped.

    Two ways to satisfy it. Where one call handles one thing, do not ask at all — the
    identity is the call, as `LangChainQuestionGenerator` now does with one question per held
    finding. Where one call spans many, as a conversation citing several findings does, ask
    for the identifier and drop the ones you do not recognise.
    """

    root = SOURCE_ROOT / "reasoning"
    assert root.is_dir(), "reasoning/ is gone; this guard sweeps nothing"

    schemas = [
        (path, name, field)
        for path in _python_files(root)
        for name, field in _output_schema_fields(path)
    ]
    assert schemas, "no model output schemas were found; this guard sweeps nothing"

    offenders = [
        f"{path.relative_to(SOURCE_ROOT)}: {name}.{field}"
        for path, name, field in schemas
        if field in _ORDINAL_NAMES or field.rsplit("_", 1)[-1] in _ORDINAL_NAMES
    ]
    assert not offenders, (
        "a model is being asked for a place in a list the application built: "
        + str(sorted(offenders))
        + " — ask for the identifier instead, or fan the call out so there is nothing to point at"
    )
