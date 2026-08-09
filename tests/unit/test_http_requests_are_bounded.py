"""A degraded backend must not leave a CLI command waiting forever."""

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
REQUEST_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def test_every_requests_call_has_an_explicit_timeout():
    missing = []

    for path in (REPO / "connectonion").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            if (
                isinstance(owner, ast.Name)
                and owner.id == "requests"
                and node.func.attr in REQUEST_METHODS
                and not any(keyword.arg == "timeout" for keyword in node.keywords)
            ):
                missing.append(f"{path.relative_to(REPO)}:{node.lineno}")

    assert missing == [], "requests calls without a timeout: " + ", ".join(missing)
