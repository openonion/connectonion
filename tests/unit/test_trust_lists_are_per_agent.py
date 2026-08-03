"""Whose whitelist is it.

`admins.txt` was moved out of `~/.co/` and beside the agent's own identity,
because one machine hosting two agents meant making someone an admin of one
made them an admin of both. The other three lists — whitelist, contacts,
blocklist — were left on the old global path.

Whitelist is the one that grants. `is_whitelisted()` is a real allow, so
promoting an address while poking at a throwaway agent silently promotes it on
the production agent running on the same box. Nothing in either agent's
directory records that it happened.

These tests put two agents in two directories and check that what one grants,
the other has never heard of.
"""

import importlib
from pathlib import Path

import pytest

tools = importlib.import_module('connectonion.network.trust.tools')


STRANGER = '0x' + 'c' * 64


@pytest.fixture
def two_agents(tmp_path, monkeypatch):
    """Two agent directories, the way one machine hosting two agents looks."""
    a, b = tmp_path / 'agent-a', tmp_path / 'agent-b'
    (a / '.co').mkdir(parents=True)
    (b / '.co').mkdir(parents=True)
    # A $HOME of its own, so a stray real ~/.co cannot make these pass.
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    return a, b


def test_a_whitelist_grant_does_not_reach_the_other_agent(two_agents, monkeypatch):
    a, b = two_agents

    monkeypatch.chdir(a)
    tools.promote_to_whitelist(STRANGER)
    assert tools.is_whitelisted(STRANGER), "the grant did not take effect where it was made"

    monkeypatch.chdir(b)
    assert not tools.is_whitelisted(STRANGER), (
        "an address whitelisted on one agent is whitelisted on every agent "
        "sharing the machine"
    )


def test_a_contact_does_not_reach_the_other_agent(two_agents, monkeypatch):
    a, b = two_agents

    monkeypatch.chdir(a)
    tools.promote_to_contact(STRANGER)
    assert tools.is_contact(STRANGER)

    monkeypatch.chdir(b)
    assert not tools.is_contact(STRANGER)


def test_a_block_does_not_reach_the_other_agent(two_agents, monkeypatch):
    """Blocking leaks in the safe direction, and still should not leak.

    An operator who blocks someone from a public agent has not asked to cut
    them off from a private one they also run.
    """
    a, b = two_agents

    monkeypatch.chdir(a)
    tools.block(STRANGER)
    assert tools.is_blocked(STRANGER)

    monkeypatch.chdir(b)
    assert not tools.is_blocked(STRANGER)


def test_the_list_files_live_beside_the_agent(two_agents, monkeypatch):
    """Where they are is the whole fix — visible in the agent's own directory,
    next to the identity they are compared against."""
    a, _ = two_agents

    monkeypatch.chdir(a)
    tools.promote_to_whitelist(STRANGER)

    assert (a / '.co' / 'whitelist.txt').exists()
    assert not (Path.home() / '.co' / 'whitelist.txt').exists()


class TestTheOldGlobalListsAreNotLostSilently:
    """Upgrading moves where these live. Nobody should find out from a lockout.

    An operator who whitelisted a colleague in ~/.co/whitelist.txt gets, after
    the upgrade, a colleague who cannot connect and no reason anywhere. The
    entries are not read any more — reading them would be the bug — so the one
    thing left to do is say where they went.
    """

    def test_a_legacy_list_with_entries_is_announced_once(self, two_agents,
                                                          monkeypatch, capsys):
        a, _ = two_agents
        legacy = Path.home() / '.co'
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / 'whitelist.txt').write_text(STRANGER + '\n')

        monkeypatch.setattr(tools, '_announced_legacy', set())
        monkeypatch.chdir(a)
        tools.is_whitelisted(STRANGER)
        tools.is_whitelisted(STRANGER)
        tools.is_whitelisted(STRANGER)

        out = capsys.readouterr().out
        assert str(legacy / 'whitelist.txt') in out
        # The line names both paths, so count the lines, not the filename.
        assert out.count('[trust]') == 1, "said once, not on every check"

    def test_nothing_is_said_when_there_is_no_legacy_file(self, two_agents,
                                                          monkeypatch, capsys):
        a, _ = two_agents
        monkeypatch.setattr(tools, '_announced_legacy', set())
        monkeypatch.chdir(a)
        tools.is_whitelisted(STRANGER)
        assert capsys.readouterr().out == ""


class TestTheDeployedAgentRunsFromItsOwnDirectory:
    """The line that makes all of the above work in production.

    Scoping the lists to the agent means resolving them from the working
    directory. On a deployed agent that only holds because the unit file says
    so. Drop `WorkingDirectory` and every list resolves under `/`, quietly
    empty: the whitelist stops granting, the blocklist stops blocking, and
    nothing anywhere says why.

    Nothing pinned this before. It was one uncommented line in a unit template.
    """

    def test_the_unit_pins_the_working_directory(self):
        from connectonion.cli.commands.deploy_to_server import _unit_text, SRV

        unit = _unit_text("ledger", "agent.py")

        assert f"WorkingDirectory={SRV}/ledger" in unit, (
            "without this the agent's trust lists resolve under / and are "
            "silently empty"
        )

    def test_the_working_directory_is_where_the_lists_are(self):
        """Same directory the deploy puts .co/ in — one place, not two."""
        from connectonion.cli.commands.deploy_to_server import _unit_text, SRV

        unit = _unit_text("ledger", "agent.py")
        workdir = next(l.split('=', 1)[1] for l in unit.splitlines()
                       if l.startswith('WorkingDirectory='))

        assert f"{workdir}/.co" == f"{SRV}/ledger/.co"


class TestCoTrustSaysWhereItLooked:
    """Four empty lists and no agent look identical, and mean opposite things."""

    def test_no_agent_here_is_not_reported_as_empty_lists(self, tmp_path,
                                                          monkeypatch, capsys):
        from connectonion.cli.commands.trust_commands import handle_trust_list

        monkeypatch.chdir(tmp_path)          # no .co/ in it
        handle_trust_list()

        out = capsys.readouterr().out
        assert 'No agent here' in out
        assert 'Whitelist' not in out, (
            "listing empty sections here reads as 'my whitelist was wiped'"
        )

    def test_a_real_agent_still_lists_its_entries(self, tmp_path, monkeypatch,
                                                  capsys):
        from connectonion.cli.commands.trust_commands import handle_trust_list

        co = tmp_path / '.co'
        co.mkdir()
        (co / 'whitelist.txt').write_text('0xabc\n')
        monkeypatch.chdir(tmp_path)

        handle_trust_list()

        out = capsys.readouterr().out
        assert 'Whitelist' in out
        assert '0xabc' in out
