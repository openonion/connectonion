"""`co server new` → deploy → iterate → destroy, against a real machine.

Skipped unless CO_E2E_SERVERS=1: a run creates a GCE instance, spends credit and
takes several minutes.

    CO_E2E_SERVERS=1 pytest tests/e2e/real_api/test_server_lifecycle.py -m real_api -v -s

`-m real_api` is not optional. pytest.ini carries `-m "not real_api and not
network"` in addopts, and this directory is marked real_api automatically, so
without it pytest deselects all of this and reports

    collected 11 items / 11 deselected / 0 selected

in a tenth of a second. No failure, no red — a run that looks like it passed and
tested nothing. The env var above is what gates the cost; the marker filter is
just in the way.

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

    # Immediately, before anything else can touch it: was the machine we were
    # just charged for actually registered? #445 — `co server new` prints
    # "✓ ready … $360.00 charged" and the next command answers "No server named".
    # Reading the file here separates "never written" from "written then
    # removed", which is the one thing the source cannot tell us.
    registry = Path.home() / ".co" / "servers.yaml"
    print(f"\n[registry] exists={registry.exists()} "
          f"mtime={registry.stat().st_mtime if registry.exists() else None}")
    print(f"[registry] contents:\n{registry.read_text() if registry.exists() else '(none)'}")

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


# --- The Home page, which has never been checked against a real deploy ---
#
# The dashboard moved into .co/ (#405), and .co/* is excluded from the deploy
# rsync with a handful of paths included back by name. Whether the include
# actually fires is not something a unit test can answer: it is an rsync filter
# argument, and the only way to know is to look on the machine.


def test_an_authored_dashboard_travels_with_the_deploy(server, project):
    """A Home page the author wrote must arrive intact.

    If the rsync filter misses it, the deploy still succeeds and the agent still
    starts — it just writes a fresh starter over the top on first boot and looks
    entirely healthy while the operator's page is gone. That is the failure this
    catches, and it is silent by construction.
    """
    dashboard = project / ".co" / "dashboard.html"
    dashboard.write_text(
        "<!DOCTYPE html><html><body><h1>DASHBOARD_MARKER_ONE</h1></body></html>",
        encoding="utf-8",
    )

    subprocess.run(["co", "deploy", "--to", server], cwd=project, check=True,
                   capture_output=True, timeout=900)

    remote = co("server", "ssh", server, f"cat /srv/{AGENT}/.co/dashboard.html").stdout
    assert "DASHBOARD_MARKER_ONE" in remote, "the authored dashboard did not travel"


def test_a_redeploy_does_not_overwrite_the_authored_dashboard(server, project):
    """The agent owns the file after it exists. A redeploy carries the author's
    new version; nothing on the server may regenerate over it."""
    dashboard = project / ".co" / "dashboard.html"
    dashboard.write_text(
        "<!DOCTYPE html><html><body><h1>DASHBOARD_MARKER_TWO</h1></body></html>",
        encoding="utf-8",
    )

    subprocess.run(["co", "deploy", "--to", server], cwd=project, check=True,
                   capture_output=True, timeout=900)

    remote = co("server", "ssh", server, f"cat /srv/{AGENT}/.co/dashboard.html").stdout
    assert "DASHBOARD_MARKER_TWO" in remote
    assert "DASHBOARD_MARKER_ONE" not in remote


def test_the_deployed_dashboard_offers_the_deployed_skill(server, project):
    """The starter lists the agent's skills as one-click buttons, and a client
    refuses any button naming a skill the agent did not publish. So a starter
    generated on the server has to name the skill that actually shipped there —
    otherwise Home is a page of buttons that silently do nothing."""
    co("server", "ssh", server, f"rm -f /srv/{AGENT}/.co/dashboard.html")
    co("server", "ssh", server, f"systemctl restart {AGENT}")
    _wait_for_dashboard(server)

    remote = co("server", "ssh", server, f"cat /srv/{AGENT}/.co/dashboard.html").stdout
    assert 'data-ochat-skill="greet-visitor"' in remote, (
        "the starter written on the server does not offer the skill that was deployed"
    )


def test_the_starter_lands_in_the_co_directory_on_the_server(server):
    """Not the project root. The unit under systemd runs with WorkingDirectory
    set to the project, so a starter resolved against the bare cwd would land
    beside agent.py and be excluded from the next deploy's rsync."""
    listing = co("server", "ssh", server, f"ls /srv/{AGENT}/").stdout
    assert "dashboard.html" not in listing.split(), (
        "a dashboard was written to the project root, not into .co/"
    )


def _wait_for_dashboard(server, attempts=12):
    """host() writes the starter at startup; systemctl returns before that."""
    import time

    for _ in range(attempts):
        result = co("server", "ssh", server,
                    f"test -f /srv/{AGENT}/.co/dashboard.html && echo yes || echo no",
                    check=False)
        if "yes" in result.stdout:
            return
        time.sleep(5)
    raise AssertionError("no dashboard.html appeared on the server after restart")
