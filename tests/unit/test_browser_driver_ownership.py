import ast
from pathlib import Path


def test_connectonion_runtime_has_no_patchright_import_and_uses_onionwright_api():
    package = Path(__file__).parents[2] / "connectonion"
    imported = set()
    for source_path in package.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

    assert not any(name == "patchright" or name.startswith("patchright.") for name in imported)
    assert "onionwright.async_api" in imported
    assert "onionwright.sync_api" in imported


def test_public_dependency_set_contains_playwright_not_patchright():
    pyproject = (Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="utf-8")

    assert '"playwright==1.61.0"' in pyproject
    assert "patchright" not in pyproject.lower()
