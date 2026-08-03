"""The examples in the READMEs call the API the package actually has.

Two shapes in `docs/README.md`'s "Real-World" section, both of which raise
before doing anything:

    agent = Agent("customer_support", tools=[send_email],
                  instructions="You help users …")
    response = agent("Send a welcome email to alice@example.com")

`Agent.__init__` takes `system_prompt`, not `instructions`, and it has no
`**kwargs` to absorb the difference:

    TypeError: Agent.__init__() got an unexpected keyword argument 'instructions'

And `Agent` defines no `__call__`, so the second line raises too. The method is
`agent.input(...)`.

Someone reading the README meets these in the section that promises real-world
usage. They are the first thing a person runs, and neither line survives.

The tests below are the general rule rather than these two fixes: every keyword
a documented call passes must exist on the callable, and no example may call an
agent instance. Both are cheap to check and neither can drift silently again.
"""

import inspect
import re
from pathlib import Path

import pytest

import connectonion as co


REPO = Path(__file__).resolve().parents[2]
DOCS = [REPO / "README.md", REPO / "docs" / "README.md"]
SOURCES = {p: p.read_text(encoding="utf-8") for p in DOCS if p.exists()}


def _kwargs_passed_to(name: str, text: str) -> set:
    """Keyword names used in `name(...)` calls in a markdown file."""
    used = set()
    for call in re.findall(rf"\b{name}\(([^)]*)\)", text, re.S):
        used.update(re.findall(r"(\w+)\s*=", call))
    return used


CALLABLES = {
    "Agent": co.Agent.__init__,
    "llm_do": co.llm_do,
    "host": co.host,
}


@pytest.mark.parametrize("path", list(SOURCES))
@pytest.mark.parametrize("name", sorted(CALLABLES))
def test_every_documented_keyword_exists(name, path):
    fn = CALLABLES[name]
    signature = inspect.signature(fn)
    accepts_anything = any(p.kind is inspect.Parameter.VAR_KEYWORD
                           for p in signature.parameters.values())
    if accepts_anything:
        pytest.skip(f"{name} takes **kwargs — any keyword is forwarded")

    unknown = sorted(_kwargs_passed_to(name, SOURCES[path]) - set(signature.parameters))

    assert not unknown, (
        f"{path.relative_to(REPO)} passes {unknown} to {name}(), which takes "
        f"{sorted(signature.parameters)} and has no **kwargs — the example "
        f"raises TypeError before it does anything"
    )


@pytest.mark.parametrize("path", list(SOURCES))
def test_no_example_calls_an_agent_instance(path):
    """`Agent` has no __call__; the method is .input()."""
    assert "__call__" not in co.Agent.__dict__, (
        "Agent became callable — this test and the examples can be relaxed"
    )

    # `agent("…")` / `monitor("…")` at the start of a line, with a string
    # argument. Lower-case only: `Agent("name", …)` is the constructor, and a
    # capitalised name is a class rather than an instance.
    offenders = re.findall(r"^\s*(?:\w+\s*=\s*)?([a-z_]*(?:agent|monitor|assistant))\(\s*[\"']",
                           SOURCES[path], re.M)

    assert not offenders, (
        f"{path.relative_to(REPO)} calls {sorted(set(offenders))} directly; Agent instances "
        f"are not callable — the example raises TypeError"
    )
