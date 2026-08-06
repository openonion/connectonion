"""An `Integration: exposes` clause names functions that are not there.

Every module in this package carries an LLM-Note header, and the `exposes`
clause is the one an agent reads to find out what it may call. Ten names across
eight modules did not exist:

    useful_tools/todo_list.py   list_todos()      the method is list()
    tui/keys.py                 restore_terminal()  it is disable_bracketed_paste()

Those two had an unambiguous right answer and are corrected. The other eight are
in KNOWN_STALE below — each needs someone to decide what the header meant before
it can be rewritten, and guessing is how a header becomes wrong in the first
place:

    tui/input.py            Input(...) with read_input() → str
    useful_tools/terminal.py    browse_files(), input_with_at()
    network/io/__init__.py      send(), receive(), request_approval() — the
                                module defines nothing at all
    debug/…/runtime_inspector.py    get_traceback()
    useful_tools/browser_tools/element_finder.py  highlight_element()

This is the failure #717, #724 and #726 are about — a header trusted as a source
while the code moved — and this release has now hit it in docs/connectonion.md,
in create.py/init.py, in the model lists, and in fanout.py, which I had edited
myself. A per-file fix each time does not stop the next one; the invariant does.

## What this asserts, and what it deliberately does not

Only the `exposes` clause, and only names written with `()`. Prose elsewhere in a
header ("used by host()", "calls greet()") describes other people's functions and
is none of this test's business — an earlier version of the scan read those too
and produced 28 hits, 18 of them nonsense.

Names are matched against every def and class anywhere in the file, methods
included: `TodoList.add(...)` is legitimately named in a header, and a scan that
only sees module-level defs would call it missing.
"""

import ast
import pathlib
import re

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2] / "connectonion"

# Documented as exposed and genuinely absent when this test was written. Each one
# is a header to correct, not a test to keep passing — the list exists so the
# invariant can be enforced now and the stragglers fixed without a red suite.
KNOWN_STALE = {
    ("debug/runtime_inspector/runtime_inspector.py", "get_traceback"),
    ("network/io/__init__.py", "receive"),
    ("network/io/__init__.py", "request_approval"),
    ("network/io/__init__.py", "send"),
    ("tui/input.py", "read_input"),
    ("useful_tools/browser_tools/element_finder.py", "highlight_element"),
    ("useful_tools/terminal.py", "browse_files"),
    ("useful_tools/terminal.py", "input_with_at"),
}


def _exposed_names(tree):
    """The names an `Integration: exposes` clause promises, with parentheses."""
    doc = ast.get_docstring(tree) or ""
    match = re.search(r"Integration: exposes (.*?)(?: \| |\n)", doc)
    if not match:
        return set()
    return set(re.findall(r"\b([a-z_][a-z0-9_]{3,})\(", match.group(1)))


def _available_names(tree):
    """Every def, class and import in the file — methods included."""
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    names |= {a.asname or a.name.split(".")[0]
              for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
              for a in n.names}
    return names


def _scan():
    stale, checked = set(), 0
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        promised = _exposed_names(tree)
        if not promised:
            continue
        checked += 1
        available = _available_names(tree)
        rel = str(path.relative_to(ROOT))
        stale |= {(rel, name) for name in promised if name not in available}
    return stale, checked


class TestNoNewHeaderGoesStale:

    def test_nothing_beyond_the_known_list(self):
        stale, _ = _scan()

        assert stale <= KNOWN_STALE, (
            "a header promises a name that does not exist: "
            f"{sorted(stale - KNOWN_STALE)}"
        )

    def test_the_scan_is_actually_looking(self):
        _, checked = _scan()

        assert checked > 100, f"only {checked} headers had an exposes clause"

    def test_the_known_list_is_not_stale_itself(self):
        """A fixed header must be removed from KNOWN_STALE, or it rots too."""
        stale, _ = _scan()

        assert KNOWN_STALE <= stale, (
            "these were fixed — drop them from KNOWN_STALE: "
            f"{sorted(KNOWN_STALE - stale)}"
        )


def _tested_by_refs(tree):
    """The test files a header claims cover it."""
    doc = ast.get_docstring(tree) or ""
    match = re.search(r"tested by \[([^\]]+)\]", doc)
    if not match:
        return set()
    return set(re.findall(r"[\w/]+\.py", match.group(1)))


class TestEveryTestedByReferenceResolves:
    """A header pointing at a test file that does not exist is worse than silence.

    Six references were dead — renamed or removed files — and each one told a
    reader that a module had coverage somewhere they could go look at:

        core/llm.py                    tests/test_billing_error_agent.py
        llm_do.py                      tests/test_llm_do_comprehensive.py
                                       tests/test_real_llm_do.py
        network/connect.py             tests/integration/test_remote_agent.py
        tool_approval/__init__.py      tests/integration/test_bash_chain_permissions.py
        tool_approval/approval.py      (same)

    Correcting them turned up something the dead links had hidden: `llm_do` has
    no test file of its own. Its header now says so, rather than naming two files
    that were never there.
    """

    def test_no_header_points_at_a_missing_test_file(self):
        tests_root = ROOT.parent / "tests"
        missing = []
        for path in sorted(ROOT.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for ref in _tested_by_refs(tree):
                if not list(tests_root.rglob(pathlib.Path(ref).name)):
                    missing.append((str(path.relative_to(ROOT)), ref))

        assert missing == [], f"headers point at test files that do not exist: {missing}"

    def test_the_scan_finds_clauses_to_check(self):
        found = sum(
            1 for path in ROOT.rglob("*.py")
            if "__pycache__" not in str(path)
            and _tested_by_refs(ast.parse(
                path.read_text(encoding="utf-8", errors="replace"))) 
        )

        assert found > 50, f"only {found} headers named a test file"


class TestTheScanReadsTheRightThing:
    """The first version read whole headers and produced 28 hits, most nonsense."""

    def test_prose_outside_the_exposes_clause_is_ignored(self):
        tree = ast.parse(
            '"""M.\n\nLLM-Note:\n  Integration: exposes only_this()\n'
            '  Errors: raised when host() refuses\n"""\n\ndef only_this(): ...\n'
        )

        assert _exposed_names(tree) == {"only_this"}

    def test_a_method_counts_as_available(self):
        tree = ast.parse(
            '"""M.\n\nLLM-Note:\n  Integration: exposes Thing with do_it()\n"""\n\n'
            'class Thing:\n    def do_it(self): ...\n'
        )

        assert _exposed_names(tree) <= _available_names(tree)

    def test_a_module_without_the_clause_is_skipped(self):
        tree = ast.parse('"""Just a module."""\n')

        assert _exposed_names(tree) == set()
