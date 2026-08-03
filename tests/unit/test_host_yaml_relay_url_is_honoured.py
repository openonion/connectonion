"""`relay_url` in host.yaml decides which relay the agent announces on.

Every project's `.co/host.yaml` carries the line, under a header that says
"Host configuration — edit these values":

    relay_url: wss://oo.openonion.ai

Editing it does nothing. `load_host_config` applies code parameters over the
file "only if not None", and `host()` alone among them defaults to a real
string:

    port: int = None                        file wins
    trust: … = None                         file wins
    workers: int = None                     file wins
    relay_url: str = DEFAULT_RELAY_URL      file never wins

`python agent.py` calls `host(agent)` without naming a relay, so the default
string is passed as an explicit code parameter and overrides the file every
time.

Measured. A project whose host.yaml said `relay_url: wss://127.0.0.1:9/ws` —
a port that refuses instantly, confirmed with a direct connect
(`ConnectionRefusedError` in 0.0s):

    banner              ✓ relay
    relay errors        none, over 75 seconds
    co call <address>   returned the agent's pwd

It was announcing on the public relay. Nothing said otherwise, because as far
as the process was concerned nothing was wrong.

Whoever points an agent at their own relay this way is on the public one
instead, and the first symptom is whatever they were trying to keep off it.

Passing `relay_url=` to `host()` still wins over the file, and
`relay_url=None` still means no relay at all — kept apart from "not specified"
by a sentinel, because the two used to be the same value and only one of them
should reach the file.
"""

from pathlib import Path

import pytest

from connectonion.network.host.config import load_host_config
from connectonion.network.host.server import DEFAULT_RELAY_URL, UNSET, resolve_relay_url


PRIVATE = "wss://relay.example.internal/ws"


@pytest.fixture
def co_dir(tmp_path):
    co = tmp_path / ".co"
    co.mkdir()
    (co / "host.yaml").write_text(
        f"name: billing\nentrypoint: agent.py\nrelay_url: {PRIVATE}\n")
    return co


class TestTheFileIsRead:

    def test_the_relay_in_host_yaml_is_used(self, co_dir):
        config = load_host_config(co_dir)

        assert resolve_relay_url(UNSET, config) == PRIVATE

    def test_the_other_keys_still_behave(self, co_dir):
        """port and trust already worked this way; this must not change them."""
        (co_dir / "host.yaml").write_text(
            f"name: billing\nport: 9001\ntrust: strict\nrelay_url: {PRIVATE}\n")

        config = load_host_config(co_dir, port=None, trust=None)

        assert config["port"] == 9001
        assert config["trust"] == "strict"


class TestCodeStillWins:

    def test_an_explicit_url_overrides_the_file(self, co_dir):
        config = load_host_config(co_dir)

        assert resolve_relay_url("wss://from-code/ws", config) == "wss://from-code/ws"


class TestTheDefaultStillApplies:

    def test_a_project_with_no_relay_line_gets_the_public_one(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "host.yaml").write_text("name: billing\n")

        assert resolve_relay_url(UNSET, load_host_config(co)) == DEFAULT_RELAY_URL

    def test_no_config_file_at_all(self, tmp_path):
        assert resolve_relay_url(UNSET, load_host_config(tmp_path / ".co")) == DEFAULT_RELAY_URL


class TestTurningItOffStillWorks:
    """`host(agent, relay_url=None)` is how an agent stays off the relay, and it
    has to stay distinguishable from "not specified" — which is what the default
    now means."""

    def test_none_means_no_relay_even_when_the_file_names_one(self, co_dir):
        assert not resolve_relay_url(None, load_host_config(co_dir))

    def test_an_empty_string_in_the_file_also_means_off(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "host.yaml").write_text('name: billing\nrelay_url: ""\n')

        assert not resolve_relay_url(UNSET, load_host_config(co))
