"""Every `tested by [...]` in an LLM-Note header names a file that is there.

The headers exist to orient whoever reads a module next — the field is called
LLM-Note and the codebase writes them deliberately. Measured across the package:

    106 pointers,  48 of them at files that do not exist

Two causes, and they want different treatment:

    25   the tests moved into tests/unit/ and the headers stayed
         tests/test_address.py        ->  tests/unit/test_address.py
         tests/test_llm.py            ->  tests/unit/test_llm.py

    23   no file of that name anywhere
         tests/tui/test_divider.py, tests/prompts/test_assembler.py, …

The first is a fact and was corrected. The second cannot be guessed: matching by
name similarity paired `tests/tui/test_divider.py` with `tests/unit/test_gdrive.py`
and `tests/tui/test_dropdown.py` with `tests/e2e/test_deploy.py`. Replacing a dead
pointer with a confident wrong one is worse than removing it, so those were
removed rather than invented.

(Matching by "which test imports this module" was tried too and is no better for
this purpose: `core/llm.py` is imported by 42 test files, so naming one of them
as *the* test is as arbitrary as the pointer that was already wrong.)
"""

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "connectonion"


def _pointers():
    """(source file, referenced test path) for every tested-by entry."""
    for py in sorted(PACKAGE.rglob("*.py")):
        head = py.read_text(encoding="utf-8", errors="replace")[:4000]
        for group in re.findall(r"tested by \[([^\]]+)\]", head):
            for ref in group.split("|"):
                ref = ref.strip().split(",")[0].strip()
                if ref.startswith("tests/"):
                    yield py, ref


class TestEveryPointerResolves:

    def test_there_are_pointers_to_check(self):
        """If the parser stops matching, this file stops meaning anything."""
        assert list(_pointers()), "no tested-by pointers found — the header format changed"

    def test_they_all_exist(self):
        broken = sorted({
            f"{py.relative_to(REPO)} -> {ref}"
            for py, ref in _pointers() if not (REPO / ref).exists()
        })

        assert broken == [], (
            "LLM-Note headers point at test files that are not there:\n  "
            + "\n  ".join(broken)
        )


class TestTheParserItself:
    """So a future 'fix' cannot make this pass by finding nothing."""

    def test_it_reads_a_single_entry(self, tmp_path):
        assert re.findall(r"tested by \[([^\]]+)\]",
                          "  Dependencies: … | tested by [tests/unit/test_a.py]") == \
            ["tests/unit/test_a.py"]

    def test_it_splits_several(self):
        group = re.findall(r"tested by \[([^\]]+)\]",
                           "tested by [tests/unit/test_a.py | tests/unit/test_b.py]")[0]

        assert [r.strip() for r in group.split("|")] == \
            ["tests/unit/test_a.py", "tests/unit/test_b.py"]

    def test_it_ignores_prose_that_is_not_a_path(self):
        """Some headers say 'no direct tests' rather than naming a file."""
        group = re.findall(r"tested by \[([^\]]+)\]",
                           "tested by [no direct tests (integration only)]")[0]

        assert not group.strip().startswith("tests/")
