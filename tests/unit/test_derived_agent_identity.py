"""A deployed agent's identity is derived, not minted on the machine.

Letting the server mint one on first boot gives an address nobody can know in
advance and nobody can recover once the disk is gone — #306's failure mode moved
up a level, from "changes every deploy" to "changes every machine", which is
rarer and therefore worse: it is discovered during an outage.
openonion/connectonion#396
"""

import base64
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts
from connectonion.cli.commands import server_commands as sc


PHRASE = ("abandon abandon abandon abandon abandon abandon "
          "abandon abandon abandon abandon abandon about")


@pytest.fixture
def operator(tmp_path, monkeypatch):
    """An operator identity in ~/.co, which is where a server's keys come from."""
    monkeypatch.setattr(sc.Path, "home", staticmethod(lambda: tmp_path))
    co = tmp_path / ".co"
    co.mkdir(parents=True)
    monkeypatch.setattr("connectonion.address.load",
                        lambda d: {"seed_phrase": PHRASE, "address": "0xoperator"})
    return tmp_path


class TestTheAddressIsKnowableInAdvance:
    def test_the_same_name_always_gives_the_same_address(self, operator):
        first = sc.derived_agent_identity("customer-bot")
        second = sc.derived_agent_identity("customer-bot")

        assert first["address"] == second["address"]

    def test_a_different_name_is_a_different_agent(self, operator):
        assert (sc.derived_agent_identity("customer-bot")["address"]
                != sc.derived_agent_identity("linkedin-bot")["address"])

    def test_the_key_is_a_real_ed25519_seed(self, operator):
        from nacl.signing import SigningKey

        identity = sc.derived_agent_identity("customer-bot")

        assert len(identity["key_bytes"]) == 32
        derived = "0x" + bytes(SigningKey(identity["key_bytes"]).verify_key).hex()
        assert derived == identity["address"]

    def test_without_a_phrase_there_is_nothing_to_derive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc.Path, "home", staticmethod(lambda: tmp_path / "empty"))
        monkeypatch.setattr("connectonion.address.load", lambda d: None)
        monkeypatch.setattr(
            "connectonion.cli.commands.keys_commands._find_co_dir", lambda: None)

        assert sc.derived_agent_identity("customer-bot") is None


class TestSeedingTheServer:
    def _steps(self, **kwargs):
        sent = []

        def fake_ssh(target, command, timeout=300):
            sent.append(command)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._ensure_setup("co@h", "my-agent", "agent.py", 99, None, None, **kwargs)
        return "\n".join(sent)

    def test_the_key_travels_over_ssh_not_in_the_tarball(self):
        """.co/keys is excluded from the rsync, like admins.txt."""
        identity = {"address": "0xabc", "key_bytes": b"\x01" * 32}

        script = self._steps(agent_identity=identity)

        assert base64.b64encode(identity["key_bytes"]).decode() in script
        assert "/.co/keys" in script

    def test_an_existing_identity_is_never_overwritten(self):
        """An agent given its own key — by --own-identity, or by an older deploy
        that let it mint one — keeps it. Overwriting an identity is not a thing
        a deploy may do."""
        script = self._steps(agent_identity={"address": "0xabc",
                                             "key_bytes": b"\x01" * 32})

        assert "if [ ! -f" in script
        assert "agent.key" in script

    def test_the_key_file_is_not_world_readable(self):
        script = self._steps(agent_identity={"address": "0xabc",
                                             "key_bytes": b"\x01" * 32})

        assert "chmod 600" in script

    def test_nothing_is_written_when_the_agent_owns_its_identity(self):
        script = self._steps(agent_identity=None)

        assert "agent.key" not in script
