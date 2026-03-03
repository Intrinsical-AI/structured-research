"""Lightweight architectural guardrails for API imports."""

from __future__ import annotations

import ast
from pathlib import Path


def test_api_app_does_not_import_forbidden_layers():
    app_path = Path("src/structured_search/api/app.py")
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "structured_search.domain",
        "structured_search.ports",
        "structured_search.infra",
        "structured_search.tasks",
    )

    bad_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith(forbidden_prefixes):
                    bad_imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(forbidden_prefixes):
                bad_imports.append(module)

    assert bad_imports == []
