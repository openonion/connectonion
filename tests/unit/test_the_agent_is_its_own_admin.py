"""The one identity that may grant admin can reach the command that grants it.

`load_admins()` says what it intends:

    # Self address is always admin (from project's .co/address.json)

and then reads `.co/address.json` — a file nothing writes any more. Identity
lives in `.co/keys/`. `get_self_address()` was corrected for exactly this
(openonion/oo-chat#28, where paid onboarding could not succeed because the
payment address came back None); `load_admins` was not, so the two disagree
about who the agent is.

Measured on a project that has been run once, so its keys exist:

    self address    0x530c85d3641cff867d
    is_super_admin  True
    is_admin        False

The admin socket gates in that order:

    if not trust_agent.is_admin(agent_address):        # ws_admin.py:103
        forbidden: admin only
    ...
    elif msg_type == "ADMIN_ADD":
        if not trust_agent.is_super_admin(...):        # ws_admin.py:147

So the only super-admin is refused at the outer gate, and ADMIN_ADD and
ADMIN_REMOVE are unreachable by anyone at all — including the account they
were written for.

Third time this shape has turned up in this release: a gate compared against a
value the resolver never produces for that identity (#579 for the approval
dialog, #614 for CONNECT). The fix is the same each time — ask the resolver
everyone else asks.

No access widens. Signing as the agent's own address requires its private key,
which lives with the agent; anyone holding it already controls the process.
"""

from pathlib import Path

import pytest

from connectonion import address
from connectonion.network.trust import tools


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project whose agent has run once, so `.co/keys/` exists."""
    co = tmp_path / ".co"
    co.mkdir()
    data = address.generate()
    address.save(data, co)
    monkeypatch.chdir(tmp_path)
    return co, data["address"]


class TestTheAgentCountsAsItsOwnAdmin:

    def test_is_admin_agrees_with_is_super_admin(self, project):
        co, me = project

        assert tools.is_super_admin(me, co), "the fixture is not what it claims"
        assert tools.is_admin(me, co), (
            "the only super-admin is not an admin, so ws_admin's outer gate "
            "refuses it before ADMIN_ADD is ever reached"
        )

    def test_the_self_address_is_in_the_loaded_set(self, project):
        co, me = project

        assert me in tools.load_admins(co)


class TestNobodyElseIsLetIn:

    def test_a_stranger_is_still_not_an_admin(self, project):
        co, _ = project

        assert not tools.is_admin("0x" + "c" * 64, co)

    def test_the_file_still_decides_for_everyone_else(self, project):
        co, me = project
        colleague = "0x" + "d" * 64
        (co / "admins.txt").write_text(colleague + "\n")

        admins = tools.load_admins(co)
        assert colleague in admins
        assert me in admins


class TestTheOldFileStillWorks:
    """A project made before keys moved has address.json and nothing else."""

    def test_address_json_is_still_honoured(self, tmp_path, monkeypatch):
        import json

        co = tmp_path / ".co"
        co.mkdir()
        legacy = "0x" + "e" * 64
        (co / "address.json").write_text(json.dumps({"address": legacy}))
        monkeypatch.chdir(tmp_path)

        assert legacy in tools.load_admins(co)


class TestNoIdentityAtAll:

    def test_an_unrun_project_has_no_self_admin(self, tmp_path, monkeypatch):
        """`.co/keys/` appears on first run; before that there is nobody to add."""
        co = tmp_path / ".co"
        co.mkdir()
        monkeypatch.chdir(tmp_path)

        assert tools.load_admins(co) == set()
