"""The Quick Start in docs/network/host.md runs as written.

Re-tested on 1.8.8b9: copied word for word into agent.py, it died with
`NameError: name 'translate' is not defined` -- the example handed the agent a
tool it never defined. The same file ships in the wheel as
connectonion/docs/network/host.md and is linked into co ai's prompts, so the
broken example was also what the coding agent learned from.

This executes the page's first Python block with only `host()` stubbed: the
stub builds the agent from the factory the page passes, which is what the real
host() does for every session.
"""

import re
from pathlib import Path

import connectonion
from connectonion.network.host import server as host_server

HOST_MD = Path(__file__).resolve().parents[2] / "docs" / "network" / "host.md"


def _quick_start_code() -> str:
    page = HOST_MD.read_text(encoding="utf-8")
    section = page.split("## Quick Start", 1)[1]
    return re.search(r"```python\n(.*?)```", section, re.S).group(1)


def test_the_quick_start_defines_everything_it_uses(monkeypatch):
    built = []

    def host(create_agent, *args, **kwargs):
        built.append(create_agent())

    monkeypatch.setattr(connectonion, "host", host)
    monkeypatch.setattr(host_server, "host", host)

    exec(compile(_quick_start_code(), str(HOST_MD), "exec"), {"__name__": "__main__"})

    assert len(built) == 1
    agent = built[0]
    assert agent.name == "translator"
    assert agent.tools.get("translate") is not None


def test_the_banner_it_shows_matches_the_agent(monkeypatch):
    """The page's sample output said "12 tools" for a one-tool agent."""
    page = HOST_MD.read_text(encoding="utf-8")
    output = page.split("## Quick Start", 1)[1].split("**Output:**", 1)[1]

    assert "1 tool" in output.split("```")[1]
