"""When the analyser says a module has become the place everything goes through.

The signal under test is a proxy and says so, but it still has to be wrong in the right
direction: a module that is merely large, or merely popular inside its own package, must
not be reported, because a report that fires on every big file is a report nobody reads.
Each fixture below is one of those near misses.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import Atlas, MetricNature

CODE = "concentrated-scope"


def _repository(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _analyse(root: Path) -> Atlas:
    return PythonAstRepositoryAnalyzer().analyze(root)


def _signalled_paths(atlas: Atlas) -> set[str]:
    by_id = {node.atlas_id: node for node in atlas.nodes}
    return {
        by_id[signal.node_id].path
        for signal in atlas.signals
        if signal.code == CODE
    }


def _module(names: list[str]) -> str:
    """A module whose public surface is exactly the names given."""

    return "".join(f"def {name}(value):\n    return value\n\n\n" for name in names)


def _dependants(module: str, symbol_by_module: dict[str, str]) -> dict[str, str]:
    """One importing module per entry, each reaching for its own name."""

    return {
        path: f"from {module} import {symbol}\n\n\ndef use(value):\n    return {symbol}(value)\n"
        for path, symbol in symbol_by_module.items()
    }


#: Nine dependants in three packages, each pulling a different name out of the module they
#: share. Reused by the fixtures below so that only the shared module differs between them.
SPREAD_DEPENDANTS = {
    "orders/intake.py": "reserve_stock",
    "orders/dispatch.py": "record_shipment",
    "orders/refunds.py": "issue_credit",
    "billing/invoices.py": "price_line",
    "billing/ledger.py": "post_entry",
    "billing/dunning.py": "send_reminder",
    "shipping/labels.py": "print_label",
    "shipping/routes.py": "plan_route",
    "shipping/tracking.py": "reserve_stock",
}


def test_a_module_many_packages_reach_for_different_names_is_reported(
    tmp_path: Path,
) -> None:
    root = _repository(
        tmp_path,
        {
            "platform_core/hub.py": _module(sorted(set(SPREAD_DEPENDANTS.values()))),
            **_dependants("platform_core.hub", SPREAD_DEPENDANTS),
        },
    )

    atlas = _analyse(root)

    assert _signalled_paths(atlas) == {"platform_core/hub.py"}
    signal = next(item for item in atlas.signals if item.code == CODE)
    assert "platform_core.hub" in signal.message
    assert "billing" in signal.message and "orders" in signal.message
    # Labelled for what it is, so a reader is never told a count has decided anything.
    assert signal.nature is MetricNature.STRUCTURAL_PROXY
    assert signal.definition and signal.limitations


def test_a_large_module_reached_through_one_name_is_left_alone(tmp_path: Path) -> None:
    """The counterweight: local complexity behind a narrow seam is a module earning its keep."""

    private_helpers = "".join(
        f"def _step_{index}(value):\n    return value + {index}\n\n\n" for index in range(12)
    )
    root = _repository(
        tmp_path,
        {
            "engine/core.py": private_helpers
            + "def run(value):\n"
            + "".join(f"    value = _step_{index}(value)\n" for index in range(12))
            + "    return value\n",
            **_dependants(
                "engine.core",
                dict.fromkeys(SPREAD_DEPENDANTS, "run"),
            ),
        },
    )

    atlas = _analyse(root)

    assert _signalled_paths(atlas) == set()


def test_a_wide_module_used_only_inside_its_own_package_is_left_alone(
    tmp_path: Path,
) -> None:
    """Nine names and nine callers, all of them siblings. Nothing crosses a boundary."""

    names = sorted(set(SPREAD_DEPENDANTS.values()))
    root = _repository(
        tmp_path,
        {
            "orders/hub.py": _module(names),
            **_dependants(
                "orders.hub",
                {
                    f"orders/part_{index}.py": name
                    for index, name in enumerate(SPREAD_DEPENDANTS.values())
                },
            ),
        },
    )

    atlas = _analyse(root)

    assert _signalled_paths(atlas) == set()


def test_a_small_repository_reports_nothing(tmp_path: Path) -> None:
    """Three modules cannot amplify a change into eight, whatever their shape."""

    root = _repository(
        tmp_path,
        {
            "shared.py": _module(sorted(set(SPREAD_DEPENDANTS.values()))),
            "orders/intake.py": "from shared import reserve_stock\n",
            "billing/ledger.py": "from shared import post_entry\n",
        },
    )

    atlas = _analyse(root)

    assert _signalled_paths(atlas) == set()


def test_tests_reaching_for_everything_do_not_concentrate_a_module(
    tmp_path: Path,
) -> None:
    """A test module imports whatever it exercises; that is not a concern pulled through."""

    names = sorted(set(SPREAD_DEPENDANTS.values()))
    root = _repository(
        tmp_path,
        {
            "platform_core/hub.py": _module(names),
            **{
                f"tests/{package}/test_{index}.py": f"from platform_core.hub import {name}\n\n\n"
                f"def test_{index}():\n    assert {name}(1) == 1\n"
                for index, (package, name) in enumerate(
                    zip(
                        ["orders", "billing", "shipping"] * 3,
                        SPREAD_DEPENDANTS.values(),
                        strict=False,
                    )
                )
            },
        },
    )

    atlas = _analyse(root)

    assert _signalled_paths(atlas) == set()
