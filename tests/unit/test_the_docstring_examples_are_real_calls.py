"""An example in a docstring is a call somebody will make.

`test_the_documented_calls_are_real_calls.py` checks README.md and docs/README.md.
Docstring examples were never in its scope, and one of them does not run:

    connectonion/network/relay.py:58

        Example:
            >>> from . import announce, address
            >>> addr = address.load()

    >>> address.load()
    TypeError: load() missing 1 required positional argument: 'co_dir'

That is the example `help(send_announce)` prints, and the one an IDE shows on
hover — the place a reader is most likely to copy from without checking.

Resolution is deliberately conservative, because a careless version of this
check reports mostly noise. A first pass over these same files flagged five
examples and four were the checker's fault:

    relay.py       await connect()                       relay.connect() takes no
                                                         required args — the module's
                                                         own function, not connectonion.connect
    llm_do.py      llm_do("John, 30 years old", …)       the comma is inside a string,
    transcribe.py  transcribe("meeting.mp3", prompt=…)   not between two arguments

So: arguments come from `ast`, never from splitting on commas, and a name is
resolved against the module the docstring lives in *first* — a module that
defines its own `connect` means its own `connect`.
"""

import ast
import inspect
import importlib
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "connectonion"


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _examples_in(path: Path):
    """(lineno, source) for each `>>>` line that parses as a statement."""
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        stripped = line.strip()
        if not stripped.startswith(">>> "):
            continue
        source = stripped[4:]
        try:
            yield lineno, ast.parse(source)
        except SyntaxError:
            continue  # a fragment or a continuation line, not a call to check


def _resolve(node: ast.AST, module):
    """The callable an example's `f(...)` or `a.f(...)` refers to, or None.

    The module the docstring lives in wins: relay.py documenting `connect()`
    means `relay.connect`, not `connectonion.connect`.
    """
    import connectonion

    if isinstance(node, ast.Name):
        owner_first = getattr(module, node.id, None)
        return owner_first if callable(owner_first) else None

    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        owner = getattr(module, node.value.id, None) or getattr(connectonion, node.value.id, None)
        target = getattr(owner, node.attr, None) if owner is not None else None
        return target if callable(target) else None

    return None


def _unbindable(tree, module):
    """Calls in this example that would raise TypeError before doing anything."""
    broken = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = _resolve(node.func, module)
        if fn is None or inspect.isclass(fn):
            continue
        try:
            signature = inspect.signature(fn)
        except (ValueError, TypeError):
            continue
        if any(kw.arg is None for kw in node.keywords):
            continue  # **kwargs splat — nothing to check
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue
        try:
            signature.bind(*[None] * len(node.args),
                           **{kw.arg: None for kw in node.keywords})
        except TypeError as exc:
            broken.append((getattr(fn, "__name__", str(fn)), str(exc)))
    return broken


SOURCES = sorted(PACKAGE.rglob("*.py"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_every_docstring_example_is_a_call_that_could_run(path):
    if "templates" in path.parts:
        pytest.skip("scaffolding written into a user's project, not imported here")

    module = importlib.import_module(_module_name(path))

    failures = []
    for lineno, tree in _examples_in(path):
        for name, why in _unbindable(tree, module):
            failures.append(f"{path.relative_to(REPO)}:{lineno} — {name}(): {why}")

    assert not failures, "\n".join(failures)


class TestTheCheckerItself:
    """The false positives that a naive version of this produced, pinned so the
    check cannot quietly become one that passes by never resolving anything."""

    def test_it_resolves_a_name_the_module_defines_itself(self):
        relay = importlib.import_module("connectonion.network.relay")

        assert _resolve(ast.parse("connect()").body[0].value.func, relay) is relay.connect

    def test_it_reads_arguments_from_the_syntax_not_the_commas(self):
        """`llm_do("John, 30 years old", output=Person)` passes one positional."""
        call = ast.parse('llm_do("John, 30 years old", output=Person)').body[0].value

        assert len(call.args) == 1

    def test_it_finds_a_call_that_is_really_broken(self):
        import connectonion.network.relay as relay

        broken = _unbindable(ast.parse("address.load()"), relay)

        assert broken and "co_dir" in broken[0][1]
