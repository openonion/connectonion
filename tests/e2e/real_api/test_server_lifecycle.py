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
- the agent ran as root, so `co call` handed out more than ssh to the box would
- `co` was not on the unit's PATH, so `co call <address> co status` — the example
  in `co call`'s own help — answered "co: command not found"
- the operator was a stranger to their own agent: their key was written into
  .co/admins.txt and the trust gate never looked at that list

The unit tests could not have caught any of them. They all live between our code
and ssh, and the only way to see them is to talk to a real box.

If a run fails with `Permission denied (publickey)`, check where you are before
suspecting the code. Compare the host key the address presents to you against
the machine's own, reaching it out of band:

    ssh-keyscan -t ed25519 <ip> | ssh-keygen -lf -
    gcloud compute ssh <instance> --zone=<zone> --tunnel-through-iap \
      --command="sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub"

Different fingerprints mean you are not talking to that machine, and nothing on
it is wrong. That cost an afternoon once: an address that failed from one
laptop, worked from a GCE box, and had our key correctly installed the whole
time.
"""

import os
import shutil
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

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
    """An agent carrying a skill, because a skill is the thing that did not ship.

    It installs the working tree, not the last release. `co deploy --to` reads
    requirements.txt, and a bare `connectonion` there means the server runs
    whatever PyPI has today — so this test would exercise the previous release
    while claiming to test the change in front of you. The template is generated
    by the CLI under test and can reference an API that has not shipped yet;
    against PyPI that is a crash loop, and the failure says nothing about
    versions.
    """
    root = tmp_path_factory.mktemp("e2e")
    subprocess.run(["co", "create", AGENT], cwd=root, check=True, capture_output=True)
    path = root / AGENT

    wheel = _build_wheel(tmp_path_factory.mktemp("wheel"))
    shutil.copy(wheel, path / wheel.name)
    requirements = path / "requirements.txt"
    kept = [l for l in requirements.read_text().splitlines()
            if not l.strip().startswith("connectonion")]
    requirements.write_text("\n".join([f"./{wheel.name}", *kept]) + "\n")

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


def _build_wheel(into: Path) -> Path:
    """A wheel of the working tree, for the server to install."""
    repo = Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable, "-m", "build", "--wheel", "-o", str(into)],
                   cwd=repo, check=True, capture_output=True, timeout=900)
    wheels = sorted(into.glob("connectonion-*.whl"))
    assert wheels, f"no wheel built into {into}"
    return wheels[-1]


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


def _agent_address(server: str) -> str:
    """The deployed agent's address, read off its own logs."""
    import re

    logs = co("server", "ssh", server,
              f"journalctl -u {AGENT} --no-pager -n 200").stdout
    found = re.findall(r"0x[0-9a-f]{64}", logs)
    assert found, "the agent never printed its address"
    return found[0]


def test_the_agent_does_not_run_as_root(server, project):
    """`co call` runs whatever the admin sends, so the unit's user is the
    privilege the remote-exec path hands out. As root that was more than the
    operator gets by sshing in themselves."""
    user = co("server", "ssh", server,
              f"ps -o user= -p $(systemctl show -p MainPID --value {AGENT})").stdout

    assert user.strip() and user.strip() != "root", user


def test_the_operator_can_run_a_command_on_their_own_agent(server, project):
    """The whole point of `co call`, and the example in its own help.

    It failed twice over: the trust gate never consulted .co/admins.txt, so the
    owner was a stranger; and once past that, `co` was not on the unit's PATH.
    """
    address = _agent_address(server)

    result = co("call", address, "co", "status", timeout=300)

    assert "onboarding" not in result.stdout + result.stderr, \
        "the operator was treated as a stranger by their own agent"
    assert "command not found" not in result.stdout + result.stderr, \
        "the agent could not find co on its own PATH"
    assert "Credential Sources" in result.stdout, result.stdout[:400]


def test_the_remote_browser_answers(server, project):
    """`co browser` over `co call` is the remote twin of the local command.

    A shared /tmp/co owned by another user used to stop it before it started.
    """
    address = _agent_address(server)

    result = co("call", address, "co", "browser", "status", timeout=300)

    assert "Permission denied" not in result.stderr, result.stderr[:300]
    assert "Stealth driver" in result.stdout, result.stdout[:300]
    # "Stealth driver ✓" is about the patchright PACKAGE, and this assertion used
    # to stop there — so it passed against a server with no browser on it at all,
    # which is what a fresh provision is (nothing installs one). Whether it
    # SHOULD is a separate question; what this checks is that the answer says
    # which case it is, instead of a green line that means neither.
    assert "Browser binary" in result.stdout, result.stdout[:400]
