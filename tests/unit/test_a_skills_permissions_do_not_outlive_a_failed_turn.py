"""A skill's permissions end with the turn, including a turn that ends badly.

The module says so in its own docstring:

    Permission Scope:
    - Set when skill invoked (tied to turn number)
    - Auto-clears when turn ends (security)
    - Only affects current turn (no permission escalation)

`cleanup_scope` is `@on_complete`, and `on_complete` is a plain statement after
the loop in `Agent.input`:

    result = self._run_iteration_loop(max_iterations or self.max_iterations)
    ...
    self._invoke_events('on_complete')

No `finally`. A turn that raises never reaches it, and the grant stays:

    turn 1, during      ['Bash(rm -rf *)', 'write']
      ... the turn raises
    turn 2, at the start['Bash(rm -rf *)', 'write']      <- still there

The comment in `_grant_skill_permissions` names the trigger: "on_complete is not
in a finally block, so a turn that raises — a rejected approval does exactly
that — never restores and leaves its snapshot behind". So the most ordinary way
to reach it is the operator answering "no" to a dialog. They refuse, and the
skill's permissions survive their refusal for the rest of the session.

Restoring at the *start* of a turn is what fixes it: the plugin's own
`@after_user_input` runs on every turn, before anything is granted, and a
snapshot left by an earlier turn is exactly the evidence that its restore never
ran. Doing it there rather than wrapping the turn in `try/finally` keeps
`on_complete` meaning "the turn finished", which the logger and the eval writer
both rely on.
"""

import pytest

from connectonion.useful_plugins.skills import (
    _grant_skill_permissions,
    _restore_permissions,
    handle_skill_invocation,
)


class FakeAgent:
    """Enough of an Agent for the permission bookkeeping."""

    def __init__(self, turn=1):
        self.current_session = {"turn": turn, "permissions": {}, "messages": []}
        self.logger = None


def _a_turn_that_raised(turn=1):
    """An agent left as a turn that died mid-flight leaves it."""
    agent = FakeAgent(turn=turn)
    _grant_skill_permissions(agent, "risky", ["Bash(rm -rf *)", "write"])
    return agent                       # no _restore_permissions: the turn raised


class TestTheNextTurnStartsClean:

    def test_the_grant_does_not_survive(self):
        agent = _a_turn_that_raised()

        agent.current_session["turn"] = 2
        handle_skill_invocation(agent)

        assert "Bash(rm -rf *)" not in agent.current_session["permissions"]

    def test_nothing_of_the_skill_survives(self):
        agent = _a_turn_that_raised()

        agent.current_session["turn"] = 2
        handle_skill_invocation(agent)

        assert agent.current_session["permissions"] == {}

    def test_the_stale_snapshot_is_gone(self):
        """Left behind, it becomes the baseline the next skill restores to."""
        agent = _a_turn_that_raised()

        agent.current_session["turn"] = 2
        handle_skill_invocation(agent)

        assert "_permission_snapshot" not in agent.current_session

    def test_an_operator_approval_from_the_failed_turn_is_kept(self):
        """Theirs, not the skill's — the same rule `_restore_permissions` follows."""
        agent = _a_turn_that_raised()
        agent.current_session["permissions"]["read_file"] = {
            "allowed": True, "source": "user",
        }

        agent.current_session["turn"] = 2
        handle_skill_invocation(agent)

        assert "read_file" in agent.current_session["permissions"]


class TestTheTurnThatIsStillRunning:
    """Only a snapshot from an *earlier* turn is evidence of a failed restore."""

    def test_the_current_turn_keeps_its_grant(self):
        agent = _a_turn_that_raised()

        handle_skill_invocation(agent)          # same turn, still going

        assert "Bash(rm -rf *)" in agent.current_session["permissions"]

    def test_and_keeps_its_snapshot(self):
        agent = _a_turn_that_raised()

        handle_skill_invocation(agent)

        assert agent.current_session["_permission_snapshot"]["turn"] == 1


class TestWhatMustNotChange:

    def test_a_turn_that_ended_properly_is_unaffected(self):
        agent = _a_turn_that_raised()
        _restore_permissions(agent)             # on_complete did run

        agent.current_session["turn"] = 2
        handle_skill_invocation(agent)

        assert agent.current_session["permissions"] == {}

    def test_an_agent_that_never_ran_a_skill(self):
        agent = FakeAgent(turn=3)

        handle_skill_invocation(agent)

        assert agent.current_session["permissions"] == {}

    def test_restore_still_clears_within_one_turn(self):
        agent = _a_turn_that_raised()

        _restore_permissions(agent)

        assert agent.current_session["permissions"] == {}
