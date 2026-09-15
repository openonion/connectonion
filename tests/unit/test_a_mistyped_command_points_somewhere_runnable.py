"""A mistyped command ends at something you can run, not at `--help`.

Click already answers a near-miss with "Did you mean 'lark'?" — but the next
step printed underneath was always `co --help`, for every typo, whether or not a
candidate had just been named. Two problems with that, both measured:

  * when Click *does* know the answer, the tip throws it away. The reader is
    told the right word in one line and sent to a flag in the next.
  * when Click does *not* know — `co like`, `co lisen`, both too far by edit
    distance to match anything — `co --help` is a boxed, paginated screen of
    groups. `co commands` prints all 199 commands one per line with a summary,
    which is the shape something reading this output can actually use.

So: name the candidate when there is one, and name the command that lists
everything when there is not.
"""

import subprocess
import sys

import pytest

CO = [sys.executable, "-m", "connectonion.cli.main"]


def run(*args, home=None):
    env = {"PATH": "/usr/bin:/bin", "CO_TIPS": "on"}
    if home:
        env["HOME"] = str(home)
    done = subprocess.run(CO + list(args), capture_output=True, text=True, env=env)
    return done.returncode, done.stdout + done.stderr


@pytest.mark.parametrize("typo,wanted", [
    ("larc", "co lark"),
    ("feishoo", "co feishu"),
    ("skil", "co skills"),
    ("recieve", None),          # a subcommand typo; checked separately below
])
def test_a_near_miss_names_the_command_it_guessed(typo, wanted, tmp_path):
    if wanted is None:
        pytest.skip("covered by test_a_subcommand_typo_stays_inside_its_group")
    code, out = run(typo, home=tmp_path)

    assert code == 2
    assert f"Next: {wanted}" in out, f"the tip should carry the guess, got:\n{out}"


@pytest.mark.parametrize("typo", ["like", "lisen", "zzzzzz"])
def test_no_guess_points_at_the_list_of_everything(typo, tmp_path):
    """`co --help` is a screen of groups; `co commands` is every command, one per line."""
    code, out = run(typo, home=tmp_path)

    assert code == 2
    assert "Next: co commands" in out, f"got:\n{out}"


def test_a_subcommand_typo_stays_inside_its_group(tmp_path):
    """`co lark recieve` is a lark problem; sending the reader to the root list
    would make them find their way back down again."""
    code, out = run("lark", "recieve", home=tmp_path)

    assert code == 2
    assert "Next: co lark receive" in out, f"got:\n{out}"


def test_there_is_still_exactly_one_next_step(tmp_path):
    code, out = run("like", home=tmp_path)

    assert out.count("Next:") == 1


def test_the_command_that_lists_everything_exists_and_is_listed(tmp_path):
    """A tip naming a command that does not exist is the worst of both worlds."""
    code, out = run("commands", home=tmp_path)

    assert code == 0
    assert "co commands" in out, "it has to list itself, or the tip is a dead end"
    assert len(out.splitlines()) > 50
