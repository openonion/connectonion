"""The examples in the events API describe a trace the agent does not write.

`core/events.py` is where someone learns to hook into a run. Three of its
docstrings — the code people copy — filter the trace like this:

    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution':
        print(f"Tool: {trace['tool_name']} in {trace['timing']:.0f}ms")

Nothing writes `tool_execution`. The entries are `tool_call` and `tool_result`,
their name field is `name`, and their timing field is `timing_ms`. A handler
written from these examples never fires: the `if` is never true, the list
comprehension is always empty, and there is no error to notice — the run
completes and the hook simply had nothing to say.

`tool_execution` came from `core/tool_executor.py`'s module note, which claimed
to write it and did not. The note has since been corrected; these examples had
not been.

An example in a public API is the contract most people actually read. This test
holds the docstrings to the trace: every type they compare against must be a
type something writes, and every field they read must exist on that entry.
"""

import ast
import re
from pathlib import Path

import pytest

from connectonion.core import events


SOURCE = Path(events.__file__).read_text()
PACKAGE = Path(events.__file__).resolve().parents[2] / "connectonion"


def _types_written() -> set:
    """Every 'type' literal the package puts into a trace entry."""
    written = set()
    for path in PACKAGE.rglob("*.py"):
        for m in re.finditer(r"""['"]type['"]\s*:\s*['"]([a-z_]+)['"]""", path.read_text()):
            written.add(m.group(1))
    return written


def _types_compared_in_docstrings() -> set:
    """Every type literal an events.py docstring tells a reader to match."""
    compared = set()
    tree = ast.parse(SOURCE)
    for node in ast.walk(tree):
        doc = ast.get_docstring(node) if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) else None
        if not doc:
            continue
        compared.update(re.findall(r"""\['type'\]\s*==\s*'([a-z_]+)'""", doc))
    return compared


class TestTheTypesExist:

    def test_the_examples_name_types_something_writes(self):
        written = _types_written()
        compared = _types_compared_in_docstrings()

        assert compared, "no example filters the trace — has this file changed shape?"
        assert compared <= written, (
            f"events.py teaches readers to match {sorted(compared - written)}, "
            f"which nothing writes"
        )

    def test_tool_execution_is_gone(self):
        """The specific name that was wrong, so a revert is loud."""
        assert "tool_execution" not in SOURCE


class TestTheFieldsExist:
    """A type that exists is not enough — the examples also read fields off it."""

    TOOL_RESULT_FIELDS = {"args", "id", "name", "result", "status",
                          "timing_ms", "tool_id", "ts", "type"}

    def test_every_field_the_examples_read_is_on_the_entry(self):
        fields = set()
        tree = ast.parse(SOURCE)
        for node in ast.walk(tree):
            doc = ast.get_docstring(node) if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) else None
            if not doc or "tool_result" not in doc:
                continue
            # t['field'] / trace['field'] on the lines that talk about tools
            fields.update(re.findall(r"""\b(?:t|trace)\['([a-z_]+)'\]""", doc))

        unknown = fields - self.TOOL_RESULT_FIELDS
        assert not unknown, f"the examples read {sorted(unknown)}, which a tool entry has not"

    def test_the_old_field_names_are_gone(self):
        assert "tool_name" not in SOURCE, "tool entries carry `name`, not `tool_name`"
        assert "['timing']" not in SOURCE, "tool entries carry `timing_ms`"
