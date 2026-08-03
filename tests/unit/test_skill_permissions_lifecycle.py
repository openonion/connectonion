"""What a turn's permissions look like after the skills in it are done.

Two faults in the same two functions.

`_grant_skill_permissions` snapshots the current permissions so they can be put
back. It writes that snapshot into one slot, and a second skill in the same
turn overwrites it — with a state that already contains the first skill's
grants. Restore then returns to "after skill A", and A's patterns are permanent
for the rest of the session. Skills reference other skills; two in a turn is
ordinary.

`_restore_permissions` replaces the whole permissions dict with the snapshot.
Anything the operator approved *during* the skill — the dialog they answered
with "trust this for the session" — is in the live dict and not in the snapshot,
so it is discarded. They approved something and it silently did not stick.

Restore fires once per turn (`@on_complete`), not once per skill, so the first
snapshot is the one that describes where the turn began. That is the one to
keep.
"""

import pytest

from connectonion.useful_plugins.skills import (
    _grant_skill_permissions,
    _restore_permissions,
)


class FakeAgent:
    def __init__(self, permissions=None):
        self.current_session = {'turn': 1, 'permissions': permissions or {}}


class TestNestedSkillsDoNotLeak:

    def test_two_skills_in_one_turn_both_end(self):
        agent = FakeAgent()

        _grant_skill_permissions(agent, 'deploy', ['Bash(rsync *)'])
        _grant_skill_permissions(agent, 'notify', ['Bash(curl *)'])
        _restore_permissions(agent)

        left = set(agent.current_session.get('permissions', {}))
        assert left == set(), (
            f"a skill's permissions outlived the turn: {sorted(left)}"
        )

    def test_the_turn_returns_to_where_it_started(self):
        agent = FakeAgent({'read_file': {'allowed': True, 'source': 'safe'}})

        _grant_skill_permissions(agent, 'a', ['Bash(git *)'])
        _grant_skill_permissions(agent, 'b', ['Bash(npm *)'])
        _restore_permissions(agent)

        assert set(agent.current_session['permissions']) == {'read_file'}

    def test_three_deep_is_no_different(self):
        agent = FakeAgent()

        for name, pattern in [('a', 'Bash(a *)'), ('b', 'Bash(b *)'),
                              ('c', 'Bash(c *)')]:
            _grant_skill_permissions(agent, name, [pattern])
        _restore_permissions(agent)

        assert agent.current_session.get('permissions', {}) == {}


class TestAnApprovalGivenDuringASkillSurvives:
    """The operator answered a dialog. That answer is not the skill's to undo."""

    def test_a_session_approval_is_kept(self):
        agent = FakeAgent()

        _grant_skill_permissions(agent, 'deploy', ['Bash(rsync *)'])
        # What check_approval writes when someone picks "trust for this session".
        agent.current_session['permissions']['bash'] = {
            'allowed': True, 'source': 'user', 'reason': 'approved for session',
            'expires': {'type': 'session_end'},
        }

        _restore_permissions(agent)

        assert 'bash' in agent.current_session['permissions'], (
            "the operator approved something during a skill and it vanished "
            "when the skill cleaned up"
        )
        assert agent.current_session['permissions']['bash']['source'] == 'user'

    def test_the_skills_own_grants_still_go(self):
        """Keeping user approvals must not keep everything."""
        agent = FakeAgent()

        _grant_skill_permissions(agent, 'deploy', ['Bash(rsync *)'])
        agent.current_session['permissions']['bash'] = {
            'allowed': True, 'source': 'user', 'reason': 'approved',
        }

        _restore_permissions(agent)

        remaining = agent.current_session['permissions']
        assert 'bash' in remaining
        assert not any(v.get('source') == 'skill' for v in remaining.values())


class TestATurnThatDiedDoesNotPoisonTheNextOne:
    """`on_complete` is not in a finally block.

        result = self._run_iteration_loop(...)
        ...
        self._invoke_events('on_complete')

    A turn that raises — a rejected approval does exactly that — never restores,
    and leaves its snapshot behind.

    That was self-healing while the snapshot was overwritten by whoever granted
    next. Making the first write win removed the self-healing: the stale
    snapshot would survive, and the following turn would restore to a point two
    turns back. So the snapshot records which turn it describes, and a snapshot
    from an older turn is replaced rather than trusted.
    """

    def test_a_snapshot_from_a_dead_turn_is_not_reused(self):
        agent = FakeAgent()

        # Turn 1 grants and then dies — no restore.
        _grant_skill_permissions(agent, 'deploy', ['Bash(rsync *)'])

        # Turn 2 starts where turn 1 left off, as the session actually does.
        agent.current_session['turn'] = 2
        _grant_skill_permissions(agent, 'notify', ['Bash(curl *)'])
        _restore_permissions(agent)

        left = set(agent.current_session.get('permissions', {}))
        assert 'Bash(curl *)' not in left, "turn 2's own grant outlived turn 2"
        assert left == {'Bash(rsync *)'}, (
            f"turn 2 restored to somewhere that is not where turn 2 began: "
            f"{sorted(left)}"
        )

    def test_two_grants_in_the_same_turn_still_share_one_snapshot(self):
        """The fix for the dead turn must not undo the fix for nesting."""
        agent = FakeAgent()

        _grant_skill_permissions(agent, 'a', ['Bash(a *)'])
        _grant_skill_permissions(agent, 'b', ['Bash(b *)'])
        _restore_permissions(agent)

        assert agent.current_session.get('permissions', {}) == {}
