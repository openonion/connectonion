"""A command that refuses names exactly one next command, not two.

Click prints its own usage errors and exits 2 without passing through our
`invoke`, so `_OneSuggestion.main` adds `Next: co <group> --help` for those —
otherwise a mistyped argument gets "Try --help", which is a flag, not a command.
That safety net is right.

It was catching too much. Exit code 2 is also what a handler raises when it
refuses on purpose, and those handlers have already printed a precise next step.
The result was two tips in one run: the useful one on stdout and a generic one on
stderr, which an agent merging streams reads first.

The skill this is audited against (`useful_skills/cli-skill-design`) puts it
plainly: "One next step. Two tips is a fork, and the agent resolves a fork by
guessing."

So: if the command already named a next step, the net stays out of the way. If it
named none, the net still fires.
"""

import subprocess
import sys

import pytest

from connectonion.cli.commands import command_tips

CO = [sys.executable, "-m", "connectonion.cli.main"]


def run(*args, home=None):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "CO_TIPS": "on"}
    if home:
        env["HOME"] = str(home)
    done = subprocess.run(CO + list(args), capture_output=True, text=True, env=env)
    return done.returncode, done.stdout, done.stderr


@pytest.fixture(autouse=True)
def _forget_tips():
    command_tips.forget_next_step_named()
    yield
    command_tips.forget_next_step_named()


def test_a_deliberate_refusal_prints_one_tip_not_two(tmp_path):
    """`co env set LARK_APP_SECRET x` refuses and names `co auth lark`.

    Before this, stderr also carried `Next: co --help`, so a caller doing
    `2>&1` — which is most of them — saw the useless one first.
    """
    code, out, err = run("env", "set", "LARK_APP_SECRET", "x", home=tmp_path)

    assert code == 2
    assert "Next: co auth lark" in out
    assert "Next: co --help" not in err, "the generic tip must not double the real one"
    assert (out + err).count("Next:") == 1


def test_a_real_usage_error_still_gets_a_next_command(tmp_path):
    """The case the net exists for: Click exits 2 before any handler runs.

    A missing argument never reaches a handler, so nothing has named a next
    command and the generic tip is the only thing standing between the caller
    and "Try --help", which is a flag rather than something to run.

    It lands as `co --help` rather than `co env --help` because the root group's
    `main` is what catches this, not the group's. Less precise than it could be,
    and out of scope here — this test holds the net in place, not its aim.
    """
    code, out, err = run("env", "set", home=tmp_path)

    assert code == 2
    assert "Next: co" in err and "--help" in err


def test_the_flag_tracks_whether_a_next_step_was_named():
    """The mechanism, asserted directly rather than inferred from output."""
    assert command_tips.next_step_already_named() is False

    command_tips.print_tip("nothing actionable here")
    assert command_tips.next_step_already_named() is False, (
        "a message with no next command must not suppress the net"
    )

    command_tips.print_tip("Next: co auth lark")
    assert command_tips.next_step_already_named() is True


def test_forgetting_resets_it():
    command_tips.print_tip("Next: co env")
    command_tips.forget_next_step_named()

    assert command_tips.next_step_already_named() is False
