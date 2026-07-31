"""An agent is named by the project it is, not by the template it came from.

`create_agent()` hardcoded name="oo", so every agent built from the co-ai
template — which is the only template — announced itself as "oo". The author's
own .co/host.yaml says what they called it, in a field named `name`, and it
never reached the network. Three agents in one client list, all "oo".
"""

import textwrap

import pytest

from connectonion.cli.co_ai import agent as co_ai


def co_dir_with(tmp_path, host_yaml: str = None):
    d = tmp_path / ".co"
    d.mkdir()
    if host_yaml is not None:
        (d / "host.yaml").write_text(textwrap.dedent(host_yaml), encoding="utf-8")
    return d


def test_the_name_in_host_yaml_is_the_agent_s_name(tmp_path):
    co_dir = co_dir_with(tmp_path, """
        name: billing
        entrypoint: agent.py
    """)

    assert co_ai.agent_name(co_dir) == "billing"


def test_without_host_yaml_it_falls_back(tmp_path):
    co_dir = co_dir_with(tmp_path, host_yaml=None)

    assert co_ai.agent_name(co_dir) == "oo"


def test_a_host_yaml_without_a_name_falls_back(tmp_path):
    co_dir = co_dir_with(tmp_path, """
        entrypoint: agent.py
        port: 8000
    """)

    assert co_ai.agent_name(co_dir) == "oo"


def test_malformed_host_yaml_does_not_take_the_agent_down(tmp_path):
    # The agent's name is not worth crashing over — a broken host.yaml is
    # reported elsewhere (#381/#422), and here it just means "no name given".
    co_dir = co_dir_with(tmp_path, "name: [unclosed\n")

    assert co_ai.agent_name(co_dir) == "oo"
