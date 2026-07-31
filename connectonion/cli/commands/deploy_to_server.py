"""
Purpose: Deploy an agent onto a server you own — converge the setup, sync the code, restart the unit
LLM-Note:
  Dependencies: imports from [hashlib, json, shlex, subprocess, pathlib, yaml, rich, server_commands, project_cmd_lib] | imported by [cli/main.py via handle_deploy_to] | tested by [tests/unit/test_deploy_to_server.py]
  Data flow: handle_deploy_to(server, project_dir) → load_server() resolves the ssh target → _read_provision() reads /srv/<agent>/.co/provision.json → _ensure_setup() runs only the missing steps → _sync_code() rsyncs excluding .co/ → _install_deps() only when requirements.txt changed → _write_unit() on change → systemctl restart
  State/Effects: on the server creates /srv/<agent>/{,.venv,.co} and /etc/systemd/system/<agent>.service | rsyncs code | NEVER writes inside /srv/<agent>/.co except provision.json | locally reads .co/host.yaml and the project files
  Integration: exposes handle_deploy_to(server, project_dir) | requires a server registered by `co server add` (#311) reachable with the key from `co keys --ssh` (#310)
  Performance: one ssh round trip to read provision.json, one rsync, one restart | setup steps are skipped entirely once the schema matches
  Errors: an unreachable or unprepared server fails before anything is changed | a failed unit start surfaces journalctl output rather than a bare exit code
"""

import base64
import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from dotenv import dotenv_values
from rich.console import Console

from .server_commands import SSH_TIMEOUT_SECONDS, load_server

console = Console()

# Bumped when a setup step is added or changes shape. A server reporting an
# older schema runs the missing steps; one reporting this schema goes straight
# to rsync and restart.
PROVISION_SCHEMA = 3

# Secrets live outside the rsync root on purpose. Inside `/srv/<agent>/` the
# next deploy's `--delete` would overwrite them with the laptop's copy, so a key
# rotated in production could not stay rotated.
ENV_FILE_TEMPLATE = "/etc/connectonion/{agent}.env"

# How long a unit has to stay up before we call the deploy good, and how long we
# are willing to wait for it. A single sleep-then-look is not enough: `systemctl
# restart` resets NRestarts, and an agent that fails on import can take ten
# seconds to get there — long enough to look healthy to a probe that only waits
# eight. So we watch, fail the moment it restarts itself, and otherwise wait for
# it to have been continuously up.
STARTUP_STABLE_SECONDS = 15
STARTUP_TIMEOUT_SECONDS = 45

SRV = "/srv"


def _ssh(target: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run one command on the server. Longer default timeout than a preflight:
    apt and pip are slow, and killing them halfway leaves a half-installed box."""
    from .server_commands import _identity

    argv = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
        "-o", "StrictHostKeyChecking=accept-new",
        *_identity(),
        target,
        command,
    ]
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A hung resolver or a box that stops answering mid-deploy raises here.
        # Uncaught it printed a Python traceback, which tells the operator we
        # crashed — when what happened is that their server went quiet.
        #
        # Returned as a failed CompletedProcess rather than raised, because every
        # caller already treats a non-zero return as a failed step and reports it
        # with the server name. One shape of failure, one place that renders it.
        return subprocess.CompletedProcess(
            argv, returncode=124,          # the conventional exit code for a timeout
            stdout="",
            stderr=f"ssh to {target} timed out after {timeout}s — the server did "
                   f"not answer. Check it is running and reachable: "
                   f"co server check <name>",
        )


def _read_project(project_dir: Path) -> Optional[dict]:
    """Read the agent name and entrypoint from .co/host.yaml.

    Same contract as the cloud deploy, so a project does not need a second
    config to be deployable both ways.
    """
    host_yaml = project_dir / ".co" / "host.yaml"
    if not host_yaml.exists():
        console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
        return None

    config = yaml.safe_load(host_yaml.read_text(encoding="utf-8")) or {}
    from .project_cmd_lib import DEPLOY_NAME_PATTERN, normalize_deploy_name

    name = str(config.get("name") or "unnamed-agent")
    if not DEPLOY_NAME_PATTERN.match(name):
        console.print(f"[red]Invalid agent name: {name}[/red]")
        # The name becomes a directory and a systemd unit name, so the same rule
        # the cloud path enforces applies here.
        suggestion = normalize_deploy_name(name)
        if suggestion:
            console.print(f"[dim]Try:  name: {suggestion}[/dim]")
        return None

    return {
        "name": name,
        "entrypoint": str(config.get("entrypoint") or "agent.py"),
        # host() defaults to 8000; a project that moved it has to say so here, or
        # Caddy would proxy to a port nothing is listening on.
        "port": int(config.get("port") or 8000),
    }


def _warn_about_skills_left_behind(project_dir: Path) -> None:
    """Name the skills that work here and will not exist on the server.

    The rsync carries the project tree, so ~/.co/skills and ~/.claude/skills — usually
    symlinks into a separate repo — are simply absent there. The agent then behaves
    differently for a reason nothing in its output explains.
    """
    from ...useful_plugins.skills import skills_that_will_not_travel, find_skill_problems

    staying = skills_that_will_not_travel(project_dir=project_dir)
    if staying:
        console.print(
            f"  [yellow]![/yellow] {len(staying)} skill(s) stay on this machine: "
            + ", ".join(s.name for s in staying[:5])
            + (f" (+{len(staying) - 5} more)" if len(staying) > 5 else "")
        )
        console.print("    [dim]co skills copy <name> --to-project   to ship one[/dim]")

    for location, name, reason in find_skill_problems(project_dir=project_dir):
        console.print(f"  [red]✗[/red] {location}/{name} — {reason}")


def _read_provision(target: str, agent: str) -> dict:
    """Read the convergence marker, and check the one thing it claims.

    The marker survives every rsync, by design — it is the record of work that
    does not need doing again. But it records what *was* true, and the venv it
    speaks for can be gone: a disk cleanup, a restored snapshot, an `rm -rf`
    during debugging. The marker knows nothing about that, so the deploy skipped
    creating the venv, pip short-circuited on an unchanged requirements hash,
    and the restart failed with a systemd error naming a python that is not
    there — the one cause never mentioned.

    So the interpreter is checked in the same round trip that reads the marker.
    Not a re-verification of everything it implies; one test for the file the
    systemd unit will execute.
    """
    result = _ssh(target,
                  f"cat {SRV}/{agent}/.co/provision.json 2>/dev/null; "
                  f"echo; test -x {SRV}/{agent}/.venv/bin/python && echo VENV_PRESENT",
                  timeout=60)
    if result.returncode != 0:
        return {"schema": 0}

    marker, _, tail = result.stdout.rpartition("\n")
    if "VENV_PRESENT" not in result.stdout:
        # Whatever the marker says, the work has to be done again.
        return {"schema": 0}
    if not marker.strip():
        return {"schema": 0}
    try:
        return json.loads(marker)
    except json.JSONDecodeError:
        # A truncated or hand-edited marker should mean "converge again", not
        # crash the deploy.
        return {"schema": 0}


def _unit_text(agent: str, entrypoint: str, hostname: Optional[str] = None,
               user: str = "root") -> str:
    """The systemd unit. Restart=always and enable are what the container was for.

    AGENT_PUBLIC_DOMAIN is what makes the agent reachable to anything but ssh.
    Without it announce.py publishes `http://<ip>:8000` to the relay, and 8000 is
    closed on a provisioned server — so every client probes an endpoint that can
    never answer. With it the agent announces `https://<hostname>`, which is what
    Caddy is listening on.

    It runs as the same user that owns the files, not as root. `co call` executes
    whatever the admin sends, so running as root hands out more than ssh to this
    box would: the operator logs in as an ordinary user, and their agent had a
    superset of their own privileges. It also gives the process a real HOME —
    as root it was /root, which is why the browser looked for its cache there and
    could never have found one.

    PATH puts the project's venv first, which is what activating it would do.
    Without it the agent inherits systemd's default PATH and `co` — installed in
    that venv — is not on it, so `co call <address> co status`, the example in
    `co call`'s own help, answers "co: command not found". It reaches every
    command the agent shells out to, not just remote exec.
    """
    environment = f"Environment=PATH={SRV}/{agent}/.venv/bin:/usr/local/sbin:" \
                  f"/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
    if hostname:
        environment += f"Environment=AGENT_PUBLIC_DOMAIN={hostname}\n"
    return f"""[Unit]
Description=ConnectOnion agent {agent}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={SRV}/{agent}
EnvironmentFile=-{ENV_FILE_TEMPLATE.format(agent=agent)}
{environment}ExecStart={SRV}/{agent}/.venv/bin/python {entrypoint}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _ensure_setup(target: str, agent: str, entrypoint: str, schema: int,
                  ssh_public_line: Optional[str],
                  deployer_address: Optional[str] = None) -> bool:
    """Bring the server to the state a deploy assumes. Idempotent.

    Runs on every deploy, and is a no-op once the schema matches — which is why
    a machine registered by hand needs no separate path: its first deploy is the
    one that sets it up.
    """
    steps = []

    if schema < PROVISION_SCHEMA:
        # python, venv and the directory layout. Once only, unless the schema
        # moves. `.co/` is created but never written into again by a deploy.
        steps.append(f"""
set -e
sudo mkdir -p {SRV}/{agent}/.co
sudo chown -R "$USER" {SRV}/{agent}
command -v python3 >/dev/null || (sudo apt-get update -qq && sudo apt-get install -y -qq python3)
dpkg -s python3-venv >/dev/null 2>&1 || (sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv)
[ -x {SRV}/{agent}/.venv/bin/python ] || python3 -m venv {SRV}/{agent}/.venv
""")

    if ssh_public_line:
        # Ensured every deploy, not once: authorized_keys is the only way back
        # in, so it self-heals rather than needing a rescue path.
        quoted = shlex.quote(ssh_public_line)
        steps.append(f"""
mkdir -p ~/.ssh && chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
grep -qxF {quoted} ~/.ssh/authorized_keys || echo {quoted} >> ~/.ssh/authorized_keys
""")

    if deployer_address:
        # The same idea one layer up: authorized_keys is who may enter the machine,
        # admins.txt is who may command the agent. Without this nobody can — ADMIN_ADD
        # is gated on super-admin, super-admin is the agent's OWN address, and that
        # private key exists only on the server. The one account that could grant admin
        # is the one nobody can sign as.
        #
        # Written every deploy, like the SSH key, so it self-heals. It lives in .co/,
        # which the rsync excludes, so it has to be written over ssh rather than shipped.
        quoted_admin = shlex.quote(deployer_address)
        admins = f"{SRV}/{agent}/.co/admins.txt"
        steps.append(f"""
touch {admins}
grep -qxF {quoted_admin} {admins} || echo {quoted_admin} >> {admins}
""")

    if not steps:
        return True

    console.print("[dim]  converging server …[/dim]")
    result = _ssh(target, "\n".join(steps), timeout=600)
    if result.returncode != 0:
        console.print("[red]Setup failed.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-8:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _remote_user(target: str) -> str:
    """The account the ssh session lands as, according to the server.

    Falls back to parsing the target only if the server cannot be asked, which
    keeps the `user@host` form working even on a machine without `id`.
    """
    result = _ssh(target, "id -un", timeout=30)
    name = (result.stdout or "").strip()
    if result.returncode == 0 and name:
        return name
    return target.split("@")[0]


def _write_unit_if_changed(target: str, agent: str, entrypoint: str,
                           hostname: Optional[str] = None,
                           user: Optional[str] = None) -> bool:
    """Write the systemd unit only when its content differs.

    Rewriting it every deploy would mean a daemon-reload every deploy for no
    reason, and would hide whether a restart came from new code or a new unit.
    """
    # The ssh target's user owns everything under /srv/<agent> — it is the user
    # rsync wrote as — so it is the one the service should run as. The caller
    # resolves it once per deploy; falling back here keeps the old signature
    # working for direct callers.
    if user is None:
        user = _remote_user(target)
    wanted = _unit_text(agent, entrypoint, hostname, user=user)
    unit_path = f"/etc/systemd/system/{agent}.service"

    current = _ssh(target, f"cat {unit_path} 2>/dev/null", timeout=60)
    if current.returncode == 0 and current.stdout == wanted:
        return True

    console.print("[dim]  writing systemd unit …[/dim]")
    script = f"""
set -e
cat > /tmp/{agent}.service <<'UNITEOF'
{wanted}UNITEOF
sudo mv /tmp/{agent}.service {unit_path}
sudo systemctl daemon-reload
sudo systemctl enable {agent} >/dev/null 2>&1
"""
    result = _ssh(target, script, timeout=120)
    if result.returncode != 0:
        console.print("[red]Could not write the systemd unit.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-8:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _caddyfile_text(hostname: str, port: int) -> str:
    """One hostname, proxied to the agent on loopback.

    Caddy gets and renews the certificate itself over HTTP-01, which is why 80
    has to be open even though nothing is served on it. `reverse_proxy` passes
    WebSocket upgrades through unchanged, so /ws needs no separate stanza — the
    agent's chat, dashboard pushes and remote exec all ride that one connection.

    One agent per hostname. A second agent deployed to the same server takes the
    name from the first, because there is one name and one :443. Several agents
    on one machine is still an open question (openonion/connectonion#309); when
    it is answered this file grows a stanza per agent rather than being replaced.
    """
    return f"""{hostname} {{
	reverse_proxy 127.0.0.1:{port}
}}
"""


def _ensure_caddy(target: str, hostname: str, port: int) -> bool:
    """Install Caddy if absent, and point it at this agent.

    Installed here rather than by provisioning for the reason #318 settled: a
    machine registered by hand with `co server add` never went through
    provisioning, so this has to exist anyway — and doing it in both places is
    two implementations of one thing, reachable only by two differently-created
    machines.

    The config is written only when it differs, like the systemd unit: a reload
    on every deploy would hide whether the certificate work was actually caused
    by a change.
    """
    wanted = _caddyfile_text(hostname, port)

    current = _ssh(target, "cat /etc/caddy/Caddyfile 2>/dev/null", timeout=60)
    if current.returncode == 0 and current.stdout == wanted and _caddy_running(target):
        return True

    console.print("[dim]  configuring https …[/dim]")
    script = f"""
set -e
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq caddy
fi
sudo mkdir -p /etc/caddy
cat > /tmp/Caddyfile <<'CADDYEOF'
{wanted}CADDYEOF
sudo mv /tmp/Caddyfile /etc/caddy/Caddyfile
sudo systemctl enable caddy >/dev/null 2>&1
sudo systemctl reload caddy 2>/dev/null || sudo systemctl restart caddy
"""
    result = _ssh(target, script, timeout=600)
    if result.returncode != 0:
        console.print("[red]Could not set up https.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-8:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _caddy_running(target: str) -> bool:
    return _ssh(target, "systemctl is-active caddy", timeout=60).stdout.strip() == "active"


# Everything the author wrote ships, and `--delete` removes what they deleted.
# `.co/` gets two carve-outs, both because the server owns that data:
#
#   P .co/**       nothing under .co/ is ever *deleted* on the server. Identity,
#                  logs, admins.txt, provision.json and anything a future
#                  version writes there survive a deploy without being listed.
#   --exclude ...  identity and accumulated state are never *sent*, so a stale
#                  local copy cannot overwrite the live one.
#
# This replaced an include-list that named the `.co/` files worth carrying.
# That default — exclude unless remembered — lost `.co/skills/` in its first
# version and `.co/dashboard.html` in its second, and was silently dropping
# `host.yaml`, `OO.md` and `commands/` when this was written. Forgetting to
# carry config is invisible: the deploy succeeds and a different agent runs.
RSYNC_FILTERS = [
    "--filter", "P .co/**",
    # `.env` is a secret, not source. It reaches the server through
    # _sync_env(), as a root-owned 0600 file systemd reads — not as a
    # world-readable file that happens to land in the working directory.
    "--exclude", ".env",
    "--exclude", ".env.*",
    # Generated on the server, or written there over ssh by the deploy itself.
    # The protect rule above keeps them from being deleted; these keep a local
    # copy from overwriting them, which is the other half of the same rule.
    # `address.json` decides super-admin (trust/tools.py:328) and `admins.txt`
    # decides who may command the agent — a stale local copy of either is a
    # change of who is in charge, made silently by a deploy.
    "--exclude", ".co/keys/",
    "--exclude", ".co/address.json",
    "--exclude", ".co/admins.txt",
    "--exclude", ".co/provision.json",
    "--exclude", ".co/requirements.sha256",
    "--exclude", ".co/logs/",
    "--exclude", ".co/evals/",
    "--exclude", ".co/sessions/",
    "--exclude", ".venv/",
    "--exclude", ".git/",
    "--exclude", "__pycache__/",
]


def _env_for_server(env_vars: dict, agent: str) -> dict:
    """The project's `.env`, corrected for the machine it is going to.

    `AGENT_CONFIG_PATH` is written by `co init` as an absolute path to the
    author's own `~/.co`. Shipped verbatim it names a directory that does not
    exist on the server, and `useful_tools/gmail.py`, `outlook.py`, `gdrive.py`
    and `google_calendar.py` all build their `keys.env` path from it — so those
    tools fail there rather than falling back. The Cloud path already rewrites
    it to `/app/.co`; this is the same correction for `/srv/<agent>/.co`.
    """
    out = dict(env_vars)
    if out.get("AGENT_CONFIG_PATH"):
        out["AGENT_CONFIG_PATH"] = f"{SRV}/{agent}/.co"
    return out


def _sync_env(target: str, agent: str, project_dir: Path) -> bool:
    """Write the project's secrets where systemd can read them and nobody else.

    Sent over ssh rather than rsync, to a path outside the rsync root: the file
    is owned by root at 0600, so `co call`'s remote exec — which runs as the
    service user — cannot read it back out, and `--delete` cannot overwrite a
    key that was rotated on the server.
    """
    env_path = project_dir / ".env"
    if not env_path.exists():
        return True

    env_vars = _env_for_server(dotenv_values(env_path), agent)

    # A newline inside a value would end the KEY=VALUE line and turn the rest
    # into junk entries. Say so rather than write a file that looks fine.
    multiline = [k for k, v in env_vars.items() if v is not None and "\n" in v]
    for key in multiline:
        console.print(f"[yellow]  skipping {key}: multi-line values are not "
                      f"supported in an EnvironmentFile[/yellow]")
    env_vars = {k: v for k, v in env_vars.items()
                if v is not None and k not in multiline}
    if not env_vars:
        return True

    body = "".join(f"{k}={v}\n" for k, v in env_vars.items())
    dest = ENV_FILE_TEMPLATE.format(agent=agent)

    # base64 over the wire so no value is ever shell syntax. A heredoc would be
    # terminated early by a value that happened to equal the delimiter, and the
    # remainder of the file would then run as commands — under sudo.
    payload = base64.b64encode(body.encode("utf-8")).decode("ascii")

    console.print(f"[dim]  writing secrets … ({len(env_vars)} keys)[/dim]")
    result = _ssh(target, f"""
sudo mkdir -p {shlex.quote(str(Path(dest).parent))}
printf %s {shlex.quote(payload)} | base64 -d | sudo tee {shlex.quote(dest)} >/dev/null
sudo chmod 600 {shlex.quote(dest)}
""", timeout=120)
    if result.returncode != 0:
        console.print("[red]Could not write the env file.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-5:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _sync_code(target: str, agent: str, project_dir: Path) -> bool:
    """rsync the project, carrying everything the author wrote and deleting
    nothing the server owns.

    `--delete` removes code files deleted locally, which is wanted. It stops at
    `.co/`, where the server keeps the agent's identity, its logs, the admins
    list and the convergence marker — data the project has never heard of and
    an include-list could not enumerate.

    What the author writes under `.co/` — `host.yaml`, `OO.md`, `skills/`,
    `commands/`, `dashboard.html` — is not state. It is what makes this agent
    this agent, so it ships like the rest of the tree. `host.yaml` in particular
    carries the permission whitelist and the port: without it the agent runs on
    template defaults behind a proxy pointed at the wrong port, and reports
    success either way.

    See RSYNC_FILTERS for the two rules and why the default is now "carry".
    """
    from .server_commands import _identity as _ssh_identity

    console.print("[dim]  syncing code …[/dim]")
    result = subprocess.run(
        [
            "rsync", "-az", "--delete",
            *RSYNC_FILTERS,
            "-e", " ".join(["ssh", "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new",
                            *_ssh_identity()]),
            f"{project_dir}/",
            f"{target}:{SRV}/{agent}/",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode == 0:
        # Every deploy, not only when the unit changes: the files have to belong
        # to the user the service runs as. An agent that ran as root before left
        # root-owned logs and state behind, and the first thing the unprivileged
        # process does is fail to write its own log —
        # PermissionError: [Errno 13] Permission denied: '.co/logs/oo.log'
        _ssh(target, f"sudo chown -R {_remote_user(target)}: {SRV}/{agent}", timeout=120)

    if result.returncode != 0:
        console.print("[red]rsync failed.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-8:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _install_deps_if_changed(target: str, agent: str, project_dir: Path) -> bool:
    """pip install only when requirements.txt actually changed.

    The hash of the file we just synced is compared against the hash recorded
    after the last successful install. Reinstalling every deploy would make a
    code-only change take minutes instead of seconds.
    """
    requirements = project_dir / "requirements.txt"
    if not requirements.exists():
        return True

    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = f"{SRV}/{agent}/.co/requirements.sha256"

    current = _ssh(target, f"cat {stamp} 2>/dev/null", timeout=60)
    if current.returncode == 0 and current.stdout.strip() == digest:
        return True

    console.print("[dim]  installing dependencies …[/dim]")
    result = _ssh(
        target,
        # From the project directory, because a requirements.txt is allowed to
        # name things relative to itself — a local wheel, `-e .`, a nested
        # `-r requirements-dev.txt`. Run from the login shell's home instead and
        # pip resolves those against /home/<user> and reports a file that is
        # plainly there as missing.
        f"set -e\n"
        f"cd {SRV}/{agent}\n"
        f"{SRV}/{agent}/.venv/bin/pip install -q -r requirements.txt\n"
        f"printf '%s' {shlex.quote(digest)} > {stamp}",
        timeout=900,
    )
    if result.returncode != 0:
        console.print("[red]pip install failed.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-12:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _restart(target: str, agent: str) -> bool:
    """Restart, then confirm it is actually running.

    `systemctl restart` returns 0 for a unit that starts and immediately dies,
    so the status check is the real test. On failure show journald rather than
    an exit code — the traceback is what the operator needs.
    """
    console.print("[dim]  restarting …[/dim]")
    result = _ssh(target, f"sudo systemctl restart {agent}", timeout=120)
    if result.returncode != 0:
        console.print("[red]Restart failed.[/red]")
        for line in (result.stderr or result.stdout).strip().splitlines()[-8:]:
            console.print(f"  [dim]{line}[/dim]")
        return False

    # Asking once is not a test. Restart=always means a unit that dies on import
    # is "active" in the moment right after the restart and again after every
    # crash, so an agent looping on a traceback reported a clean deploy. The
    # restart also resets NRestarts, so a single delayed look is a race against
    # however long the agent takes to fail — ten seconds, for one that dies on
    # an import.
    #
    # Watch instead: fail the moment it restarts itself, and call it good only
    # once it has been continuously up. Both answers arrive as early as they
    # honestly can.
    watch = (
        f"for i in $(seq 1 {STARTUP_TIMEOUT_SECONDS}); do\n"
        f"  state=$(systemctl is-active {agent})\n"
        f"  restarts=$(systemctl show -p NRestarts --value {agent})\n"
        f'  if [ "$restarts" != "0" ] || [ "$state" = failed ]; then\n'
        f'    echo "verdict=crashed restarts=$restarts state=$state"; exit 0\n'
        f"  fi\n"
        f'  if [ "$state" = active ] && [ "$i" -ge {STARTUP_STABLE_SECONDS} ]; then\n'
        f'    echo "verdict=up"; exit 0\n'
        f"  fi\n"
        f"  sleep 1\n"
        f"done\n"
        f'echo "verdict=never-started state=$(systemctl is-active {agent})"'
    )
    status = _ssh(target, watch, timeout=STARTUP_TIMEOUT_SECONDS + 60)
    facts = dict(f.split("=", 1) for f in status.stdout.split() if "=" in f)

    if facts.get("verdict") != "up":
        why = {"crashed": f"crashed and is being restarted "
                          f"({facts.get('restarts')} time(s) so far)",
               "never-started": f"never came up ({facts.get('state') or 'unknown'})"
               }.get(facts.get("verdict"), "did not start")
        console.print(f"[red]{agent} {why}.[/red]")
        logs = _ssh(target, f"sudo journalctl -u {agent} -n 20 --no-pager", timeout=60)
        for line in logs.stdout.strip().splitlines()[-20:]:
            console.print(f"  [dim]{line}[/dim]")
        return False
    return True


def _mark_provisioned(target: str, agent: str) -> None:
    from ... import __version__
    marker = json.dumps({"schema": PROVISION_SCHEMA,
                         "provisioned_by": f"connectonion {__version__}"})
    _ssh(target, f"printf '%s' {shlex.quote(marker)} > {SRV}/{agent}/.co/provision.json",
         timeout=60)


def handle_deploy_to(server: str, project_dir: Optional[Path] = None) -> bool:
    """co deploy --to <server>:  ensure(setup) → sync code → restart."""
    project_dir = (project_dir or Path.cwd()).resolve()

    # Checked here rather than discovered inside subprocess.run, which raises
    # FileNotFoundError and prints a traceback — for the one failure a person can
    # fix in a sentence. `co server add` has always checked; this path did not,
    # and it is the one that runs after the server is already paid for.
    for binary in ("ssh", "rsync"):
        if not shutil.which(binary):
            console.print(f"\n[red]No {binary} binary found on PATH.[/red]")
            console.print(f"[dim]co deploys through your own {binary}, so it needs "
                          f"one installed.[/dim]\n")
            return False

    entry = load_server(server)
    if not entry:
        console.print(f"\n[red]No server named '{server}'.[/red]")
        console.print("[cyan]co server ls[/cyan] to see what is registered, or "
                      "[cyan]co server add[/cyan] to register one.\n")
        return False

    project = _read_project(project_dir)
    if not project:
        return False

    target = entry["ssh"]
    agent, entrypoint = project["name"], project["entrypoint"]
    # Recorded by `co server new`. A server registered by hand with
    # `co server add` has none, and then the deploy simply does not set up https
    # — there is no name to get a certificate for, and inventing one would fail
    # the challenge rather than fail honestly.
    hostname = entry.get("hostname")

    if not (project_dir / entrypoint).exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print(f"[dim]Set 'entrypoint' in {project_dir / '.co' / 'host.yaml'}[/dim]")
        return False

    console.print(f"\n[bold]{agent}[/bold] → [cyan]{server}[/cyan] [dim]({target})[/dim]")
    _warn_about_skills_left_behind(project_dir)

    provision = _read_provision(target, agent)
    from .server_commands import _ensure_ssh_key

    ssh_public_line = _ensure_ssh_key()
    deployer_address = _deployer_address()

    if not _ensure_setup(target, agent, entrypoint, provision.get("schema", 0),
                         ssh_public_line, deployer_address):
        return False
    if not _sync_code(target, agent, project_dir):
        return False
    if not _sync_env(target, agent, project_dir):
        return False
    if not _install_deps_if_changed(target, agent, project_dir):
        return False
    if hostname and not _ensure_caddy(target, hostname, project["port"]):
        return False
    # Once per deploy: the unit and the ownership fix-up both need it, and it
    # costs an ssh round trip.
    user = _remote_user(target)
    if not _write_unit_if_changed(target, agent, entrypoint, hostname, user=user):
        return False
    if not _restart(target, agent):
        return False

    _mark_provisioned(target, agent)

    console.print(f"\n[green]✓ {agent} is running on {server}[/green]")
    if hostname:
        console.print(f"  [cyan]https://{hostname}[/cyan] "
                      f"[dim]— the certificate lands within a minute of first boot[/dim]")
    console.print(f"[dim]  logs:  co server ssh {server} 'journalctl -u {agent} -f'[/dim]")
    console.print(f"[dim]  state: {SRV}/{agent}/.co/  — untouched by deploys[/dim]")
    if deployer_address:
        console.print(f"[dim]  admin: {deployer_address[:16]}…  (your key)[/dim]")
    console.print()
    return True


def _deployer_address() -> Optional[str]:
    """The operator's own agent address — the public half only, never the key.

    This is what the deployed agent will accept admin commands from. Returns None
    when there is no local identity; the deploy proceeds, and the agent simply has
    no reachable admin, which is the state before this existed.
    """
    from ... import address
    from .keys_commands import _find_co_dir

    co_dir = _find_co_dir()
    if not co_dir:
        return None
    data = address.load(co_dir)
    return data.get("address") if data else None

