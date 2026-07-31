"""An agent introduces itself by the name its operator gave it.

`host.yaml`'s `name:` never reached the network. The metadata came from the
Agent object's own name, and the co-ai template hardcodes `name="oo"` — so every
agent built from it called itself "oo" over `/info`, in the relay's directory
and in the ANNOUNCE profile, whatever the project was called.
openonion/connectonion#436
"""

import pytest

from connectonion.network.host import server


class _Tools:
    def names(self):
        return []


class _Llm:
    model = "co/gemini-3.6-flash"


class _Agent:
    name = "oo"
    tools = _Tools()
    skills = []
    llm = _Llm()


class TestTheNameOnTheWire:
    def test_host_yaml_wins_over_the_agent_object(self):
        metadata, _ = server._extract_agent_metadata(lambda: _Agent(), "naturewill")

        assert metadata["name"] == "naturewill"

    def test_without_one_the_agents_own_name_stands(self):
        """A library user who never wrote a host.yaml keeps what they had."""
        metadata, _ = server._extract_agent_metadata(lambda: _Agent())

        assert metadata["name"] == "oo"

    def test_an_empty_name_does_not_win(self):
        """`name:` present but blank is not a name."""
        metadata, _ = server._extract_agent_metadata(lambda: _Agent(), "")

        assert metadata["name"] == "oo"

    def test_the_profile_published_to_the_relay_carries_it(self):
        """The directory entry is built from the same metadata, so this is the
        name other people see when they look the agent up."""
        metadata, _ = server._extract_agent_metadata(lambda: _Agent(), "naturewill")
        metadata["address"] = "0x" + "a" * 64

        profile = server._build_agent_profile(metadata)

        assert profile["alias"] == "naturewill"


class TestHostReadsItFromTheConfig:
    def test_host_passes_the_configured_name(self):
        """It is read from host.yaml already — it just was not being used."""
        import inspect

        src = inspect.getsource(server.host)

        assert '_extract_agent_metadata(create_agent, config.get("name"))' in src

    def test_the_config_loader_keeps_the_whole_file(self, tmp_path):
        """No allowlist to add `name` to: load_host_config merges the file."""
        from connectonion.network.host.config import load_host_config

        co = tmp_path / ".co"
        co.mkdir()
        (co / "host.yaml").write_text("name: naturewill\nentrypoint: agent.py\n")

        assert load_host_config(co)["name"] == "naturewill"
