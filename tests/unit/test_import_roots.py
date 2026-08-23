"""Where an import counts from, which decides what every module in the atlas is called.

A qualified name is not cosmetic here. Import edges are matched by it, so a name no import
statement can produce resolves nothing — and `Candidate.identified` hashes the sorted
qualified names of a candidate's participants into its id, so the same names also decide
which stored decision belongs to which finding.

The failure this file exists to prevent was silent in both directions: the atlas came back
complete-looking, with nodes and metrics and signals, and only its dependency graph missing.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.adapters.ast_support import import_roots, module_name


def _src_layout(root: Path) -> Path:
    """A package under `src/`, importing itself the way it would be installed."""

    (root / "src" / "shop" / "billing").mkdir(parents=True)
    (root / "src" / "shop" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "shop" / "billing" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "shop" / "billing" / "invoices.py").write_text(
        "def total() -> int:\n    return 1\n", encoding="utf-8"
    )
    (root / "src" / "shop" / "orders.py").write_text(
        "from shop.billing.invoices import total\n\n\n"
        "def place() -> int:\n    return total()\n",
        encoding="utf-8",
    )
    # Loose test modules beside the package, with no `__init__.py` of their own.
    (root / "tests").mkdir()
    (root / "tests" / "test_orders.py").write_text(
        "from shop.orders import place\n\n\ndef test_place() -> None:\n    assert place()\n",
        encoding="utf-8",
    )
    return root


def test_a_src_layout_is_named_the_way_it_is_imported(tmp_path: Path) -> None:
    """`src/` goes on the path when the package is installed, so it is not part of the name.

    Without this, `src/shop/orders.py` was called `src.shop.orders`, no import statement
    anywhere says that, and every import edge in the repository failed to match. Measured on
    ArchCompass itself at the time: **95 import edges instead of 5,377**, and with them went
    every cyclic-dependency and concentrated-scope signal and the whole dependency and
    change-amplification metric families.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(_src_layout(tmp_path / "project"))
    names = {node.qualified_name for node in atlas.nodes}

    assert "shop.orders" in names, sorted(names)
    assert "shop.billing.invoices" in names, sorted(names)
    assert not [name for name in names if name.startswith("src.")], sorted(names)

    # The point of the naming: the import actually resolves to the module it names.
    imports = Counter(edge.edge_type for edge in atlas.edges)
    assert imports["imports"], "a src-layout repository resolved no import at all"


def test_a_test_directory_is_not_an_import_root(tmp_path: Path) -> None:
    """A `tests/` folder with no `__init__.py` holds loose modules, not a package.

    Python itself would import `tests/test_orders.py` as `test_orders` under a rootdir
    insertion, and treating it that way here would rename every test module in every
    repository — losing where it lives, and changing the identity of every candidate that
    names one. So an import root has to actually hold a package, and `tests/` does not.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(_src_layout(tmp_path / "project"))
    names = {node.qualified_name for node in atlas.nodes}

    assert "tests.test_orders" in names, sorted(names)
    assert "test_orders" not in names, sorted(names)


def test_the_rule_is_the_directories_and_not_a_configuration_file() -> None:
    """Read from the tree, so a repository with no packaging metadata behaves the same."""

    flat = ("shop/__init__.py", "shop/orders.py", "tests/test_orders.py")
    layered = ("src/shop/__init__.py", "src/shop/orders.py", "tests/test_orders.py")
    # A repository that is itself one package: its own root has no parent to import from.
    rooted = ("__init__.py", "billing/__init__.py", "billing/invoices.py")

    assert import_roots(flat) == frozenset({""})
    assert import_roots(layered) == frozenset({"", "src"})
    assert import_roots(rooted) == frozenset({""})

    assert module_name("src/shop/orders.py", import_roots(layered)) == "shop.orders"
    assert module_name("tests/test_orders.py", import_roots(layered)) == "tests.test_orders"
    assert module_name("shop/orders.py", import_roots(flat)) == "shop.orders"
    # No roots at all is what every caller passed before src layouts were handled, and it
    # still names a path from the repository root.
    assert module_name("src/shop/orders.py") == "src.shop.orders"
