"""An async test with no asyncio marker is not a test; it is a skip.

pytest-asyncio runs in strict mode here — `pytest.ini` sets no `asyncio_mode`,
and the marker is declared:

    asyncio: Async tests using pytest-asyncio

So an `async def test_...` that is not marked (on itself, on its class, or via
a module-level `pytestmark`) is collected, skipped, and counted as a skip:

    SKIPPED [13] async def function and no async plugin installed

That is what a whole class looks like after losing its decorator. It happened
in #699: a helper was inserted between `@pytest.mark.asyncio` and the class it
decorated, so the marker landed on the helper and thirteen tests stopped
running. Locally the signal was thirteen skips, which reads like an environment
quirk and is easy to scroll past; CI reported failures only because the same
edit also broke unrelated cases in the class.

A skip is the quiet failure mode: the tests are still listed, still green, and
測 nothing. This makes that state loud.

Static on purpose. Asserting "nothing was skipped for this reason" during a run
only covers the tests that run in that session; walking the files covers all of
them, including any added tomorrow.
"""

import ast
import pathlib

import pytest


TESTS = pathlib.Path(__file__).resolve().parents[1]


def _is_asyncio_marker(node) -> bool:
    """@pytest.mark.asyncio, with or without arguments."""
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr == "asyncio"


def _module_is_marked(tree) -> bool:
    """A module-level `pytestmark = pytest.mark.asyncio`, alone or in a list."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "pytestmark" for t in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        if any(_is_asyncio_marker(v) for v in values):
            return True
    return False


def _unmarked_async_tests(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    if _module_is_marked(tree):
        return []

    found = []

    def walk(body, class_marked: bool):
        for node in body:
            if isinstance(node, ast.ClassDef):
                marked = class_marked or any(_is_asyncio_marker(d)
                                             for d in node.decorator_list)
                walk(node.body, marked)
            elif isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_"):
                own = any(_is_asyncio_marker(d) for d in node.decorator_list)
                if not (own or class_marked):
                    found.append(f"{path.relative_to(TESTS.parent)}:{node.lineno} {node.name}")

    walk(tree.body, class_marked=False)
    return found


ALL_TEST_FILES = sorted(TESTS.rglob("test_*.py"))


def test_there_are_async_tests_to_check():
    """If this ever finds none, the check below has stopped meaning anything."""
    with_async = [p for p in ALL_TEST_FILES
                  if "async def test" in p.read_text(encoding="utf-8", errors="replace")]

    assert len(with_async) > 5, f"only {len(with_async)} files with async tests"


@pytest.mark.parametrize("path", ALL_TEST_FILES, ids=lambda p: p.name)
def test_every_async_test_carries_the_marker(path):
    unmarked = _unmarked_async_tests(path)

    assert not unmarked, (
        "these are skipped, not run — add @pytest.mark.asyncio to the test, its "
        "class, or a module-level pytestmark:\n  " + "\n  ".join(unmarked)
    )
