from __future__ import annotations

import ast
import dataclasses
import re
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from archcompass.bootstrap import CHECKPOINT_RECORD_TYPES
from archcompass.persistence.ports import ScopeSelectionRepository
from archcompass.reasoning.adapters.providers import DETERMINISTIC_DESCRIPTOR
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

    `deepagents` is on the list. It is an agent harness rather than a provider, but it is the
    same kind of thing as `langchain` — a vendor whose types would otherwise spread through
    the packages that are supposed to be stated in our own terms. Only the filesystem
    middleware and its backend protocol are used, and both are adapted in one file.
    """

    vendors = ("langchain", "google", "ollama", "openai", "deepagents")
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


def test_every_key_a_candidate_branch_writes_leaves_it() -> None:
    """A key the branch writes and its output schema omits is dropped without a word.

    `investigations` was, and nothing failed: the review composed with an empty manifest
    while every finding carried the identity of a trace nothing had stored. A `Send` branch
    returns through `CandidateReviewOutput`, so anything not named there is written inside
    the branch and discarded at its edge.

    Read off the node's own source rather than by running it, so this covers the keys a
    branch writes on paths a unit test does not take.
    """

    from typing import get_type_hints

    from archcompass.workflow.state import CandidateReviewOutput

    source = (SOURCE_ROOT / "workflow" / "nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    judge = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "judge_candidate"
    )
    written = {
        key.value
        for statement in ast.walk(judge)
        if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Dict)
        for key in statement.value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }

    assert written, "no returned keys were found; this guard sweeps nothing"
    declared = set(get_type_hints(CandidateReviewOutput))
    assert written <= declared, (
        f"judge_candidate writes {sorted(written - declared)}, which "
        "CandidateReviewOutput does not declare — a Send branch drops those silently"
    )


#: Where the stand-in provider is allowed to be named, and where it is allowed to be
#: recognised. Two files, because those are two different acts: `providers.py` registers the
#: descriptor that gives the provider its name, and `SelectedLangChainJudge.selection` is the
#: single reading of the model selection that everything else in the product is handed.
_STAND_IN_DEFINITION = "reasoning/adapters/providers.py"
_STAND_IN_DECISION = ("reasoning/adapters/selected.py", "selection")

#: How the stand-in's name is read where reading it is legitimate. `providers.py` is allowed
#: the literal by the sibling test, so both spellings have to be swept; a comparison written
#: inside that file would be as much a second decision as one written anywhere else.
_STAND_IN_READ = "DETERMINISTIC_DESCRIPTOR.name"

#: The identifier the descriptor itself is bound to, split out of `_STAND_IN_READ` so that
#: the two sweeps below cannot drift into naming different things. What the second of them
#: looks for is the object rather than the string it carries: holding the descriptor is what
#: puts the name within reach, and no second recognition can be written without holding it.
_STAND_IN_DESCRIPTOR = _STAND_IN_READ.split(".")[0]

#: Every place in `src/` that may name the descriptor, as (file, enclosing function). Four,
#: because four different acts need it and no fifth does: `providers.py` builds it,
#: `bootstrap` lists it among the providers this build can reach, `deterministic.py` derives
#: from its name the stamp that every finding, synopsis and answer carries, and `selection`
#: recognises the selection. An import is not on this list because an import is not a use: it
#: binds a name, and `ast` records that on an `alias` node rather than on a `Name`.
_STAND_IN_DESCRIPTOR_SITES = (
    ("bootstrap.py", "<module>"),
    ("reasoning/adapters/deterministic.py", "<module>"),
    ("reasoning/adapters/providers.py", "<module>"),
    _STAND_IN_DECISION,
)

#: The stand-in's model name, rationed the same way and for the same reason. Rationing the
#: descriptor closed every spelling that reaches the stand-in through its *provider*, and left
#: a door beside it: `model == DETERMINISTIC_MODEL` recognises exactly the same selection,
#: holds no descriptor, writes no literal, and passed the whole sweep. The two names are the
#: two halves of `DETERMINISTIC_MODEL_IDENTITY` and they sit in the same file, so guarding one
#: and not the other was arbitrary rather than principled.
#:
#: Three sites, one fewer than the descriptor's, because nothing recognises a selection by its
#: model: `providers.py` defines it and offers it as the one model this provider has, and
#: `deterministic.py` builds the stamp out of it. `selection` is deliberately absent — the
#: decision is the provider's, and a fifth place that wanted to make it by model would have to
#: add itself here in the same commit, which is the review this exists to force.
_STAND_IN_MODEL_SITES = (
    ("reasoning/adapters/deterministic.py", "<module>"),
    ("reasoning/adapters/providers.py", "<module>"),
    ("reasoning/adapters/providers.py", "probe_deterministic"),
)

#: What may be held, and by whom. A mapping rather than two tests, so that a third name worth
#: rationing is a row here instead of a copy of the sweep — the shape this whole guard exists
#: to refuse.
_STAND_IN_HOLDINGS = {
    _STAND_IN_DESCRIPTOR: _STAND_IN_DESCRIPTOR_SITES,
    "DETERMINISTIC_MODEL": _STAND_IN_MODEL_SITES,
}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """The string constants that are documentation, by `id()`, so a sweep can skip them.

    Prose about a rule is not a copy of the rule, and the modules that own this one explain
    it at length — `deterministic.py` opens by quoting the very branch it replaced. A sweep
    that could not tell those apart from source would be a sweep somebody deletes.
    """

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _enclosing_function_names(tree: ast.AST) -> dict[int, str]:
    """Which function each node is written inside, by `id()`, innermost winning.

    `ast.walk` is breadth-first, so an outer function is visited before the functions nested
    in it and the inner name overwrites the outer one — which is the attribution a reader
    would give: a closure defined in `bootstrap.build_runtime` is its own place to forget a
    rule, not `build_runtime`'s.
    """

    holder: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for child in ast.walk(node):
                holder[id(child)] = node.name
    return holder


def _stand_in_spellings(tree: ast.AST, literal: str) -> set[str]:
    """Every word in this module that means the stand-in's name, including the copies of it.

    The sweep below used to read only the two sides of one `ast.Compare` as they were
    written, and that is not enough to make the claim it makes. Lift the field into a local
    first — which is how anybody writes a null check — and the comparison names a variable
    instead of the descriptor::

        _name = None if _cfg is None else _cfg.provider
        if _name == DETERMINISTIC_DESCRIPTOR.name:

    That is a second recognition of the stand-in, and both of these tests passed with it
    sitting in `src/`. So does a helper that takes the provider as a plain string rather than
    the selection — near enough to the `_is_deterministic` this rule was written about to be
    the same mistake, though that one took the selection and was caught. Two natural
    spellings, and the comment beside `selection` claimed both would fail.

    It is caught now because the sweep no longer asks anything about the left-hand
    side; the mirror image of it, where the descriptor is the half lifted into a local, is
    what this function is for::

        _stand_in = DETERMINISTIC_DESCRIPTOR.name
        if _cfg.provider == _stand_in:

    Only an exact rebinding is followed — a name assigned nothing but a spelling already
    known to mean the stand-in, standing alone or as one element of a tuple — and the pass
    repeats until no new name is bound, so a chain of copies is followed too. A value
    *derived* from the name is deliberately left alone:
    `DETERMINISTIC_MODEL_IDENTITY` is built out of it by an f-string and means "this model",
    which is a different question from "this provider". Nothing in `src/` compares against it
    today — it is stamped, never tested — and a comparison that did appear would be asking
    what produced a stored finding rather than what is selected now. That is a neighbouring
    decision with its own single owner, and this sweep does not claim to cover it.

    Names are collected for the whole module rather than per function, because a module-level
    constant read inside three functions is exactly the second place to forget a rule that
    this test exists to refuse, and a per-function view would not see it.

    The chase stops there, and stopping is the point. A copy made by a call, by an f-string or
    by a parameter default is not followed, and there is no dataflow analysis in this file.
    There does not need to be: the sweep two tests below rations the descriptor itself, so a
    copy of its name can only be made in one of the four places allowed to hold it. Three of
    those four are module scopes, which is the whole of what is left to this function, and an
    exact rebinding is what a person writes there.
    """

    spellings = {_STAND_IN_READ, literal}
    while True:
        grown = set(spellings)
        for node in ast.walk(tree):
            targets: list[ast.expr]
            value: ast.expr | None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign | ast.NamedExpr):
                targets, value = [node.target], node.value
            else:
                continue
            if value is None:
                continue
            # `_STAND_IN, _RETRIES = DETERMINISTIC_DESCRIPTOR.name, 3` binds the name as
            # surely as a statement of its own, and it is the one multiple-binding form
            # people actually write. Taken element by element, because unparsing the whole
            # right-hand side of it yields a tuple, which is a spelling of nothing.
            if (
                len(targets) == 1
                and isinstance(targets[0], ast.Tuple)
                and isinstance(value, ast.Tuple)
                and len(targets[0].elts) == len(value.elts)
            ):
                grown.update(
                    target.id
                    for target, element in zip(targets[0].elts, value.elts, strict=True)
                    if isinstance(target, ast.Name) and ast.unparse(element) in grown
                )
                continue
            if ast.unparse(value) not in grown:
                continue
            grown.update(target.id for target in targets if isinstance(target, ast.Name))
        if grown == spellings:
            return spellings
        spellings = grown


def test_the_stand_in_provider_is_written_out_in_exactly_one_place() -> None:
    """The name `fake` exists once in the source: on the descriptor that registers it.

    This is the rule the migration checksum established, applied to a provider name. Where
    two things must name one value, do not write the name twice — and this name had been
    written four times: the descriptor, two `provider == "fake"` tests in `selected.py`, and
    the `f"fake:{model}"` the stand-in stamps every finding, synopsis and answer with.

    A copy of it is not a loud failure. `DETERMINISTIC_MODEL_IDENTITY` is compared against
    what a stored finding carries, so a rename that moved the descriptor and left the stamp
    behind would make the delta report a moved model for every candidate of every review —
    which is the defect this whole line of work exists to close, arriving by a different
    door. Every other reader asks `DETERMINISTIC_DESCRIPTOR.name`, so a rename is one edit.

    The name is looked for as a word inside every string the module actually evaluates, not
    only as a whole one, because the copy that mattered was a prefix: `f"fake:{model}"` holds
    the provider name and is equal to nothing. Docstrings are skipped and comments are not
    string constants at all, so the prose that explains this rule does not trip it.
    """

    name = DETERMINISTIC_DESCRIPTOR.name
    spelled = re.compile(rf"\b{re.escape(name)}\b")
    written = []
    for path in _python_files(SOURCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        documentation = _docstring_nodes(tree)
        written.extend(
            path.relative_to(SOURCE_ROOT).as_posix()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in documentation
            and spelled.search(node.value)
        )
    assert written == [_STAND_IN_DEFINITION], (
        f"the stand-in provider is written out as {name!r} in {sorted(written)}; it may be "
        f"spelled only in {_STAND_IN_DEFINITION}, and read everywhere else off "
        "DETERMINISTIC_DESCRIPTOR.name"
    )


def test_only_the_judge_selection_decides_that_the_stand_in_is_selected() -> None:
    """One place asks whether the selection is the stand-in. Everything else asks that place.

    The failure this guards is not hypothetical and it is not the first of its kind. Three
    capabilities in `selected.py` shared a `_is_deterministic` helper whose body was, word for
    word, the expression inside `selection` — sitting under a comment claiming the rule lived
    in one place. Before that, `bootstrap` mapped the same provider to the stand-in's model
    identity while the stand-in stamped it from `deterministic.py`, and a third callback read
    the selection again for the retriever. Two of those derived the same fact differently and
    a verdict swung `cleared → material → cleared → material` across four revisions of one
    unchanged commit, because the delta compared a stamp against a value nothing stamped.

    Each fix made both sides read one value; each held until a code path arrived that did not
    read it. So this is asked of the source rather than of behaviour — and it has to be, since
    a re-spelled copy of the rule agrees with the original on every input a test could pass
    it. What it cannot agree with is the next edit to one of them.

    What is swept is any comparison, anywhere in `src/`, in which the stand-in's name appears
    at all — the literal, `DETERMINISTIC_DESCRIPTOR.name`, or a local or module name copied
    from either by `_stand_in_spellings`. Nothing is asked about the other side of it. That
    is both stronger and shorter than asking for the provider field and the name on the two
    sides of one `ast.Compare`, which is what this test did until it was falsified: lifting
    the field into a local first walked straight past it, and this docstring claimed
    otherwise. There is no honest reason to compare against this name and not be deciding
    that the stand-in is selected, so the pair of conditions bought nothing but the hole.

    This is not the outer wall any more, and it should not be read as one. The test below
    refuses the descriptor itself to every file but four, so a comparison has to be written
    inside one of those four to reach this sweep at all. It is kept because three of the four
    are module scopes that the sweep below cannot help but allow, and a copy made there and
    compared inside a method of the same module is caught here and nowhere else.
    """

    literal = repr(DETERMINISTIC_DESCRIPTOR.name)
    deciders: list[tuple[str, str]] = []
    for path in _python_files(SOURCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        holder = _enclosing_function_names(tree)
        spellings = _stand_in_spellings(tree, literal)
        # The literal carries its own quotes and cannot take a `\b` on the left, so it stays
        # a substring test; every other spelling is a bare name or an attribute read, where
        # the boundary is what stops `_name` from matching inside `_name_of_the_model`.
        named = re.compile(
            "|".join(rf"\b{re.escape(word)}\b" for word in sorted(spellings - {literal}))
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            sides = [ast.unparse(node.left), *map(ast.unparse, node.comparators)]
            if any(literal in side or named.search(side) for side in sides):
                deciders.append(
                    (
                        path.relative_to(SOURCE_ROOT).as_posix(),
                        holder.get(id(node), "<module>"),
                    )
                )

    assert deciders == [_STAND_IN_DECISION], (
        f"the stand-in is recognised in {sorted(deciders)}; exactly one place may compare "
        f"anything against its name — {_STAND_IN_DECISION[0]}:{_STAND_IN_DECISION[1]} — and "
        "every other caller reads `selection().deterministic` off the record it returns"
    )


def _descriptor_bindings(tree: ast.AST, held: str) -> set[str]:
    """What this module calls the rationed name, including under an `as` name.

    Read off the module's own imports rather than assumed, so the sweep follows the file's
    vocabulary instead of one spelling of it: `import ... as _stand_in` is a rename, and a
    guard that only knew the canonical name would report success over the file that used it.
    """

    bound = {held}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            bound.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == held
            )
    return bound


def test_four_places_hold_the_stand_in_descriptor_and_nothing_else_may() -> None:
    """Holding the descriptor is what this refuses, not comparing against the name it carries.

    The sibling above asks about comparisons, and asking about comparisons is a chase. It was
    strengthened once to follow the name into a local, and three spellings still walked past
    it — each of them a real file that this module passed in full. The name unpacked out of a
    tuple, `_STAND_IN, _RETRIES = DETERMINISTIC_DESCRIPTOR.name, 3`. The name copied
    through a call, `_STAND_IN = str(DETERMINISTIC_DESCRIPTOR.name)`. The name handed in as a
    parameter default, `def probe(configuration, stand_in=DETERMINISTIC_DESCRIPTOR.name)`.
    The third is not the exotic one: passing a collaborator in as a parameter is how
    `bootstrap` hands `selection` to its readers, so it is the likeliest next spelling rather
    than the least.

    Following each of them costs dataflow analysis in a test file, and what it would buy is a
    list of the forms somebody has thought of. So the question is asked one step earlier: to
    decide anything about the stand-in you must first be holding the descriptor, and it is the
    descriptor that is rationed here. All three spellings fail this test, and so do three that
    a sweep of comparisons cannot see at all — a dict keyed by the provider name, a
    `startswith`, a `match` — because none of those can be written without the descriptor
    either. The rule does not care what a fifth place would do with it, which is exactly why
    it does not have to know.

    The inverse was considered and rejected: sweep every comparison against a `.provider` and
    allow-list the one legitimate site. `src/` compares a provider in nineteen places across
    six files — `factory` routing to a transport, the catalogue matching a stored selection,
    the embedding default — and eighteen of them are honest. An eighteen-entry allow-list is
    not a guard, it is a form to fill in, and the path that should have been refused is added
    to it in the same commit that writes it.

    What this does not reach, and does not claim to. A value *derived* from the name rather
    than the name itself: `DETERMINISTIC_MODEL_IDENTITY` is built in `deterministic.py` out of
    it, and a reader testing a stored `model_identity` against that constant would be asking
    what produced a finding rather than what is selected now — a neighbouring decision with
    its own owner, declined here for the reason `_stand_in_spellings` declines it. Nor does either
    sweep see a second recognition written inside `selection`, the one function both of them
    allow, or a name reached by `getattr` rather than written.
    """

    for rationed, allowed in _STAND_IN_HOLDINGS.items():
        holders: list[tuple[str, str]] = []
        for path in _python_files(SOURCE_ROOT):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            holder = _enclosing_function_names(tree)
            bound = _descriptor_bindings(tree, rationed)
            for node in ast.walk(tree):
                # Both halves of how a module reaches it: the bare name an import bound, and
                # the attribute read of a module imported whole. Neither matches an `alias`,
                # so the import that makes the name available is not counted as a use of it.
                reached = (isinstance(node, ast.Name) and node.id in bound) or (
                    isinstance(node, ast.Attribute) and node.attr == rationed
                )
                if not reached:
                    continue
                holders.append(
                    (
                        path.relative_to(SOURCE_ROOT).as_posix(),
                        holder.get(id(node), "<module>"),
                    )
                )

        assert sorted(set(holders)) == sorted(allowed), (
            f"`{rationed}` is held in {sorted(set(holders))}; only {sorted(allowed)} may "
            "name it, and anything else that needs to know whether the stand-in is selected "
            "reads `selection().deterministic`"
        )


#: The modules holding a `ScopeSelectionRepository` today, by path under `src/archcompass`.
#: The sweep below allows a new one and checks its key like every other, but it refuses to
#: run with fewer than these. A guard whose subject has been renamed out from under it
#: sweeps nothing and reports success — the failure every other sweep in this file opens
#: with `is_dir()` to avoid.
_SCOPE_SELECTION_READERS = frozenset(
    {
        "analysis/analyzer.py",
        "analysis/freshness.py",
        "repositories/service.py",
    }
)

#: A receiver named `scope_selections`, however it is reached: `self._scope_selections`,
#: `scope_selections`, `self.scope_selections`. The port is never held under another name in
#: this tree, and holding it under one would be the edit that hides a call site from here.
_SCOPE_SELECTION_HOLDER = re.compile(r"(^|\.)_?scope_selections$")

#: Read off the protocol rather than written out here, so a method renamed on the port, or a
#: third one added to it, is swept without anybody remembering to come back. Naming them in
#: this file would be the same mistake the sweep exists to forbid, one level up.
_SCOPE_SELECTION_METHODS = frozenset(
    name
    for name, value in vars(ScopeSelectionRepository).items()
    if not name.startswith("_") and callable(value)
)

#: The ways a caller may obtain the key, and none of them build it. `ASKED` is the question
#: put to the analyzer, which is the object that decides the answer. `CARRIED` is a plain
#: attribute chain ending in the answer it already gave — `version.root_path`,
#: `summary.root_path`, `repository.canonical_root` — read whole off a record written from
#: it. `ABSENT` is the empty string, which a web route holds where there is no repository to
#: name; it is admitted because it is a miss by construction rather than a miss by
#: misspelling, since the only writer of this table records `version.root_path` and the
#: analyzer will not return an empty root for one. What none of the three can express is an
#: expression that assembles the string, so a `Path`, a `str()`, an `expanduser()`, a
#: `resolve()` or a `/` anywhere in the key fails all of them.
_SCOPE_KEY_ASKED = re.compile(r"[\w.]+\.canonical_root\(.+\)")
_SCOPE_KEY_CARRIED = re.compile(r"[\w.]+\.(root_path|canonical_root)")
_SCOPE_KEY_ABSENT = frozenset({"''", '""'})

#: Both function nodes, since every sweep below treats an `async def` exactly as a `def`.
_DEF = ast.FunctionDef | ast.AsyncFunctionDef

#: One parsed module: its path under `src/archcompass`, its tree, the function each node sits
#: in and the class each node sits in, both by `id()`. The last two are what let the sweep
#: follow a name out of the function that used it and into the ones that supply it.
_SweptModule = tuple[
    str, ast.AST, dict[int, ast.FunctionDef | ast.AsyncFunctionDef], dict[int, str]
]


def _enclosing_functions(tree: ast.AST) -> dict[int, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Which function each node is written inside, by `id()`, innermost winning.

    The node rather than its name, because the sweep below has to read a function's parameter
    list and follow the calls made inside it. Innermost wins for the same reason it does in
    `_enclosing_function_names`: `ast.walk` is breadth-first, so an outer function is visited
    before the ones nested in it and the inner name overwrites the outer.
    """

    holder: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for child in ast.walk(node):
                holder[id(child)] = node
    return holder


def _enclosing_classes(module: str, tree: ast.AST) -> dict[int, str]:
    """Which class each node is written inside, by `id()`, qualified by module.

    Qualified because the names collide: `RepositoryIndexService._recorded_for` and
    `ReviewWorkflowService._recorded_for` are two unrelated private helpers in two packages,
    and a sweep that followed `self._recorded_for(...)` by name alone walked from one into the
    other and reported the second one's `thread_id` as a badly spelled repository root.
    """

    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                owner[id(child)] = f"{module}::{node.name}"
    return owner


def _bound_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """The positional parameters a call site actually writes an argument for.

    `self` is dropped: `self._recorded_for(root)` passes one argument to a function declared
    with two, and every index after it would be off by one.
    """

    names = [item.arg for item in [*function.args.posonlyargs, *function.args.args]]
    return names[1:] if names[:1] == ["self"] else names


def _arguments_passed_for(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    owner: str | None,
    parameter: str,
    sources: list[_SweptModule],
) -> list[tuple[ast.expr, ast.FunctionDef | ast.AsyncFunctionDef | None]]:
    """What every caller in `src/` passes for `parameter`, paired with the function it sat in.

    Every module and not just the one the function lives in, because
    `RepositoryIndexService.scope` is public and the caller that reaches it is a web route two
    packages away. A forwarder whose callers were only looked for at home would leave a hole
    exactly the width of that route.

    Calls are matched by name, which is ambiguous, so a call through `self` is admitted only
    from inside the same class. That restriction is not tidiness: without it this sweep
    followed `ReviewWorkflowService._recorded_for(thread_id, review_id)` into the repository
    service's unrelated helper of the same name and failed on `thread_id`. A call through
    anything else — `runtime.repository_service.scope(root)` — cannot be attributed to a class
    from syntax alone and is admitted on the name, which over-collects towards more
    expressions having to satisfy the rule rather than fewer.
    """

    parameters = _bound_parameters(function)
    if parameter not in parameters:
        return []
    index = parameters.index(parameter)
    found: list[tuple[ast.expr, ast.FunctionDef | ast.AsyncFunctionDef | None]] = []
    for _module, tree, holder, classes in sources:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Name):
                name, through_self = called.id, False
            elif isinstance(called, ast.Attribute):
                name = called.attr
                through_self = (
                    isinstance(called.value, ast.Name) and called.value.id == "self"
                )
            else:
                continue
            if name != function.name:
                continue
            if through_self and classes.get(id(node)) != owner:
                continue
            keyword = next((item for item in node.keywords if item.arg == parameter), None)
            if keyword is not None:
                found.append((keyword.value, holder.get(id(node))))
            elif index < len(node.args):
                found.append((node.args[index], holder.get(id(node))))
    return found


def _key_expressions(
    expression: ast.expr,
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    owner: str | None,
    sources: list[_SweptModule],
    seen: frozenset[tuple[int, str]] = frozenset(),
) -> list[ast.expr]:
    """Every expression that can arrive here, following names and branches one hop at a time.

    A name is evidence of nothing on its own, and one hop of indirection is all it takes to
    put a hand-spelled key beyond a sweep's reach: `self._recorded_for(...)` is that hop, and
    the mutation that re-spelled the key at *its* call site rather than at `.get` failed no
    test in the tree. So a name is resolved — to the right-hand side of the assignment that
    made it, or,
    when it is a parameter, to whatever each caller in the tree passes for it. Assignments are
    preferred, because a parameter that is reassigned no longer carries what was passed. A
    conditional yields both of its arms, since either one can be the key.

    A name that resolves to nothing is handed back as itself and fails the rule below. An
    unexaminable key is not a key anybody has shown to be asked for, and the loud failure says
    exactly which expression to go and look at.
    """

    if isinstance(expression, ast.IfExp):
        return [
            resolved
            for branch in (expression.body, expression.orelse)
            for resolved in _key_expressions(branch, function, owner, sources, seen)
        ]
    if not isinstance(expression, ast.Name) or function is None:
        return [expression]
    marker = (id(function), expression.id)
    if marker in seen:
        return [expression]
    onwards = seen | {marker}
    assigned = [
        node.value
        for node in ast.walk(function)
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == expression.id
                for target in node.targets
            )
        )
        or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == expression.id
            and node.value is not None
        )
    ]
    onward_from: list[tuple[ast.expr, ast.FunctionDef | ast.AsyncFunctionDef | None, str | None]]
    if assigned:
        onward_from = [(value, function, owner) for value in assigned if value is not None]
    else:
        onward_from = [
            (value, caller, _owner_of(caller, sources))
            for value, caller in _arguments_passed_for(
                function, owner, expression.id, sources
            )
        ]
    if not onward_from:
        return [expression]
    return [
        resolved
        for value, caller, caller_owner in onward_from
        for resolved in _key_expressions(value, caller, caller_owner, sources, onwards)
    ]


def _owner_of(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None, sources: list[_SweptModule]
) -> str | None:
    """The qualified class a function is written in, or `None` for a module-level one."""

    if function is None:
        return None
    for _, _, _, classes in sources:
        if id(function) in classes:
            return classes[id(function)]
    return None


def test_a_scope_selection_key_is_always_asked_for_and_never_spelled_out() -> None:
    """Nothing in `src/` computes the string a scope selection is filed under. It asks for it.

    `scope_selections` is keyed by a plain path string, and a lookup under a spelling nothing
    recorded does not fail — it returns `None`, which reads as "nobody chose a scope". The
    review then runs over the whole repository, its fingerprint is taken over a different set
    of files than the stored atlas covers, and `AtlasFreshnessService` marks that atlas stale
    on every open, forever. The workspace on this machine is living in the near miss already:
    `scope_selections` holds a row for `examples/cases/acme-shop/repository` while
    `atlas_versions` holds one for `eval/cases/acme-shop/repository` — the same case under two
    spellings of its root, with the recorded scope invisible to one of them.

    Three readers used to spell that key out by hand, each carrying its own copy of
    `str(root.expanduser().resolve(strict=False))` beside a comment promising it matched the
    others. They did match. That is what makes a duplicated derivation survive every behavioural
    test written against it — the shape `a30648e` and `366b7e5` each fixed elsewhere in this
    repository, and which came back both times when a new code path arrived that derived the
    value again. `AtlasSource.canonical_root` answers the question instead, so there is no
    expression left to keep in step — and this sweep is what stops a fourth one being written.
    Six re-spellings were tried against this sweep: at `.get`, at the private helper that
    forwards to it, in the freshness check, behind a local name, at a web route two packages
    away, and as a `canonical_root` of the service's own. Each one is caught here and fails
    nothing else, and each one passes the whole unit suite with this test deselected — because
    none of them changes what the code does, which is the entire difficulty.

    Every allowed form asks or carries; none of them builds. `analyzer.canonical_root(path)`
    puts the question to the object that decides the answer; `version.root_path`,
    `summary.root_path` and `repository.canonical_root` read that same answer back off records
    written from it. Anything that assembles the string here fails, including a copy that is
    correct today, which is the only kind this defect has ever arrived as.
    """

    sources: list[_SweptModule] = []
    for path in _python_files(SOURCE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = path.relative_to(SOURCE_ROOT).as_posix()
        sources.append(
            (module, tree, _enclosing_functions(tree), _enclosing_classes(module, tree))
        )

    keys: set[tuple[str, str, str]] = set()
    readers: set[str] = set()
    for module, tree, holder, classes in sources:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in _SCOPE_SELECTION_METHODS:
                continue
            if not _SCOPE_SELECTION_HOLDER.search(ast.unparse(node.func.value)):
                continue
            readers.add(module)
            if not node.args:
                keys.add((module, node.func.attr, ast.unparse(node)))
                continue
            enclosing = holder.get(id(node))
            for resolved in _key_expressions(
                node.args[0], enclosing, classes.get(id(node)), sources
            ):
                keys.add((module, node.func.attr, ast.unparse(resolved)))

    assert readers >= _SCOPE_SELECTION_READERS, (
        f"this sweep found scope-selection calls only in {sorted(readers)}, and expects them "
        f"in at least {sorted(_SCOPE_SELECTION_READERS)}; a sweep that has lost its subject "
        "reports success over no code at all"
    )
    spelled = sorted(
        entry
        for entry in keys
        if entry[2] not in _SCOPE_KEY_ABSENT
        and not _SCOPE_KEY_ASKED.fullmatch(entry[2])
        and not _SCOPE_KEY_CARRIED.fullmatch(entry[2])
    )
    assert not spelled, (
        "a scope selection is keyed by a string the caller works out for itself: "
        + "; ".join(
            f"{module}: scope_selections.{method}({key})" for module, method, key in spelled
        )
        + " — the key may only be `<analyzer>.canonical_root(<root>)`, asked of the object "
        "that decides it, or a `.root_path` / `.canonical_root` read whole off a record that "
        "was written from that answer"
    )

    # A second answerer is the same defect wearing the right name. The rule above admits any
    # `.canonical_root(...)`, so a service that grew a helper of that name whose body was the
    # old hand-spelled expression would satisfy it while reintroducing exactly what it forbids
    # — `_SCOPE_KEY_ASKED` matches `self.canonical_root(repository)` in full, and that mutation
    # passed this test until these lines were added. What makes the question worth asking at
    # all is that the answer is the string `analyze` will stamp on the atlas, so only the thing
    # that runs the analysis may answer it: every `canonical_root` in `src/` sits beside an
    # `analyze` in the same class. A second analyzer is welcome and would carry both; a helper
    # on a service carries neither the method nor the guarantee.
    answered_by = [
        (module, owner.name, {item.name for item in owner.body if isinstance(item, _DEF)})
        for module, tree, _, _ in sources
        for owner in ast.walk(tree)
        if isinstance(owner, ast.ClassDef)
        and any(isinstance(item, _DEF) and item.name == "canonical_root" for item in owner.body)
    ]
    loose = sorted(
        f"{module}:{node.name}"
        for module, tree, _, classes in sources
        for node in ast.walk(tree)
        if isinstance(node, _DEF) and node.name == "canonical_root" and id(node) not in classes
    )
    assert answered_by, (
        "nothing in src/ defines `canonical_root`; the question this rule is built on has no "
        "answerer, so the sweep above is checking a shape nobody implements"
    )
    assert not loose, (
        f"`canonical_root` is defined outside any class at {loose}; the answer is only worth "
        "asking for because it is the string that analyzer's own `analyze` will stamp"
    )
    impostors = sorted(
        f"{module}:{owner}" for module, owner, methods in answered_by if "analyze" not in methods
    )
    assert not impostors, (
        f"{impostors} answer `canonical_root` without running an analysis; only an analyzer "
        "may answer it, because the answer's whole content is what that analyzer's `analyze` "
        "will stamp on the atlas — a helper of this name anywhere else is the hand-spelled "
        "key back again, under a spelling the rule above cannot tell from the real one"
    )


#: The record one reading of the model selection produces, and the only name this sweep is
#: handed. Which function produces one, and what each reader calls the callable it holds, are
#: both derived from the annotations in `src/` below — a list of reader names maintained here
#: would be the second place to forget, which is the thing four fixes of this defect have now
#: been lost to.
_SELECTION_RECORD = "JudgeSelection"

#: Where a reading is taken today, as a lower bound rather than an equality: wiring an eighth
#: reader should not have to be recorded here, but a sweep that has stopped finding these has
#: stopped sweeping and would report success over no code at all. Six of them are the readers
#: `bootstrap` hands `SelectedLangChainJudge.selection` to; the seventh is that judge reading
#: its own answer to decide which judge it is.
_SELECTION_READERS = frozenset(
    {
        ("reasoning/cache.py", "key"),
        ("analysis/delta.py", "calculate"),
        ("bootstrap.py", "deterministic_retrieval_mode"),
        ("reasoning/adapters/selected.py", "judge"),
        ("reasoning/adapters/selected.py", "generate"),
        ("reasoning/adapters/selected.py", "write"),
        ("reasoning/adapters/selected.py", "answer"),
    }
)


def _selection_reader_names(trees: list[ast.AST]) -> tuple[frozenset[str], frozenset[str]]:
    """Every name in `src/` that yields a reading of the model selection, found by annotation.

    Two families, and neither is spelled out. A *producer* is a function whose return
    annotation names the record — `SelectedLangChainJudge.selection` is the only one, and
    `bootstrap` and `selected.py` call it by that name. A *holder* is an attribute a
    constructor assigns from a parameter annotated as a callable returning the record. Every
    holder spells it `_selection` today, and that agreement is a convention rather than a
    rule: `delta.py` called its `_judgement` until the rename that gave the record its
    present name, and nothing refuses the next one that picks a spelling of its own. That is
    why this reads annotations and not names.

    Deriving both is what lets the guard survive a rename and an eighth reader. Nothing here
    is edited when one is wired, because pyright already makes that reader declare the type
    at the `bootstrap` call site, and declaring it is what puts it in this sweep.
    """

    producers: set[str] = set()
    holders: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.returns is not None and _SELECTION_RECORD in ast.unparse(node.returns):
                producers.add(node.name)
            held = {
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                if argument.annotation is not None
                and _SELECTION_RECORD in ast.unparse(argument.annotation)
                and "Callable" in ast.unparse(argument.annotation)
            }
            holders.update(
                target.attr
                for statement in ast.walk(node)
                if isinstance(statement, ast.Assign)
                and isinstance(statement.value, ast.Name)
                and statement.value.id in held
                for target in statement.targets
                if isinstance(target, ast.Attribute)
            )
    return frozenset(producers), frozenset(holders)


def test_no_function_reads_the_model_selection_more_than_once() -> None:
    """One reading per operation. A second call is the torn read, and it has been written.

    `selection()` is asked per call and not once at build, because a workspace changes its
    model through `PUT /api/models/selection` while the process runs and the change has to
    take effect. That is the feature, and it is also the hazard: two calls inside one
    operation can straddle the change, and a reader that takes a field from each ends up with
    a pair no selection ever had — the old model's name beside the new model's prompt.

    `cache.py` argues this out in full three lines above the read, and the comment was the
    only thing holding it: reverting that single `selection()` to a call each leaves every unit
    test in this suite passing, which was measured before this guard was written. Every stub
    the suite hands these readers answers the same thing twice, so no behavioural test in the
    tree can distinguish one reading from two. `test_reasoning_adapters.py` now has two that
    can, over a selection that moves between calls — but those cover two of the seven readers,
    and the lesson of the four previous fixes is that the eighth code path is the one nobody
    writes a test for. So the shape is asked of the source, where it is one rule over all of
    them.

    The rule is deliberately about the call count and not about how many fields are read.
    "Two calls but only one field each" is not safe either — two readers of one operation
    splitting the work between them is the same torn read spread over two lines — and a
    count is the thing that cannot be argued with. Binding the record to a local costs
    nothing, so there is no legitimate second call to protect.
    """

    trees = {
        path: ast.parse(path.read_text(encoding="utf-8"))
        for path in _python_files(SOURCE_ROOT)
    }
    producers, holders = _selection_reader_names(list(trees.values()))
    assert producers, (
        f"no function in src/ returns a {_SELECTION_RECORD}; this sweep has lost the record "
        "it is named after and would pass over anything"
    )
    assert holders, (
        f"nothing in src/ holds a Callable[[], {_SELECTION_RECORD}]; the six readers "
        "`bootstrap` wires are invisible to this sweep"
    )

    reads: list[tuple[str, str]] = []
    repeated: list[str] = []
    for path, tree in trees.items():
        module = path.relative_to(SOURCE_ROOT).as_posix()
        enclosing = _enclosing_function_names(tree)
        # A local alias counts as the reader it aliases. `judging = self._selection` followed
        # by two `judging()` calls is the same torn read written around a guard that only knew
        # how to see `self._selection()`, and it is the first thing anybody tries. Binding the
        # *record* — `selection = self._selection()` — is the correct spelling and is not an
        # alias, which is why only a bare attribute counts here and never a call's result.
        aliases = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr in producers | holders
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        counted: dict[str, int] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                (isinstance(node.func, ast.Attribute) and node.func.attr in producers | holders)
                or (isinstance(node.func, ast.Name) and node.func.id in aliases)
            ):
                continue
            where = enclosing.get(id(node), "<module>")
            counted[where] = counted.get(where, 0) + 1
        reads.extend((module, where) for where in counted)
        repeated.extend(
            f"{module}:{where} reads it {count} times"
            for where, count in sorted(counted.items())
            if count > 1
        )

    assert set(reads) >= _SELECTION_READERS, (
        f"this sweep found readings of the model selection only in {sorted(set(reads))}, and "
        f"expects them in at least {sorted(_SELECTION_READERS)}; a sweep that has lost its "
        "subject reports success over no code at all"
    )
    assert not repeated, (
        "the model selection is read twice inside one operation: "
        + "; ".join(repeated)
        + " — a workspace can change its model between the two calls, so the two readings "
        "are not one selection. Bind `selection()` to a local once and read every field off "
        "that record."
    )


#: The two stamps a judgement leaves on what it judged. Named together because they are one
#: fact with two halves — which model, asked which question — and both have to be read off
#: the same record for the same reason.
_JUDGEMENT_STAMPS = ("model_identity", "prompt_identity")

#: What a "collection of findings" looks like in an annotation, in the two families that
#: exist here: the domain's own `Finding` and the wire's `FindingResponse`. Matched as a
#: word so that a field annotated `RecordedInvestigation` is not swept in by accident.
_FINDING_COLLECTION = re.compile(r"\b(tuple|list|Sequence|dict|Iterable)\[[^\]]*\bFinding\w*\b")


def _annotated_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str]:
    """Every parameter that carries an annotation, as name to unparsed annotation.

    The mirror of `_annotated_fields`, and it exists for the same reason: the sweeps below
    derive what they are about from annotations rather than from names, so renaming a
    parameter cannot quiet a guard.
    """

    return {
        argument.arg: ast.unparse(argument.annotation)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        if argument.annotation is not None
    }


def _annotated_fields(node: ast.ClassDef) -> dict[str, str]:
    return {
        statement.target.id: ast.unparse(statement.annotation)
        for statement in node.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }


def test_no_record_of_many_findings_claims_one_judgement_identity() -> None:
    """A set of stamps is not a stamp, and a record that holds both invites the comparison.

    `Review` carried `model_identity` and `prompt_identity`, composed by `report.py` as
    `",".join(sorted({every stamp its findings carry}))`, and `DeterministicRevisionCalculator`
    compared that joined string against the single identity `SelectedLangChainJudge.selection`
    reports. Those are not the same kind of value. They were equal only because every review
    stored here holds exactly one — measured read-only over `.archcompass/workspace.sqlite3`:
    7 reviews, 148 findings, one pair, none unstamped — so the defect was latent rather than
    absent. Judgement fans out per candidate through `Send` and `selection()` is read per call
    so that `PUT /api/models/selection` takes effect mid-run, which is how a review comes to
    hold two stamps; against such a review the joined string equalled no single identity, so
    every candidate read changed and the whole review was judged again. That re-judgement
    stamped every finding with the identity in force, which is why the next revision matched
    again — re-measured on the wiring that carried the fields, over the stored 7-finding
    review with three findings restamped: `unchanged=0 changed=7`, then `unchanged=7
    changed=0`. A whole review re-judged for nothing, once per straddle, rather than for ever.

    This is the "delete the second place" mechanism rather than a better join, because a
    better join is what has already failed four times here. The rule is stated over the shape
    instead of over the name `Review`: any record that holds a collection of findings and
    also declares one of the two stamps is claiming that many judgements had one identity,
    and that claim is what the comparison was built on. `synopsis_identity` is deliberately
    not swept — one paragraph really does have one author.

    The reach is what the regexes above admit and no more: an annotation naming a container
    of `Finding` or `FindingResponse`, and a field named exactly as the judge stamps it. A
    record that reached the same claim through an alias would pass, which is why the sibling
    test holds the comparison itself rather than only the field it read.
    """

    holders: list[str] = []
    offenders: list[str] = []
    for path in _python_files(SOURCE_ROOT):
        module = path.relative_to(SOURCE_ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = _annotated_fields(node)
            if not any(_FINDING_COLLECTION.search(item) for item in fields.values()):
                continue
            holders.append(f"{module}:{node.name}")
            offenders.extend(
                f"{module}:{node.name}.{stamp}" for stamp in _JUDGEMENT_STAMPS if stamp in fields
            )

    assert holders, (
        "no record in src/ was found holding a collection of findings; this sweep has lost "
        "its subject and would report success over no code at all"
    )
    assert not offenders, (
        "a record of many findings claims one judgement identity: "
        + ", ".join(sorted(offenders))
        + " — the identity of many judgements is a set, the delta compares a single value, "
        "and the two agree only until a review mixes two models. Read the stamp off the "
        "finding that carries it."
    )


#: What a parameter holding exactly one candidate's sequence looks like. The loop over it is
#: one of the two shapes that count as having a finding in hand.
_OVER_CANDIDATES = re.compile(r"\b(tuple|list|Sequence)\[\s*Candidate\b")


def test_the_revision_delta_compares_a_judgement_identity_per_candidate() -> None:
    """Nowhere in `src/` may a judgement stamp be compared without one finding in hand.

    The sibling test deletes the review-level field; this one deletes the place that read
    it. `MODEL` and `PROMPT` were appended to `global_causes` before the loop, from a
    comparison that ran once and then spoke for every candidate. That placement is what made
    a review-wide value the only thing there was to compare against, and it is what makes
    reintroducing such a field the obvious repair the next time somebody needs a second
    opinion here. With one finding in scope the only stamps reachable are that candidate's
    own, so the fix cannot be undone by half.

    **The reach is every function in `src/archcompass`, and it was `calculate` alone until a
    verify pass walked through the gap.** A helper lifted to module level in `delta.py`, taking
    `previous` and joining every finding's stamp, passed both source sweeps; only
    `test_a_review_that_mixed_two_models_re_judges_only_what_the_moved_model_judged` failed.
    That is the fifth time this defect has come back through a code path a guard did not read,
    so the guard now reads all of them. Going wider than `delta.py` is deliberate: a review-wide
    join needs no review-level field to spell — `",".join(sorted({f.prompt_identity for f in
    previous.findings})) != selection.prompt_identity` is the whole defect and it compiles in
    any module — so a file-scoped rule makes "put it in a second file" the route, which is this
    defect's entire history.

    Going wider costs nothing measurable and needs no exemption list. Walking
    `src/archcompass` on this branch, exactly two comparisons mention a stamp read off a
    record, and both are `judgement_moved`'s in `analysis/delta.py`. The one other comparison
    naming a stamp anywhere in `src/` — `model_identity is None` in `langchain.py`, choosing
    how to word a parsing failure — is not swept, because the sweep matches a stamp read as an
    attribute of something rather than the bare word: that one reads a `str | None` parameter
    and touches no record at all. Nothing is listed as excused, so there is no list for the
    next repair to add a name to.

    What "in hand" means is derived from annotations rather than from names, and either shape
    satisfies it: lexically inside a `for` over a parameter annotated as a sequence of
    `Candidate`, or inside a function taking a parameter annotated `Finding` and *not* a
    container of them. That second exclusion is load-bearing rather than tidy: `tuple[Finding,
    ...]` names `Finding` too, so without it a helper taking `findings` and comparing a join of
    their stamps satisfies the rule while being the defect — checked by writing that helper and
    watching the sweep pass without the exclusion and fail with it.

    Three assertions, and the third is what closes the helper shape: a function taking a
    `Finding` could still read a stamp off a closed-over review, so no stamp may be read off any
    parameter annotated `Review` at all. Deleted together with the field it named, and held here
    so that the read cannot come back before the field does.

    Neither of this pair is complete alone and neither is a re-spelling of the code. This one
    asserts a placement and says nothing about what is compared;
    `test_no_record_of_many_findings_claims_one_judgement_identity` asserts what may exist to
    be compared and says nothing about where. Four ways of putting the comparison back were
    written out and run against this sweep — the verifier's module-level helper, the same
    helper moved to a second module, the original hoist into `global_causes`, and the
    `tuple[Finding, ...]` dodge — and all four fail it.
    """

    def _named(node: ast.FunctionDef | ast.AsyncFunctionDef, pattern: str) -> set[str]:
        return {
            name
            for name, annotation in _annotated_parameters(node).items()
            if re.search(pattern, annotation)
        }

    def _one_finding(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        return {
            name
            for name, annotation in _annotated_parameters(node).items()
            if re.search(r"\bFinding\b", annotation)
            and not _FINDING_COLLECTION.search(annotation)
        }

    scopes: set[str] = set()
    in_hand: set[int] = set()
    compared: list[tuple[str, ast.Compare]] = []
    off_the_review: set[str] = set()
    for path in _python_files(SOURCE_ROOT):
        module = path.relative_to(SOURCE_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            where = f"{module}:{node.name}"
            if _one_finding(node):
                scopes.add(f"{where} takes one Finding")
                in_hand.update(id(inner) for inner in ast.walk(node))
            iterated = _named(node, _OVER_CANDIDATES.pattern)
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.For)
                    and isinstance(inner.iter, ast.Name)
                    and inner.iter.id in iterated
                ):
                    scopes.add(f"{where} iterates {inner.iter.id}")
                    in_hand.update(id(within) for within in ast.walk(inner))
            reviews = _named(node, r"\bReview\b")
            off_the_review.update(
                f"{module}:{inner.lineno} {ast.unparse(inner)}"
                for inner in ast.walk(node)
                if isinstance(inner, ast.Attribute)
                and inner.attr in _JUDGEMENT_STAMPS
                and isinstance(inner.value, ast.Name)
                and inner.value.id in reviews
            )
        compared.extend(
            (module, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(
                isinstance(inner, ast.Attribute) and inner.attr in _JUDGEMENT_STAMPS
                for inner in ast.walk(node)
            )
        )

    assert scopes, (
        "nothing in src/ iterates a sequence of Candidate and nothing there takes a single "
        "Finding; this sweep derives its scope from those two annotations, so it has lost "
        "its subject and would report success over no code"
    )
    assert compared, (
        "no comparison in src/ reads a judgement stamp off a record; the delta has stopped "
        "reporting ChangeCause.MODEL and ChangeCause.PROMPT altogether"
    )
    loose = [
        f"{module}:{node.lineno} {ast.unparse(node)}"
        for module, node in compared
        if id(node) not in in_hand
    ]
    assert not loose, (
        "a judgement stamp is compared without one finding in hand: "
        + "; ".join(sorted(loose))
        + " — a comparison there runs once and speaks for every candidate, so its other side "
        "can only be a review-wide value, which is the defect this pair of guards exists for."
    )
    assert not off_the_review, (
        "a judgement stamp is read off a review: "
        + ", ".join(sorted(off_the_review))
        + " — a review holds many judgements and no single identity for them, which is why "
        "the field it was read from was deleted rather than recomposed."
    )
