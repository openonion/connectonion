"""
Purpose: Register, list and preflight the machines `co deploy --to` can target
LLM-Note:
  Dependencies: imports from [subprocess, shutil, pathlib, yaml, rich] | imported by [cli/main.py via handle_server_*] | tested by [tests/unit/test_server_commands.py]
  Data flow: handle_server_add(name, ssh_target) → _load()/_save() ~/.co/servers.yaml → handle_server_list() renders the table | handle_server_check(name) → _ssh(target, probe script) → parses one KEY=value line per requirement → prints the first failure by name
  State/Effects: reads and writes ~/.co/servers.yaml (name → ssh target, last check result) | shells out to the system ssh binary | never stores a credential
  Integration: exposes handle_server_add(), handle_server_list(), handle_server_check(), load_server() for deploy | requirement list is Ubuntu 24.04, python 3.11+, systemd the user may manage, free disk
  Performance: one ssh round trip per check; the probe is a single command, not one per requirement
  Errors: an unreachable host fails with ssh's own message and a short timeout, never a hang | a missing requirement is named
"""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

import yaml
from rich.console import Console
from rich.table import Table

console = Console()

SERVERS_FILE = Path.home() / ".co" / "servers.yaml"

# Deliberately short. "It doesn't work on my box" is only answerable if we
# stated a narrow promise and `co server check` says which item is missing.
MIN_PYTHON = (3, 11)
MIN_FREE_DISK_GB = 5
SUPPORTED_UBUNTU = "24.04"

# ssh must fail fast rather than hang: an unreachable host is the common case
# when a name is typed wrong, and a hang looks like a bug in us.
SSH_TIMEOUT_SECONDS = 10


def _load() -> Dict[str, dict]:
    if not SERVERS_FILE.exists():
        return {}
    data = yaml.safe_load(SERVERS_FILE.read_text()) or {}
    return data.get("servers", {})


def _save(servers: Dict[str, dict]) -> None:
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERVERS_FILE.write_text(yaml.safe_dump({"servers": servers}, sort_keys=True))


def load_server(name: str) -> Optional[dict]:
    """Look up one registered server. Used by `co deploy --to`."""
    return _load().get(name)


def _ssh(target: str, command: str) -> subprocess.CompletedProcess:
    """Run one command on the target through the system ssh binary.

    We shell out rather than reimplement ssh, so the operator's own agent,
    `~/.ssh/config`, jump hosts and key selection all keep working — the same
    principle as `co browser` driving a real browser.
    """
    return subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",                    # never prompt; fail instead
            "-o", f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
            "-o", "StrictHostKeyChecking=accept-new",
            target,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=SSH_TIMEOUT_SECONDS + 20,
    )


def handle_server_add(name: str, ssh_target: str) -> bool:
    """Register a machine under a short name.

    Takes an ssh target, not a credential. Nothing secret is written.
    """
    if not shutil.which("ssh"):
        console.print("\n[red]No ssh binary found on PATH.[/red]")
        console.print("[dim]co talks to servers through your own ssh, so it needs one installed.[/dim]\n")
        return False

    console.print(f"\n[dim]Checking {ssh_target} …[/dim]")
    result = _ssh(ssh_target, "echo ok")

    if result.returncode != 0:
        # Surface ssh's own words — it explains permission, DNS and host-key
        # problems better than a message we would invent.
        console.print(f"[red]Cannot reach {ssh_target}.[/red]")
        detail = (result.stderr or result.stdout).strip()
        if detail:
            for line in detail.splitlines():
                console.print(f"  [dim]{line}[/dim]")
        console.print("\n[dim]Nothing was saved. Fix the ssh target and try again.[/dim]")
        console.print(f"[dim]Tip: your derived key is [bold]co keys --ssh[/bold] — it has to be in "
                      f"authorized_keys on that host.[/dim]\n")
        return False

    servers = _load()
    existed = name in servers
    servers[name] = {"ssh": ssh_target, "last_check": None}
    _save(servers)

    verb = "Updated" if existed else "Added"
    console.print(f"[green]✓[/green] {verb} [cyan]{name}[/cyan] → {ssh_target}")
    console.print(f"\n[dim]Next:[/dim] co server check {name}\n")
    return True


def handle_server_list() -> bool:
    """Show what you can deploy to."""
    servers = _load()

    if not servers:
        console.print("\n[dim]No servers registered.[/dim]")
        console.print("[cyan]co server add prod --ssh user@host[/cyan]\n")
        return True

    table = Table(box=None, padding=(0, 2))
    table.add_column("NAME", style="cyan")
    table.add_column("TARGET")
    table.add_column("LAST CHECK")

    for name in sorted(servers):
        entry = servers[name] or {}
        last = entry.get("last_check")
        if last is None:
            shown = "[dim]never checked[/dim]"
        elif last == "ok":
            shown = "[green]ok[/green]"
        else:
            shown = f"[red]{last}[/red]"
        table.add_row(name, entry.get("ssh", "[red]?[/red]"), shown)

    console.print()
    console.print(table)
    console.print(f"\n[dim]{_short(SERVERS_FILE)}[/dim]\n")
    return True


def _short(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    return "~" + s[len(home):] if s.startswith(home) else s


# One command, one round trip. Each line is `KEY=value` so a missing tool
# reports as an empty value rather than derailing the whole probe.
_PROBE = r"""
. /etc/os-release 2>/dev/null
echo "distro=${ID:-unknown}"
echo "version=${VERSION_ID:-unknown}"
echo "python=$( (command -v python3 >/dev/null && python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])') 2>/dev/null )"
echo "systemd=$( [ -d /run/systemd/system ] && echo yes )"
echo "systemctl=$( command -v systemctl >/dev/null && echo yes )"
echo "sudo=$( sudo -n true 2>/dev/null && echo yes )"
echo "diskgb=$( df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9' )"
"""


def _parse_probe(stdout: str) -> Dict[str, str]:
    facts = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            facts[key.strip()] = value.strip()
    return facts


def _requirement_failures(facts: Dict[str, str]) -> list:
    """Return the requirements that are not met, each as (name, detail)."""
    failures = []

    if facts.get("distro") != "ubuntu":
        failures.append(("Ubuntu", f"found {facts.get('distro') or 'unknown'}"))
    elif facts.get("version") != SUPPORTED_UBUNTU:
        failures.append(("Ubuntu " + SUPPORTED_UBUNTU, f"found {facts.get('version') or 'unknown'}"))

    python = facts.get("python") or ""
    if not python:
        failures.append(("python3", "not on PATH"))
    else:
        parts = python.split(".")
        if tuple(int(p) for p in parts[:2]) < MIN_PYTHON:
            failures.append((f"python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+", f"found {python}"))

    if facts.get("systemd") != "yes" or facts.get("systemctl") != "yes":
        failures.append(("systemd", "not present"))
    elif facts.get("sudo") != "yes":
        # Managing a unit needs more than systemd existing.
        failures.append(("permission to manage units", "passwordless sudo unavailable"))

    disk = facts.get("diskgb") or ""
    if not disk:
        failures.append(("free disk", "could not read df"))
    elif int(disk) < MIN_FREE_DISK_GB:
        failures.append((f"{MIN_FREE_DISK_GB} GB free disk", f"found {disk} GB"))

    return failures


def handle_server_check(name: str) -> bool:
    """Preflight a target and say which requirement failed, by name."""
    entry = load_server(name)
    if not entry:
        console.print(f"\n[red]No server named '{name}'.[/red]")
        console.print("[cyan]co server ls[/cyan] to see what is registered.\n")
        return False

    target = entry["ssh"]
    console.print(f"\n[dim]Checking {name} ({target}) …[/dim]")

    result = _ssh(target, _PROBE)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        console.print(f"[red]✗ unreachable[/red]")
        for line in detail:
            console.print(f"  [dim]{line}[/dim]")
        _record(name, "unreachable")
        console.print()
        return False

    failures = _requirement_failures(_parse_probe(result.stdout))

    if not failures:
        console.print(f"[green]✓ {name} is ready to deploy to[/green]\n")
        _record(name, "ok")
        return True

    for requirement, detail in failures:
        console.print(f"[red]✗ {requirement}[/red] [dim]— {detail}[/dim]")
    console.print(f"\n[dim]co deploy --to {name} needs all of these. "
                  f"Only Ubuntu {SUPPORTED_UBUNTU} is supported.[/dim]\n")
    _record(name, failures[0][0])
    return False


def _record(name: str, outcome: str) -> None:
    servers = _load()
    if name in servers:
        servers[name]["last_check"] = outcome
        _save(servers)
