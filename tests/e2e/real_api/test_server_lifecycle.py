"""`co server new` → deploy → iterate → destroy, against a real machine.

Skipped unless CO_E2E_SERVERS=1: a run creates a GCE instance, spends credit and
takes several minutes.

    CO_E2E_SERVERS=1 pytest tests/e2e/real_api/test_server_lifecycle.py -v -s

Every step here is one that shipped broken and passed the unit tests anyway:

- `co server check` answered "Permission denied" on a machine we had just been
  charged for, because ssh was never told about the derived key
- the key was derived from whichever project directory you stood in, so
  deploying from a second project was locked out of the first one's machine
- our copy of the key wrote one half without the other, producing a pair ssh
  refuses with "contents do not match public"
- a skill in .co/skills/ never reached the server, because the rsync filter
  excluded all of .co/

The unit tests could not have caught any of them. They all live between our code
and ssh, and the only way to see them is to talk to a real box.
"""

import os
import subprocess
import textwrap
import uuid

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("CO_E2E_SERVERS") != "1",
                       reason="creates a real server and spends credit"),
]

SERVER = "e2e-" + uuid.uuid4().hex[:6]
AGENT = "e2e-agent"


def co(*args, timeout=900, check=True):
    result = subprocess.run(["co", *args], capture_output=True, text=True, timeout=timeout)
    print(f"\n$ co {' '.join(args)}\n{result.stdout}{result.stderr}")
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module")
def server():
    co("server", "new", SERVER, "--yes", timeout=900)
    try:
        yield SERVER
    finally:
        co("server", "destroy", SERVER, "--yes", timeout=600, check=False)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """An agent carrying a skill, because a skill is the thing that did not ship."""
    root = tmp_path_factory.mktemp("e2e")
    subprocess.run(["co", "create", AGENT], cwd=root, check=True, capture_output=True)
    path = root / AGENT

    skill = path / ".co" / "skills" / "greet-visitor"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: greet-visitor
        description: Greet someone by name.
        ---

        VERSION_MARKER_ONE
        """))
    return path


def test_a_created_server_passes_its_own_preflight(server):
    """The command that answered "Permission denied (publickey)" for a machine
    the account had just been charged $180 for."""
    assert "ready to deploy to" in co("server", "check", server).stdout


def test_the_skill_travels_with_the_deploy(server, project):
    """.co/skills/ has to reach the server while the rest of .co/ stays put:
    the skills are code, and everything else in there is the agent's state."""
    subprocess.run(["co", "deploy", "--to", server], cwd=project, check=True,
                   capture_output=True, timeout=900)

    remote = co("server", "ssh", server,
                f"cat /srv/{AGENT}/.co/skills/greet-visitor/SKILL.md").stdout
    assert "VERSION_MARKER_ONE" in remote

    assert co("server", "ssh", server,
              f"systemctl is-active {AGENT}").stdout.strip() == "active"


def test_a_second_deploy_updates_the_skill_and_keeps_the_state(server, project):
    """The iteration case. State under .co/ must survive a redeploy — that is
    the whole promise of keeping it out of the sync — while a changed skill must
    not."""
    co("server", "ssh", server,
       f"echo STATE_FROM_FIRST_DEPLOY > /srv/{AGENT}/.co/e2e-state.txt")

    skill = project / ".co" / "skills" / "greet-visitor" / "SKILL.md"
    skill.write_text(skill.read_text().replace("VERSION_MARKER_ONE", "VERSION_MARKER_TWO"))
    (project / "agent.py").write_text(
        (project / "agent.py").read_text() + "\n# second deploy\n")

    subprocess.run(["co", "deploy", "--to", server], cwd=project, check=True,
                   capture_output=True, timeout=900)

    remote = co("server", "ssh", server,
                f"cat /srv/{AGENT}/.co/skills/greet-visitor/SKILL.md").stdout
    assert "VERSION_MARKER_TWO" in remote, "the updated skill did not travel"
    assert "VERSION_MARKER_ONE" not in remote, "the old skill was left behind"

    state = co("server", "ssh", server, f"cat /srv/{AGENT}/.co/e2e-state.txt").stdout
    assert "STATE_FROM_FIRST_DEPLOY" in state, "a redeploy destroyed the agent's state"

    code = co("server", "ssh", server, f"tail -1 /srv/{AGENT}/agent.py").stdout
    assert "second deploy" in code

    assert co("server", "ssh", server,
              f"systemctl is-active {AGENT}").stdout.strip() == "active"


def test_the_server_is_listed_with_what_it_costs(server):
    """`co server ls` reconciles against billing, so a machine you are paying
    for cannot be invisible."""
    assert server in co("server", "ls").stdout
