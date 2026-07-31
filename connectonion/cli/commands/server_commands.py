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

import re
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


def _identity() -> list:
    """`-i <derived key>` when it is on disk, otherwise nothing.

    A machine from `co server new` has only the derived key installed, so
    without this our own commands cannot reach a server we just sold. Offered
    rather than forced — no IdentitiesOnly — so a box registered by hand with
    `co server add` still opens with whichever key already worked.

    Every path that reaches a server goes through here: preflight, deploy,
    rsync, and the interactive shell. `co server ssh` was the one that did not,
    and it was the one command whose whole purpose is getting you onto the box.
    """
    from .keys_commands import SSH_PRIVATE_KEY

    return ["-i", str(SSH_PRIVATE_KEY)] if SSH_PRIVATE_KEY.exists() else []


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
            *_identity(),
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


def handle_server_ssh(name: str, command: Optional[str] = None) -> bool:
    """Open a shell on a registered server, or run one command there.

    We already hold the target. Making the operator retype an IP defeats the
    point of having registered it.
    """
    entry = load_server(name)
    if not entry:
        console.print(f"\n[red]No server named '{name}'.[/red]")
        console.print("[cyan]co server ls[/cyan] to see what is registered.\n")
        return False

    argv = ["ssh", "-o", "StrictHostKeyChecking=accept-new", *_identity(), entry["ssh"]]
    if command:
        argv.append(command)

    # Hand the terminal over rather than capturing: an interactive shell needs a
    # tty, and a captured one would hang with no prompt visible.
    return subprocess.run(argv).returncode == 0


def handle_server_forget(name: str) -> bool:
    """Drop the local entry. The machine is untouched.

    Deliberately not merged with `destroy`. One of these stops you paying and
    the other does not, and a single verb would mean either a user who thinks
    they stopped the billing and did not, or a user tidying their config who
    deletes a live machine.
    """
    servers = _load()
    if name not in servers:
        console.print(f"\n[red]No server named '{name}'.[/red]\n")
        return False

    target = servers[name].get("ssh", "?")
    del servers[name]
    _save(servers)

    console.print(f"[green]✓[/green] Forgot [cyan]{name}[/cyan] ({target})")
    console.print("\n[yellow]The machine itself is untouched — it keeps running, and if we "
                  "created it, it keeps being billed.[/yellow]")
    console.print("[dim]Tearing one down needs the server API (openonion/oo-api#36); until "
                  "then, delete it where it lives.[/dim]\n")
    return True


API_BASE = "https://oo.openonion.ai"

# Stricter than DEPLOY_NAME_PATTERN, which allows a leading digit: a server name
# becomes the machine's own name, and those must start with a letter. Checked
# here so the answer arrives before the confirmation prompt rather than after the
# charge. The backend enforces the same rule — this only saves the round trip.
SERVER_NAME_PATTERN = re.compile(r"^[a-z]([-a-z0-9]{0,37}[a-z0-9])?$")


def _ensure_ssh_key() -> Optional[str]:
    """The public line to install, having put the private half where ssh looks.

    Both halves, because only installing the public one produces a machine
    nobody can open: the private key is written by `co keys --ssh --write`,
    which nobody has run at this point. Writing it here is not a second secret
    to manage — it is derived from the recovery phrase the operator already has.

    Derived from the operator's identity in ~/.co, not from the nearest project.
    A server belongs to the person who paid for it: the account charged for it
    is the global one, and its key must be too. Deriving from whichever project
    directory you happened to stand in meant `co server new` here and
    `co deploy --to` from another project produced two different keys, and the
    second one was locked out of the machine the first had just bought.
    """
    from ... import address
    from .keys_commands import _find_co_dir, write_derived_ssh_key

    for co_dir in (Path.home() / ".co", _find_co_dir()):
        if not co_dir or not co_dir.exists():
            continue
        data = address.load(co_dir)
        if data and data.get("seed_phrase"):
            write_derived_ssh_key(data["seed_phrase"])
            return address.derive_ssh_key(data["seed_phrase"])["public_line"]
    return None


def _fetch_pricing() -> Optional[dict]:
    import requests

    try:
        response = requests.get(f"{API_BASE}/api/v1/servers/pricing", timeout=15)
    except requests.RequestException:
        return None
    return response.json() if response.status_code == 200 else None


def _confirm(name: str, machine_type: str, pricing: dict, balance: Optional[float]) -> bool:
    """Show what this costs and what is left, then ask.

    Every other `co` command is either free or spends metered credit in
    fractions of a cent. This is the first one that spends a large discrete
    amount, and the verb cannot carry that — `new` is honest about the machine
    and says nothing about the money. The prompt has to.

    Balance-after is shown rather than just the price: what decides whether
    someone can afford it is what is left, not what it costs.

    The monthly figure leads. A server is a monthly thing in everybody's head,
    and "$360" alone is a number nobody can compare to anything they already pay
    for — while "$30 a month" places it immediately. The year is how we charge,
    so it is said too, right next to it, and never instead of it.
    """
    from datetime import datetime, timedelta

    entry = pricing["machine_types"][machine_type]
    price = entry["usd_12mo"]
    months = pricing["term_months"]
    # Published by the backend rather than divided here: one price, one place,
    # and no chance of the CLI rounding its way to a different number than the
    # one on the website. Older backends do not send it — fall back rather than
    # crash, since the yearly price is the one actually charged.
    monthly = entry.get("usd_month")
    if monthly is None:
        monthly = price / months
    expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    console.print()
    console.print(f"  [cyan]name[/cyan]          {name}")
    console.print(f"  [cyan]region[/cyan]        {pricing['region']}")
    console.print(f"  [cyan]machine[/cyan]       {machine_type} [dim]— {entry['description']}[/dim]")
    console.print(f"  [cyan]cost[/cyan]          [bold]${monthly:.0f} / month[/bold] "
                  f"[dim]— ${price:.2f} for {months} months, charged now[/dim]")
    if balance is not None:
        console.print(f"  [cyan]your balance[/cyan]  ${balance:.2f} → "
                      f"[bold]${balance - price:.2f}[/bold] after")
    console.print(f"  [cyan]expires[/cyan]       {expires} "
                  f"[dim]— the server stops on that date unless renewed[/dim]")
    console.print()

    import questionary
    return bool(questionary.confirm("Create it?", default=False).ask())


def handle_server_new(name: str, machine_type: Optional[str] = None,
                      yes: bool = False) -> bool:
    """Have a server created for you, and register it locally."""
    import requests

    from .project_cmd_lib import load_api_key

    if not SERVER_NAME_PATTERN.match(name):
        console.print(f"\n[red]Invalid server name: {name}[/red]")
        console.print("[dim]1-39 lowercase letters, digits and hyphens, starting with a "
                      "letter — it becomes the machine's name.[/dim]\n")
        return False

    if load_server(name):
        console.print(f"\n[red]'{name}' is already registered locally.[/red]")
        console.print(f"[dim]co server ls  ·  or pick another name[/dim]\n")
        return False

    api_key = load_api_key()
    if not api_key:
        console.print("\n[red]Not authenticated.[/red]")
        console.print("[cyan]co auth[/cyan] first — creating a server spends credit.\n")
        return False

    ssh_public_line = _ensure_ssh_key()
    if not ssh_public_line:
        console.print("\n[red]No SSH key to install.[/red]")
        console.print("[dim]The key is derived from your recovery phrase; without it the "
                      "server would be created with no way in.[/dim]")
        console.print("[cyan]co keys --ssh[/cyan] to check.\n")
        return False

    pricing = _fetch_pricing()
    if not pricing:
        console.print(f"\n[red]Could not reach {API_BASE} for pricing.[/red]")
        console.print("[dim]Nothing was created or charged.[/dim]\n")
        return False

    machine_type = machine_type or pricing["default"]
    if machine_type not in pricing["machine_types"]:
        console.print(f"\n[red]Unknown machine type: {machine_type}[/red]")
        console.print(f"[dim]Available: {', '.join(sorted(pricing['machine_types']))}[/dim]\n")
        return False

    if not yes:
        if not _confirm(name, machine_type, pricing, _fetch_balance(api_key)):
            console.print("[dim]Nothing was created or charged.[/dim]\n")
            return False

    console.print(f"\n[dim]Creating {name} … this takes about a minute.[/dim]")
    try:
        response = requests.post(
            f"{API_BASE}/api/v1/servers",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"name": name, "ssh_public_key": ssh_public_line,
                  "machine_type": machine_type},
            timeout=300,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Request failed: {exc}[/red]")
        console.print("[dim]If the server was created you will see it in "
                      "[bold]co server ls[/bold].[/dim]\n")
        return False

    if response.status_code != 200:
        _report_failure(response)
        return False

    server = response.json()

    # Register it ourselves so the operator never types an IP.
    servers = _load()
    servers[name] = {"ssh": server["ssh_target"], "last_check": None}
    _save(servers)

    console.print(f"\n[green]✓ {name} is ready[/green]")
    console.print(f"  [cyan]{server['ssh_target']}[/cyan]")
    console.print(f"  [dim]expires {server['expires_at'][:10]} — "
                  f"${server['charged_usd']:.2f} charged[/dim]")
    console.print(f"\n[dim]Next:[/dim] co server check {name}  ·  co deploy --to {name}\n")
    return True


def _fetch_balance(api_key: str) -> Optional[float]:
    """What is actually left to spend. Best effort — the prompt is more useful
    with it and still works without.

    `balance_usd`, not `credits_usd`. The latter is lifetime top-ups and ignores
    everything already spent, so an account that had added $315 and spent $291
    reads as $315 of headroom. The prompt would then tell someone a $180 server
    leaves them $135, they say yes, and the backend correctly refuses with 402 —
    a purchase they were just told they could afford. The same confusion is what
    openonion/oo-api#42 fixed inside the balance check; this is the display side
    of it, and `co status` and `co auth` already read the right field.
    """
    import requests

    try:
        response = requests.get(f"{API_BASE}/api/v1/auth/me",
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        if response.status_code == 200:
            value = response.json().get("balance_usd")
            return float(value) if value is not None else None
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None


def _report_failure(response) -> None:
    """Say what happened to the money, first."""
    try:
        detail = response.json().get("detail", {})
    except ValueError:
        detail = {}

    if isinstance(detail, str):
        console.print(f"\n[red]{detail}[/red]\n")
        return

    error = detail.get("error")
    if error == "insufficient_credits":
        console.print(f"\n[red]Not enough credit.[/red]")
        console.print(f"  have      ${detail.get('balance', 0):.2f}")
        console.print(f"  need      ${detail.get('required', 0):.2f}")
        console.print(f"  short by  [bold]${detail.get('shortfall', 0):.2f}[/bold]")
        console.print("\n[dim]Nothing was created or charged.[/dim]")
        console.print("[dim]https://discord.gg/4xfD9k8AUF to top up.[/dim]\n")
    elif error == "provisioning_failed":
        colour = "yellow" if detail.get("refunded") else "red"
        console.print(f"\n[{colour}]{detail.get('message', 'Provisioning failed.')}[/{colour}]\n")
    else:
        console.print(f"\n[red]Server creation failed ({response.status_code}).[/red]")
        console.print(f"[dim]{detail or response.text[:300]}[/dim]\n")
