from __future__ import annotations

import ast
from pathlib import Path


def test_domain_and_application_do_not_import_infrastructure() -> None:
    forbidden = (
        "archcompass.adapters",
        "sqlite3",
        "sqlite_vec",
        "httpx",
        "typer",
    )
    for root in (Path("src/archcompass/domain"), Path("src/archcompass/application")):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            ] + [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            assert not any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for imported in imports
                for prefix in forbidden
            ), f"{path} imports infrastructure"

