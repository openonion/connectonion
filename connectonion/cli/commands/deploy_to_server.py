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

import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from .server_commands import SSH_TIMEOUT_SECONDS, load_server

console = Console()

# Bumped when a setup step is added or changes shape. A server reporting an
# older schema runs the missing steps; one reporting this schema goes straight
# to rsync and restart.
PROVISION_SCHEMA = 1

SRV = "/srv"


def _ssh(target: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run one command on the server. Longer default timeout than a preflight:
    apt and pip are slow, and killing them halfway leaves a half-installed box."""
    return subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
            "-o", "StrictHostKeyChecking=accept-new",
            target,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
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

    return {"name": name, "entrypoint": str(config.get("entrypoint") or "agent.py")}


def _read_provision(target: str, agent: str) -> dict:
    """Read the convergence marker. A missing or unreadable one means schema 0."""
    result = _ssh(target, f"cat {SRV}/{agent}/.co/provision.json 2>/dev/null", timeout=60)
    if result.returncode != 0 or not result.stdout.strip():
        return {"schema": 0}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # A truncated or hand-edited marker should mean "converge again", not
        # crash the deploy.
        return {"schema": 0}


def _unit_text(agent: str, entrypoint: str) -> str:
    """The systemd unit. Restart=always and enable are what the container was for."""
    return f"""[Unit]
Description=ConnectOnion agent {agent}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={SRV}/{agent}
ExecStart={SRV}/{agent}/.venv/bin/python {entrypoint}
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


def _write_unit_if_changed(target: str, agent: str, entrypoint: str) -> bool:
    """Write the systemd unit only when its content differs.

    Rewriting it every deploy would mean a daemon-reload every deploy for no
    reason, and would hide whether a restart came from new code or a new unit.
    """
    wanted = _unit_text(agent, entrypoint)
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


def _sync_code(target: str, agent: str, project_dir: Path) -> bool:
    """rsync the project, excluding the state directory but carrying skills.

    `--delete` removes code files deleted locally, which is wanted. `.co/` is
    excluded so the agent's identity, logs and evals survive — that exclusion is
    the whole reason a redeploy no longer reissues the agent's address.

    `.co/skills/` is the exception, and it has to be: skills are *what the agent
    is*, not state it accumulated. Excluding all of `.co/` shipped an agent with
    none of its skills — the deploy succeeded and the agent ran without them,
    which is worse than failing. So skills are included, and `--delete` applies
    inside that directory too so a removed skill actually goes away.

    Order matters to rsync: the include must precede the exclude that would
    otherwise swallow it, and `.co/` itself must be included for rsync to
    descend into it at all.
    """
    console.print("[dim]  syncing code …[/dim]")
    result = subprocess.run(
        [
            "rsync", "-az", "--delete",
            "--include", ".co/",
            "--include", ".co/skills/***",
            "--exclude", ".co/*",
            "--exclude", ".venv/",
            "--exclude", ".git/",
            "--exclude", "__pycache__/",
            "-e", f"ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
            f"{project_dir}/",
            f"{target}:{SRV}/{agent}/",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
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
        f"set -e\n"
        f"{SRV}/{agent}/.venv/bin/pip install -q -r {SRV}/{agent}/requirements.txt\n"
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

    active = _ssh(target, f"systemctl is-active {agent}", timeout=60)
    if active.stdout.strip() != "active":
        console.print(f"[red]{agent} is not running after restart "
                      f"({active.stdout.strip() or 'unknown'}).[/red]")
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

    if not (project_dir / entrypoint).exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print(f"[dim]Set 'entrypoint' in {project_dir / '.co' / 'host.yaml'}[/dim]")
        return False

    console.print(f"\n[bold]{agent}[/bold] → [cyan]{server}[/cyan] [dim]({target})[/dim]")

    provision = _read_provision(target, agent)
    ssh_public_line = _derive_ssh_public_line()
    deployer_address = _deployer_address()

    if not _ensure_setup(target, agent, entrypoint, provision.get("schema", 0),
                         ssh_public_line, deployer_address):
        return False
    if not _sync_code(target, agent, project_dir):
        return False
    if not _install_deps_if_changed(target, agent, project_dir):
        return False
    if not _write_unit_if_changed(target, agent, entrypoint):
        return False
    if not _restart(target, agent):
        return False

    _mark_provisioned(target, agent)

    console.print(f"\n[green]✓ {agent} is running on {server}[/green]")
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


def _derive_ssh_public_line() -> Optional[str]:
    """The operator's derived public key, so access self-heals every deploy.

    Returns None when there is no local identity to derive from; the deploy
    still proceeds, since the operator evidently already has access.
    """
    from ... import address
    from .keys_commands import _find_co_dir

    co_dir = _find_co_dir()
    if not co_dir:
        return None
    data = address.load(co_dir)
    if not data or not data.get("seed_phrase"):
        return None
    return address.derive_ssh_key(data["seed_phrase"])["public_line"]
