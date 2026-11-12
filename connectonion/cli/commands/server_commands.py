"""
Purpose: Register, list and preflight the machines `co deploy --to` can target
LLM-Note:
  Dependencies: imports from [subprocess, shutil, pathlib, yaml, rich] | imported by [cli/main.py via handle_server_*] | tested by [tests/unit/test_server_commands.py]
  Data flow: handle_server_add(name, ssh_target) → _load()/_save() ~/.co/servers.yaml → handle_server_list() renders the table | handle_server_check(name) → _ssh(target, probe script) → parses one KEY=value line per requirement → prints every failure by name, and caches the first as `needs <requirement>` (the bare name read as a fact about the server in the LAST CHECK column)
  State/Effects: reads and writes ~/.co/servers.yaml (name → ssh target, last check result) | shells out to the system ssh binary | never stores a credential
  Integration: exposes handle_server_add(), handle_server_list(), handle_server_check(), handle_server_new(), handle_server_destroy(), handle_server_invoice(), load_server() for deploy | requirement list is Ubuntu 24.04, python 3.11+, systemd the user may manage, free disk
  Billing: oo-api /servers/pricing `billing == "monthly_in_arrears"` selects the monthly wording (nothing charged at create, each month charged when it ends, destroy charges the used part, invoices); without it the backend is the older 12-months-up-front one and the prepaid wording is kept | amounts are always the backend's, never recomputed (the pre-create quote uses the formula the backend publishes) | --pdf is drawn with pypdf, already a dependency
  Performance: one ssh round trip per check; the probe is a single command, not one per requirement
  Errors: an unreachable host fails with ssh's own message and a short timeout, never a hang | a missing requirement is named
"""

import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

import yaml
from rich.console import Console
from rich.table import Table

from ...backend import backend_url

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
    """Replace the whole registry. Prefer _update() unless you mean to."""
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _write_atomically(SERVERS_FILE, yaml.safe_dump({"servers": servers}, sort_keys=True))


def _write_atomically(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory, then rename.

    `write_text` truncates before it writes, so a process killed in between —
    or two writing at once — leaves a file that parses as an empty registry.
    A rename on the same filesystem is atomic: readers see the old file or the
    new one, never half of either.
    """
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


@contextmanager
def _registry_lock():
    """Hold the registry while reading and writing it.

    `co server new` reads the file, spends a minute creating a machine, and
    writes it back. Anything else that registered in that minute was silently
    dropped — including by another session on the same laptop, which is the
    normal case here rather than an exotic one. The operator is charged either
    way, and the entry that vanishes is the one nothing points at.
    """
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = SERVERS_FILE.with_suffix(".lock")
    with open(lock_path, "w") as handle:
        try:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        except (ImportError, OSError):
            # Windows, or a filesystem without flock. Losing an entry is worse
            # than not locking, but crashing here would be worse than both.
            pass
        yield


def _update(mutate) -> Dict[str, dict]:
    """Read, change and write the registry without losing a concurrent change.

    The read happens inside the lock, so `co server new` picks up anything that
    landed while it was waiting on the API rather than overwriting it.
    """
    with _registry_lock():
        servers = _load()
        mutate(servers)
        _save(servers)
        return servers


def load_server(name: str) -> Optional[dict]:
    """Look up one registered server. Used by `co deploy --to`."""
    return _load().get(name)


def _identity(target: str = None) -> list:
    """The keys to offer for this target, most specific first.

    A machine from `co server new` has only a derived key installed, so without
    this our own commands cannot reach a server we just sold. Offered rather
    than forced — no IdentitiesOnly — so a box registered by hand with
    `co server add` still opens with whichever key already worked.

    Two are offered during the migration in #427: the per-server key from the
    SLIP-0010 tree, and the older single key that is in `authorized_keys` on
    every machine provisioned before it. Dropping the old one before every
    server carries the new line would lock us out of boxes we own, and the way
    back in *is* the key. ssh tries them in order and stops at the first that
    works, so a machine holding either is reachable.

    Every path that reaches a server goes through here: preflight, deploy,
    rsync, and the interactive shell.
    """
    from .keys_commands import per_host_key_path

    keys = []
    name = _server_name(target)
    if name and per_host_key_path(name).exists():
        keys += ["-i", str(per_host_key_path(name))]
    return keys


def _server_name(target: str = None) -> Optional[str]:
    """The registered name for a server, given its name or its ssh target.

    Callers hold one or the other — `co server ssh` has the name, the deploy
    helpers have `root@<ip>` — and the per-server key is derived from the name.
    The name and not the address, because the address does not exist yet at the
    moment the key has to be chosen: it is sent in the request that creates the
    machine, and GCE only answers with an IP afterwards.
    """
    if not target:
        return None
    servers = _load()
    if target in servers:
        return target
    for name, entry in servers.items():
        if entry.get("ssh") == target:
            return name
    return None


def _ssh(target: str, command: str) -> subprocess.CompletedProcess:
    """Run one command on the target through the system ssh binary.

    We shell out rather than reimplement ssh, so the operator's own agent,
    `~/.ssh/config`, jump hosts and key selection all keep working — the same
    principle as `co browser` driving a real browser.
    """
    argv = [
        "ssh",
        "-o", "BatchMode=yes",                    # never prompt; fail instead
        "-o", f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
        "-o", "StrictHostKeyChecking=accept-new",
        *_identity(target),
        target,
        command,
    ]
    limit = SSH_TIMEOUT_SECONDS + 20
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        # ConnectTimeout covers a refused connection; this covers one that is
        # accepted and then never answers. Same shape as any other failed probe,
        # so `co server check` reports it instead of crashing.
        return subprocess.CompletedProcess(
            argv, returncode=124,
            stdout="",
            stderr=f"ssh to {target} timed out after {limit}s — the server did not answer.",
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
        console.print("[dim]Tip: your derived key is [bold]co keys --ssh[/bold] — it has to be in "
                      "authorized_keys on that host.[/dim]\n")
        return False

    existed = name in _load()
    _update(lambda servers: servers.update(
        {name: {"ssh": ssh_target, "last_check": None}}))

    verb = "Updated" if existed else "Added"
    console.print(f"[green]✓[/green] {verb} [cyan]{name}[/cyan] → {ssh_target}")
    console.print(f"\n[dim]Next:[/dim] co server check {name}\n")
    return True


def handle_server_list() -> bool:
    """Show what you can deploy to, reconciled against what you are billed for.

    ~/.co/servers.yaml is a cache, not the ledger. Once a server costs money the
    backend is the truth, and the row that matters is the one the local file
    cannot produce: **billed for, not registered here**. That is someone paying
    for a machine `co` would otherwise never show them — created on another
    laptop, or dropped with `co server forget`.

    The billing lookup is best-effort. Being offline, or not authenticated, must
    not stop you listing your own deploy targets.
    """
    servers = _load()
    billed = _fetch_billed_servers()

    if not servers and not billed:
        console.print("\n[dim]No servers registered.[/dim]")
        console.print("[cyan]co server new prod[/cyan]  or  "
                      "[cyan]co server add prod --ssh user@host[/cyan]\n")
        return True

    table = Table(box=None, padding=(0, 2))
    table.add_column("NAME", style="cyan")
    table.add_column("TARGET")
    table.add_column("LAST CHECK")
    if billed is not None:
        table.add_column("BILLING")

    billed_by_name = {s["name"]: s for s in (billed or [])}

    for name in sorted(servers):
        entry = servers[name] or {}
        last = entry.get("last_check")
        age = _how_long_ago(entry.get("last_check_at"))
        if last is None:
            shown = "[dim]never checked[/dim]"
        elif last == "ok":
            shown = "[green]ok[/green]"
        else:
            shown = f"[red]{last}[/red]"
        if age:
            # An entry from before stamping has no age, and inventing one would
            # be worse than leaving the column as it was.
            shown += f" [dim]{age}[/dim]"

        row = [name, entry.get("ssh", "[red]?[/red]"), shown]
        if billed is not None:
            record = billed_by_name.get(name)
            row.append(_billing_cell(record) if record else "[dim]not ours[/dim]")
        table.add_row(*row)

    # The expensive row: charged for, absent locally.
    unregistered = [s for s in (billed or []) if s["name"] not in servers]
    for record in unregistered:
        table.add_row(
            f"[yellow]{record['name']}[/yellow]",
            f"[dim]{record.get('ssh_target') or '—'}[/dim]",
            "[yellow]not registered here[/yellow]",
            _billing_cell(record),
        )

    console.print()
    console.print(table)

    if unregistered:
        names = ", ".join(s["name"] for s in unregistered)
        console.print(f"\n[yellow]{len(unregistered)} server(s) you are billed for are not "
                      f"registered on this machine:[/yellow] {names}")
        console.print("[dim]co server add <name> --ssh <target>   to use one from here[/dim]")
        console.print("[dim]co server destroy <name>              to stop paying for one[/dim]")
    _print_moved_addresses(servers, billed or [])
    _print_grace(billed or [])
    _print_balance_cover(billed or [])

    console.print(f"\n[dim]{_short(SERVERS_FILE)}[/dim]")
    console.print("[dim]Preflight one:[/dim] [bold]co server check <name from this list>[/bold]\n")
    return True


def _fetch_billed_servers():
    """What the backend says this account owns, or None if we could not ask.

    None and [] mean different things and the caller depends on it: [] is "you
    own nothing", None is "we do not know", and only the first justifies telling
    someone their registry is complete.
    """
    import requests

    from .project_cmd_lib import load_api_key

    api_key = load_api_key()
    if not api_key:
        return None

    try:
        response = requests.get(f"{backend_url()}/api/v1/servers",
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None
    try:
        return response.json().get("servers", [])
    except ValueError:
        return None


def _billing_cell(record: dict) -> str:
    """One server's money, in the backend's numbers: price, next charge, so far, owed.

    Three shapes, because three kinds of server exist at once: monthly in
    arrears, a year bought on the old term and not yet run out, and any server
    from a backend before monthly billing (no `billing` key at all).
    """
    billing = record.get("billing")
    if billing == "prepaid_12_months":
        return f"[dim]prepaid until {record['prepaid_until'][:10]}[/dim]"
    if billing != "monthly_in_arrears":
        return f"[dim]until {record['expires_at'][:10]}[/dim]"
    if record.get("status") == "suspended":
        return (f"[red]suspended for non-payment — ${record['unpaid_usd']:.2f} unpaid, "
                f"disk kept[/red]")
    if record.get("status") == "suspending":
        return f"[red]stopping for non-payment — ${record['unpaid_usd']:.2f} unpaid[/red]"
    if record.get("status") == "deleting":
        return "[dim]being deleted[/dim]"
    cell = (f"${record['usd_month']:.2f}/mo · next charge {record['next_charge_at'][:10]} · "
            f"${record['accrued_usd']:.2f} so far")
    if record.get("unpaid_usd"):
        cell += f" · [red]${record['unpaid_usd']:.2f} unpaid[/red]"
    return cell


def _print_moved_addresses(servers: Dict[str, dict], billed: list) -> None:
    """A suspended server comes back on a new IP; say so before a deploy hits the old one."""
    for record in billed:
        entry = servers.get(record["name"]) or {}
        target = record.get("ssh_target")
        if entry.get("ssh") and target and entry["ssh"] != target:
            console.print(f"\n[yellow]{record['name']} now answers at {target}, "
                          f"not {entry['ssh']}.[/yellow]")
            console.print(f"[dim]co server add {record['name']} --ssh {target}   "
                          f"to update this machine's entry[/dim]")


def _print_grace(billed: list) -> None:
    """For a server that owes a month: when it stops and when it is deleted.

    The days come from `pricing.unpaid`, counted from the end of the unpaid
    month. A server that is still running and owes is in its first unpaid
    month (it stops three days in, by default), whose end is where its open
    month began.
    """
    owing = [s for s in billed
             if s.get("billing") == "monthly_in_arrears" and s.get("unpaid_usd")]
    if not owing:
        return
    timeline = (_fetch_pricing() or {}).get("unpaid")
    if not timeline:
        return
    for record in owing:
        console.print(f"\n[yellow]{_grace_line(record, timeline)}[/yellow]")


def _grace_line(record: dict, timeline: dict) -> str:
    from datetime import datetime, timedelta

    owes = f"{record['name']} owes ${record['unpaid_usd']:.2f}"
    if not record.get("period_start"):
        return (f"{owes} and is stopped; it is deleted {timeline['delete_after_days']} days "
                f"after its month went unpaid unless you top up.")
    unpaid_since = datetime.fromisoformat(record["period_start"])
    stop = (unpaid_since + timedelta(days=timeline["stop_after_days"])).date()
    delete = (unpaid_since + timedelta(days=timeline["delete_after_days"])).date()
    return f"{owes}: it stops on {stop} and is deleted on {delete} unless you top up."


def _print_balance_cover(billed: list) -> None:
    """Will the balance pay the next month-end charges? Best effort, like the lookup.

    The balance is shared by every server, so the comparison is against all of
    them together: each running one's month plus anything already owed.
    """
    from .project_cmd_lib import load_api_key

    monthly = [s for s in billed if s.get("billing") == "monthly_in_arrears"]
    if not monthly:
        return
    balance = _fetch_balance(load_api_key())
    if balance is None:
        return
    stopped = ("suspending", "suspended", "deleting")
    due = sum((s.get("unpaid_usd") or 0)
              + (0 if s.get("status") in stopped else s.get("usd_month") or 0)
              for s in monthly)
    dates = sorted(s["next_charge_at"][:10] for s in monthly if s.get("next_charge_at"))
    if balance >= due:
        console.print(f"\n[dim]Balance ${balance:.2f} covers the next month of these "
                      f"servers (${due:.2f}).[/dim]")
        return
    console.print(f"\n[yellow]Balance ${balance:.2f} does not cover the next month of these "
                  f"servers (${due:.2f}).[/yellow]")
    when = f" before {dates[0]}" if dates else ""
    console.print(f"[dim]A month left unpaid stops the server, then deletes it. "
                  f"Top up{when}: https://discord.gg/4xfD9k8AUF[/dim]")


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
        console.print("[red]✗ unreachable[/red]")
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
    _record_requirement_failure(name, failures[0][0])
    return False


def _record_requirement_failure(name: str, requirement: str) -> None:
    """Cache an unmet requirement as a verdict, not as its own name.

    The requirement names are bare nouns — Ubuntu 24.04, python3, systemd,
    permission to manage units — and under a column headed LAST CHECK they read
    as facts about the server. A real listing showed

        nw-runner    claude-runner     Ubuntu 24.04    not ours

    for a machine running Ubuntu 22.04, so the cell stated the opposite of the
    truth. Red was the only thing marking it as bad news, and that is lost the
    moment anyone pipes the output.

    "needs" reads correctly for every one of them, and matches the line already
    printed under a failed check: "co deploy --to <name> needs all of these".
    """
    _record(name, f"needs {requirement}")


def _record(name: str, outcome: str) -> None:
    """Store the outcome and when it was learned.

    `co server ls` renders this cache and does not probe — deliberately, so that
    being offline still lists your targets. Without a time next to it, a server
    that passed once and died since reads `ok` forever under a column named
    LAST CHECK, and that is the table you look at before `co deploy --to`.
    """
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def note(servers):
        if name in servers:
            servers[name]["last_check"] = outcome
            servers[name]["last_check_at"] = stamp

    _update(note)


def _how_long_ago(stamp: Optional[str]) -> str:
    """"3d", "20m", "just now" — or "" for an entry written before stamping."""
    if not stamp:
        return ""
    from datetime import datetime, timezone

    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)

    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 60:
        return "just now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


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

    argv = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
            *_identity(entry["ssh"]), entry["ssh"]]
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
    _update(lambda s: s.pop(name, None))

    console.print(f"[green]✓[/green] Forgot [cyan]{name}[/cyan] ({target})")
    console.print("\n[yellow]The machine itself is untouched — it keeps running, and if we "
                  "created it, it keeps being billed.[/yellow]")
    console.print(f"[dim]To stop paying for it:  co server destroy {name}[/dim]\n")
    return True


def handle_server_destroy(name: str, yes: bool = False) -> bool:
    """Tear the machine down for real, and drop the local entry with it.

    The opposite of `forget` in the only way that matters: this one stops the
    billing and cannot be undone. So it asks for the name back rather than a
    y/N — a reflex "y" is exactly how someone deletes production while meaning
    to tidy their config, and typing the name cannot be done by reflex.
    """
    import requests

    from .project_cmd_lib import load_api_key

    api_key = load_api_key()
    if not api_key:
        console.print("\n[red]Not authenticated.[/red]")
        console.print("[cyan]co auth[/cyan] first — destroying a server is a billing "
                      "operation.\n")
        return False

    record = {s["name"]: s for s in (_fetch_billed_servers() or [])}.get(name)
    if not yes:
        console.print(f"\n[red]This destroys the machine '{name}' and everything on it.[/red]")
        console.print("[dim]The disk, the agent's identity, its logs — none of it is "
                      "recoverable.[/dim]")
        console.print(f"[dim]{_destroy_terms(record)}[/dim]")
        console.print()

        import questionary
        typed = questionary.text(f"Type the server name to confirm ({name}):").ask()
        if typed != name:
            console.print("[dim]Nothing was destroyed.[/dim]\n")
            return False

    console.print(f"\n[dim]Destroying {name} …[/dim]")
    try:
        response = requests.delete(
            f"{backend_url()}/api/v1/servers/{name}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Request failed: {exc}[/red]")
        console.print("[dim]The server may still exist. Check with "
                      "[bold]co server ls[/bold].[/dim]\n")
        return False

    if response.status_code == 404:
        console.print(f"[red]No server named '{name}' on your account.[/red]")
        console.print("[dim]If it is only a local entry, use "
                      f"[bold]co server forget {name}[/bold].[/dim]\n")
        return False

    if response.status_code != 200:
        _report_failure(response)
        return False

    # Only now drop the local entry: while the machine existed the entry was
    # true, and removing it on a failed delete would hide a server still billing.
    _update(lambda servers: servers.pop(name, None))

    console.print(f"[green]✓ {name} destroyed[/green]")
    result = response.json() if response.content else {}
    if result.get("billing") == "monthly_in_arrears":
        _print_final_charge(name, result, (record or {}).get("unpaid_usd") or 0)
    else:
        _print_refund(result)
    return True


def _destroy_terms(record: Optional[dict]) -> str:
    """What destroying this server does to the money, said before it happens.

    Read from the backend's own record of the server: a monthly one is charged
    for the part of the month it ran, a year bought on the old term refunds
    what is left of it. When the lookup fails we do not guess which.
    """
    if record is None:
        return "Whatever it owes or is owed is settled now and shown below."
    if record.get("billing") == "monthly_in_arrears":
        return _monthly_destroy_terms(record.get("accrued_usd") or 0, record.get("unpaid_usd") or 0)
    if record.get("billing") == "prepaid_12_months":
        return "The unused part of the year it was bought for is refunded to your credit."
    return "The unused part of the term is refunded to your credit."


def _monthly_destroy_terms(accrued: float, owed: float) -> str:
    """A server that already owes is not charged at a destroy: the used part joins the debt."""
    if owed and accrued:
        return (f"The used part of this month (about ${accrued:.2f}) is added to what you "
                f"owe (${owed:.2f} unpaid), and the monthly billing stops.")
    if owed:
        return f"The monthly billing stops; the ${owed:.2f} unpaid stays owed."
    if accrued:
        return (f"The used part of this month (about ${accrued:.2f}) is charged now, and "
                f"the monthly billing stops.")
    return "The monthly billing stops."


def _print_final_charge(name: str, result: dict, owed_before: float) -> None:
    """What the backend did with the used part, then everything still owed for this server.

    The response's `unpaid_usd` is only this destroy's part; what the server
    already owed was read before the delete, so the total is said once more.
    """
    if result.get("charged_usd"):
        console.print(f"[dim]${result['charged_usd']:.2f} charged for the used part of this "
                      f"month — invoice {result.get('invoice_number')}.[/dim]")
        console.print(f"[dim]co server invoice {name} {result.get('invoice_number')}   "
                      f"to see it[/dim]")
    if result.get("unpaid_usd"):
        console.print(f"[yellow]${result['unpaid_usd']:.2f} for the used part of this month "
                      f"was recorded as unpaid.[/yellow]")
    owed = owed_before + (result.get("unpaid_usd") or 0)
    if owed:
        console.print(f"[yellow]You still owe ${owed:.2f} for {name}; it is charged at your "
                      f"next top-up: https://discord.gg/4xfD9k8AUF[/yellow]")
    if not result.get("charged_usd") and not owed:
        console.print("[dim]Nothing charged.[/dim]")
    console.print()


def _print_refund(result: dict) -> None:
    """A year bought up front: the unused part comes back, as an amount."""
    # State the amount, not the policy. "Prorated" tells the user nothing they
    # can check; a number against what they paid does.
    refunded = result.get("refunded_usd")
    if refunded:
        charged = result.get("charged_usd")
        against = f" of ${charged:.2f}" if charged else ""
        console.print(f"[dim]${refunded:.2f}{against} refunded to your credit — "
                      f"the unused part of the term.[/dim]\n")
    else:
        console.print("[dim]Nothing refunded — the term had already run out.[/dim]\n")


# Stricter than DEPLOY_NAME_PATTERN, which allows a leading digit: a server name
# becomes the machine's own name, and those must start with a letter. Checked
# here so the answer arrives before the confirmation prompt rather than after the
# charge. The backend enforces the same rule — this only saves the round trip.
SERVER_NAME_PATTERN = re.compile(r"^[a-z]([-a-z0-9]{0,37}[a-z0-9])?$")


def _ensure_ssh_key(name: str = None) -> Optional[str]:
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
    from .keys_commands import _find_co_dir, write_per_host_ssh_key

    if not name:
        return None

    for co_dir in (Path.home() / ".co", _find_co_dir()):
        if not co_dir or not co_dir.exists():
            continue
        data = address.load(co_dir)
        if data and data.get("seed_phrase"):
            write_per_host_ssh_key(data["seed_phrase"], name)
            return address.derive_ssh_key(data["seed_phrase"], host=name)["public_line"]
    return None


def _ssh_public_lines(name: str = None) -> list:
    """The public line to put in a server's authorized_keys.

    One line, for this server. The migration in #427 installed two for a while --
    the per-server key from the tree and an older shared one -- so that machines
    provisioned before the tree existed stayed reachable. Step 4 retired the
    shared key: every live server was checked to open with its own key alone
    before this landed, and a machine that still holds only the old line has to
    be re-provisioned rather than kept on a key nobody can derive any more.
    """
    line = _ensure_ssh_key(name)
    return [line] if line else []


def _fetch_pricing() -> Optional[dict]:
    import requests

    try:
        response = requests.get(f"{backend_url()}/api/v1/servers/pricing", timeout=15)
    except requests.RequestException:
        return None
    return response.json() if response.status_code == 200 else None


def _monthly(pricing: Optional[dict]) -> bool:
    """Is this backend billing servers monthly in arrears (oo-api #287)?

    The backend before it charged twelve months at create and sends no
    `billing` key. Everything that talks about money asks this first, so the
    CLI never tells someone "nothing is charged now" against a backend that is
    about to charge them a year.
    """
    return (pricing or {}).get("billing") == "monthly_in_arrears"


def _monthly_price(pricing: dict, machine_type: str, disk_gb: int) -> float:
    """The quote shown before create, by the formula the backend publishes.

    The create response's `usd_month` is authoritative and is what is printed
    afterwards; this only exists because the prompt has to come first.
    """
    disk = pricing["disk"]
    extra = round((disk_gb - disk["included_gb"]) * disk["usd_per_gb_month"], 2)
    return round(pricing["machine_types"][machine_type]["usd_month"] + extra, 2)


def _confirm(name: str, machine_type: str, region: str, pricing: dict,
            balance: Optional[float], disk_gb: Optional[int] = None) -> bool:
    """Show what this costs and what is left, then ask.

    Every other `co` command is either free or spends metered credit in
    fractions of a cent. A server is a large recurring amount, and the verb
    cannot carry that — `new` is honest about the machine and says nothing
    about the money. The prompt has to.
    """
    entry = pricing["machine_types"][machine_type]

    console.print()
    console.print(f"  [cyan]name[/cyan]          {name}")
    console.print(f"  [cyan]region[/cyan]        {region}")
    console.print(f"  [cyan]machine[/cyan]       {machine_type} [dim]— {entry['description']}[/dim]")
    if _monthly(pricing):
        stake = _print_monthly_terms(pricing, machine_type, disk_gb, balance)
    else:
        stake = _print_prepaid_terms(pricing, entry, balance)
    console.print()
    if not stake:
        console.print("[dim]https://discord.gg/4xfD9k8AUF to top up.[/dim]")
        return False

    # Nothing can be answered on a stdin that is not a terminal, and the prompt
    # library does not decline politely — it registers the descriptor with
    # asyncio and raises OSError: [Errno 22]. On the one command that spends
    # money, a bare traceback also leaves the reader unable to tell whether the
    # charge went through.
    if not sys.stdin.isatty():
        console.print(
            f"[red]Cannot confirm: stdin is not a terminal.[/red]\n"
            f"  {stake} "
            f"Re-run with [bold]--yes[/bold] to confirm without being asked."
        )
        return False

    import questionary
    return bool(questionary.confirm("Create it?", default=False).ask())


def _print_monthly_terms(pricing: dict, machine_type: str, disk_gb: Optional[int],
                         balance: Optional[float]) -> str:
    """Monthly in arrears: nothing now, a month's price at each month end.

    The balance line answers the one question that decides the create. The
    backend counts every live server's month plus anything owed; this server's
    month alone is a floor of that, so a balance below it returns "" and the
    prompt is never shown. Anything else short is the backend's to refuse,
    in its own words.
    """
    disk = pricing["disk"]
    disk_gb = disk_gb or disk["default_gb"]
    monthly = _monthly_price(pricing, machine_type, disk_gb)
    required = monthly * pricing.get("minimum_balance_months", 1)

    console.print(f"  [cyan]disk[/cyan]          {disk_gb} GB {disk['type']} "
                  f"[dim]— {disk['included_gb']} GB included, "
                  f"${disk['usd_per_gb_month']:.2f} / GB / month beyond[/dim]")
    console.print(f"  [cyan]cost[/cyan]          [bold]${monthly:.2f} / month[/bold] "
                  f"[dim]— charged at the end of each month from credits; "
                  f"nothing is charged now[/dim]")
    if balance is not None and balance >= required:
        console.print(f"  [cyan]your balance[/cyan]  ${balance:.2f} [dim]— must cover a month of "
                      f"every server you have, plus anything unpaid[/dim]")
    elif balance is not None:
        console.print(f"  [cyan]your balance[/cyan]  [red]${balance:.2f} — below one month "
                      f"(${required:.2f}), which the backend requires[/red]")
        return ""
    return f"Nothing would be charged now; ${monthly:.2f} at the end of each month."


def _print_prepaid_terms(pricing: dict, entry: dict, balance: Optional[float]) -> str:
    """The backend before monthly billing: twelve months, charged at create.

    Kept for as long as that backend is the one in production, so the prompt
    states the charge it is about to make rather than the one we plan to.
    """
    from datetime import datetime, timedelta

    price = entry["usd_12mo"]
    months = pricing["term_months"]
    monthly = entry.get("usd_month")
    if monthly is None:
        monthly = price / months
    expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    console.print(f"  [cyan]cost[/cyan]          [bold]${monthly:.0f} / month[/bold] "
                  f"[dim]— ${price:.2f} for {months} months, charged now[/dim]")
    if balance is not None:
        console.print(f"  [cyan]your balance[/cyan]  ${balance:.2f} → "
                      f"[bold]${balance - price:.2f}[/bold] after")
    console.print(f"  [cyan]expires[/cyan]       {expires} "
                  f"[dim]— the server stops on that date unless renewed[/dim]")
    return f"${price:.2f} would be charged now."


def _forget_host_key(ssh_target: str) -> None:
    """Drop any host key we hold for this address.

    Cloud providers reuse addresses. When one comes back attached to a machine
    we just created, the key in known_hosts belongs to a machine that no longer
    exists, and ssh refuses with a warning about a possible attack —
    StrictHostKeyChecking=accept-new covers a host it has never seen, not one
    whose key changed. The operator's first command after paying for a server
    then fails, alarmingly, for a reason that is entirely our doing.

    Safe here precisely because we are the ones who created the machine: we know
    the previous key is dead. Nothing else in `co` removes host keys.
    """
    host = ssh_target.split("@")[-1]
    subprocess.run(["ssh-keygen", "-R", host], capture_output=True, text=True)


# The machine answers on 22 before the guest agent has copied our key into
# authorized_keys — about ten seconds, in practice.
KEY_INSTALL_TIMEOUT_SECONDS = 120


def _wait_until_it_accepts_your_key(ssh_target: str, name: str = "<name>") -> bool:
    """Block until the machine actually lets you in.

    The API returns as soon as the instance has an address, which is before the
    key works. Printing "✓ ready" then suggesting `co server check` next meant
    the very next command answered "Permission denied (publickey)" — the most
    alarming way to say "wait ten seconds", on a machine just paid for.

    Returns False on timeout rather than failing the command: the server exists
    and is charged for either way, so the honest thing is to say what is true
    and let the operator retry.
    """
    import time

    deadline = time.monotonic() + KEY_INSTALL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _ssh(ssh_target, "echo ok").returncode == 0:
            return True
        time.sleep(3)

    console.print("[yellow]It is not accepting your key yet.[/yellow]")
    console.print("[dim]The machine exists and is charged for. Usually a slow first "
                  "boot — try [bold]co server check[/bold] in a minute.[/dim]")
    console.print(f"[dim]If it still refuses: [bold]co server fix-key {name}[/bold] "
                  f"reinstalls the key on the machine you already paid for.[/dim]")
    return False


def derived_agent_identity(name: str) -> Optional[dict]:
    """The identity `name` will have, derived from the operator's phrase.

    The same name always returns the same key, so an agent's address can be
    printed before it is deployed and recomputed after its machine is gone —
    which is the whole of #396. Letting the server mint one on first boot gives
    an address nobody can know in advance and nobody can recover once the disk
    is gone: #306's failure mode moved up a level, from "changes every deploy"
    to "changes every machine", which is rarer and therefore worse.

    Derived from ~/.co rather than from the project, for the same reason the SSH
    key is: a server belongs to the operator, as does the account charged for it.
    """
    from mnemonic import Mnemonic
    from nacl.signing import SigningKey

    from ... import address as address_mod
    from ...derive import derive_path, identity_uri, slip13_path
    from .keys_commands import _find_co_dir

    for co_dir in (Path.home() / ".co", _find_co_dir()):
        if not co_dir or not co_dir.exists():
            continue
        data = address_mod.load(co_dir)
        if not (data and data.get("seed_phrase")):
            continue

        seed = Mnemonic("english").to_seed(data["seed_phrase"])
        signing_key = SigningKey(derive_path(seed, slip13_path(identity_uri(name))))
        return {
            "address": "0x" + bytes(signing_key.verify_key).hex(),
            "key_bytes": bytes(signing_key),
        }
    return None


def handle_server_fix_key(name: str) -> bool:
    """Reinstall the derived key on a server you already own.

    The route out of a machine that was charged for and never accepted the key.
    Before this the only repair was destroy and pay again — the wait said "try
    again in a minute", and trying again did the same thing.

    Also the repair after rotating: the derived key changes and the machine
    should follow it, without losing what is on the disk.
    """
    import requests

    from .project_cmd_lib import load_api_key

    entry = load_server(name)
    if not entry:
        console.print(f"\n[red]No server named '{name}'.[/red]")
        console.print("[cyan]co server ls[/cyan] to see what is registered.\n")
        return False

    api_key = load_api_key()
    if not api_key:
        console.print("\n[red]Not authenticated.[/red]")
        console.print("[cyan]co auth[/cyan] first — the key is reinstalled through "
                      "the server API.\n")
        return False

    ssh_public_line = _ensure_ssh_key(name)
    if not ssh_public_line:
        console.print("\n[red]No SSH key to install.[/red]")
        console.print("[dim]It is derived from your recovery phrase. "
                      "[bold]co keys --ssh[/bold] to check.[/dim]\n")
        return False

    console.print(f"\n[dim]Reinstalling your key on {name} …[/dim]")
    try:
        response = requests.post(
            f"{backend_url()}/api/v1/servers/{name}/key",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"ssh_public_key": ssh_public_line},
            timeout=120,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Request failed: {exc}[/red]\n")
        return False

    if response.status_code != 200:
        _report_failure(response)
        return False

    _forget_host_key(entry["ssh"])
    if _wait_until_it_accepts_your_key(entry["ssh"], name):
        console.print(f"[green]✓ {name} accepts your key[/green]")
        console.print(f"\n[dim]Next:[/dim] co server check {name}\n")
        return True

    console.print("[dim]The key was reinstalled but the machine has not picked it "
                  "up yet. It is charged for either way — try again shortly.[/dim]\n")
    return False


def _choose(pricing: dict, machine_type: Optional[str], region: Optional[str],
            disk_gb: Optional[int]) -> Optional[tuple]:
    """Resolve the machine and region against what the backend sells, or say why not.

    Everything is checked against the pricing response, never a list kept
    here: the machines and disk sizes are whatever the backend offers today.
    """
    machine_type = machine_type or pricing["default"]
    region = region or pricing["default_region"]
    if machine_type not in pricing["machine_types"]:
        console.print(f"\n[red]Unknown machine type: {machine_type}[/red]")
        console.print("[dim]Available:[/dim]")
        for option, entry in pricing["machine_types"].items():
            price = f"${entry['usd_month']:.0f} / month  " if "usd_month" in entry else ""
            console.print(f"  [cyan]{option:<14}[/cyan] {price}[dim]{entry.get('description', '')}[/dim]")
        console.print()
        return None
    if region not in pricing["regions"]:
        console.print(f"\n[red]Unknown region: {region}[/red]")
        console.print(f"[dim]Available: {', '.join(sorted(pricing['regions']))}[/dim]\n")
        return None
    if disk_gb is not None and not _monthly(pricing):
        console.print(f"\n[red]{backend_url()} does not offer --disk yet.[/red]")
        console.print("[dim]Leave it out for the standard disk. Nothing was created or charged.[/dim]\n")
        return None
    if disk_gb is not None and disk_gb not in pricing["disk"]["sizes_gb"]:
        console.print(f"\n[red]Unsupported disk size: {disk_gb} GB[/red]")
        sizes = ", ".join(str(size) for size in pricing["disk"]["sizes_gb"])
        console.print(f"[dim]Available: {sizes} GB[/dim]\n")
        return None
    return machine_type, region


def _print_created(name: str, server: dict) -> None:
    """What was made and what it costs, in the backend's own numbers."""
    console.print(f"\n[green]✓ {name} is ready[/green]")
    console.print(f"  [cyan]{server['ssh_target']}[/cyan]")
    if server.get("hostname"):
        console.print(f"  [cyan]https://{server['hostname']}[/cyan] "
                      f"[dim]— once you deploy something to it[/dim]")
    if server.get("billing") == "monthly_in_arrears":
        console.print(f"  [dim]${server['usd_month']:.2f} / month — first charge "
                      f"{server['next_charge_at'][:10]}; "
                      f"${server['charged_usd']:.2f} charged now[/dim]")
    else:
        console.print(f"  [dim]expires {server['expires_at'][:10]} — "
                      f"${server['charged_usd']:.2f} charged[/dim]")
    console.print(f"\n[dim]Next:[/dim] co server check {name}  ·  co deploy --to {name}\n")


def handle_server_new(name: str, machine_type: Optional[str] = None,
                      region: Optional[str] = None, yes: bool = False,
                      disk_gb: Optional[int] = None) -> bool:
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
        console.print("[dim]co server ls  ·  or pick another name[/dim]\n")
        return False

    api_key = load_api_key()
    if not api_key:
        console.print("\n[red]Not authenticated.[/red]")
        console.print("[cyan]co auth[/cyan] first — creating a server spends credit.\n")
        return False

    ssh_public_line = _ensure_ssh_key(name)
    if not ssh_public_line:
        console.print("\n[red]No SSH key to install.[/red]")
        console.print("[dim]The key is derived from your recovery phrase; without it the "
                      "server would be created with no way in.[/dim]")
        console.print("[cyan]co keys --ssh[/cyan] to check.\n")
        return False

    pricing = _fetch_pricing()
    if not pricing:
        console.print(f"\n[red]Could not reach {backend_url()} for pricing.[/red]")
        console.print("[dim]Nothing was created or charged.[/dim]\n")
        return False

    chosen = _choose(pricing, machine_type, region, disk_gb)
    if not chosen:
        return False
    machine_type, region = chosen

    if not yes:
        if not _confirm(name, machine_type, region, pricing, _fetch_balance(api_key), disk_gb):
            console.print("[dim]Nothing was created or charged.[/dim]\n")
            return False

    body = {"name": name, "ssh_public_key": ssh_public_line,
            "machine_type": machine_type, "region": region}
    if disk_gb is not None:
        body["disk_gb"] = disk_gb
    if _monthly(pricing):
        # The acknowledgement the monthly backend requires: this client has
        # shown monthly-in-arrears terms. The older backend gets nothing new.
        body["billing"] = "monthly_in_arrears"
    console.print(f"\n[dim]Creating {name} … this takes about a minute.[/dim]")
    try:
        response = requests.post(
            f"{backend_url()}/api/v1/servers",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=300,
        )
    except requests.RequestException as exc:
        console.print(f"[red]Request failed: {exc}[/red]")
        console.print("[dim]If the server was created you will see it in "
                      "[bold]co server ls[/bold].[/dim]\n")
        return False

    if response.status_code != 200:
        _report_failure(response, monthly=_monthly(pricing))
        return False

    server = response.json()

    # Register it ourselves so the operator never types an IP. Under a lock,
    # with the read inside it: this is the write that follows a minute-long API
    # call, so anything another session registered meanwhile would otherwise be
    # overwritten — and the operator was charged for both.
    entry = {"ssh": server["ssh_target"], "last_check": None}
    # The hostname the backend created a DNS record for. Stored rather than
    # derived: the naming rule lives in one place (the backend), and a CLI that
    # reconstructed it would be a second copy that has to agree forever.
    if server.get("hostname"):
        entry["hostname"] = server["hostname"]
    _update(lambda servers: servers.update({name: entry}))

    _forget_host_key(server["ssh_target"])
    _wait_until_it_accepts_your_key(server["ssh_target"], name)
    _print_created(name, server)
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
        response = requests.get(f"{backend_url()}/api/v1/auth/me",
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        if response.status_code == 200:
            value = response.json().get("balance_usd")
            return float(value) if value is not None else None
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None


def _report_failure(response, monthly: bool = False) -> None:
    """Say what happened to the money, first.

    On the monthly backend `balance` in an insufficient-credits refusal is what
    is left after a month of every other live server, so it is labelled so.
    """
    try:
        detail = response.json().get("detail", {})
    except ValueError:
        detail = {}

    if isinstance(detail, str):
        console.print(f"\n[red]{detail}[/red]\n")
        return

    error = detail.get("error")
    if error == "insufficient_credits":
        have = "left after your other servers' months" if monthly else "have"
        need = "this server's month" if monthly else "need"
        width = max(len(have), len(need), len("short by"))
        console.print("\n[red]Not enough credit.[/red]")
        console.print(f"  {have:<{width}}  ${detail.get('balance', 0):.2f}")
        console.print(f"  {need:<{width}}  ${detail.get('required', 0):.2f}")
        console.print(f"  {'short by':<{width}}  [bold]${detail.get('shortfall', 0):.2f}[/bold]")
        if detail.get("message"):
            console.print(detail["message"], style="dim", markup=False)
        console.print("\n[dim]Nothing was created or charged.[/dim]")
        console.print("[dim]https://discord.gg/4xfD9k8AUF to top up.[/dim]\n")
    elif error == "unpaid_server_months":
        console.print(f"\n[red]Your servers owe ${detail.get('unpaid_usd', 0):.2f}.[/red]")
        if detail.get("message"):
            console.print(detail["message"], style="dim", markup=False)
        console.print("\n[dim]Nothing was created or charged. Top up, then try again: "
                      "https://discord.gg/4xfD9k8AUF[/dim]\n")
    elif error == "provisioning_failed":
        colour = "yellow" if detail.get("refunded") else "red"
        console.print(f"\n[{colour}]{detail.get('message', 'Provisioning failed.')}[/{colour}]\n")
    elif detail.get("message"):
        # The backend's own words, e.g. a create refused while a month is unpaid.
        console.print(f"\n{detail['message']}\n", style="red", markup=False)
    else:
        console.print(f"\n[red]Server creation failed ({response.status_code}).[/red]")
        console.print(f"[dim]{detail or response.text[:300]}[/dim]\n")


MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
INVOICE_NUMBER_PATTERN = re.compile(r"^[A-Z]+-\d{4}-\d{2}-\d+$")


def invoice_usage_error(name: Optional[str], number: Optional[str], month: Optional[str],
                        every: bool, pdf: Optional[str], as_json: bool) -> Optional[str]:
    """Why these arguments cannot go together, or None. The caller exits 2 on one."""
    if every and (name or number):
        return "--all is every server's invoices; leave out the server name and number."
    if not every and not name:
        return "Name a server, or pass --all. Example: co server invoice prod"
    if name and not SERVER_NAME_PATTERN.match(name):
        return f"'{name}' is not a server name. co server ls lists yours."
    if number and not (number.isdigit() or INVOICE_NUMBER_PATTERN.match(number)):
        return (f"'{number}' is not an invoice: give its row (#) from co server invoice {name}, "
                f"or its number, e.g. SRV-2026-12-000123.")
    if number and month:
        return "Pass an invoice number or --month, not both."
    if month and not MONTH_PATTERN.match(month):
        return f"--month takes YYYY-MM, e.g. 2026-12 (got {month})."
    if pdf and as_json:
        return "Pass --pdf or --json, not both."
    return None


def handle_server_invoice(name: Optional[str] = None, number: Optional[str] = None,
                          month: Optional[str] = None, every: bool = False,
                          pdf: Optional[str] = None, as_json: bool = False) -> bool:
    """Show the invoices the backend issued for a server's monthly charges.

    Rendered, never recomputed: every amount and line is the backend's, so the
    total printed is `total_usd` and nothing a rounding here could move.
    """
    api_key = _invoice_preflight()
    if not api_key:
        return False
    if every:
        month = month or _this_month()
        found = _get_json(api_key, "/api/v1/invoices", {"month": month})
        return found is not None and _show_invoices(found["invoices"], pdf, as_json,
                                                    f"issued in {month}")
    if number and not number.isdigit():
        found = _get_json(api_key, f"/api/v1/servers/{name}/invoices/{number}")
        return found is not None and _show_invoices([found], pdf, as_json, number)

    found = _get_json(api_key, f"/api/v1/servers/{name}/invoices")
    if found is None:
        return False
    summaries = found["invoices"]
    if number:
        return _show_row(api_key, name, summaries, int(number), pdf, as_json)
    if not month and not pdf:
        return _show_invoice_list(name, summaries, as_json)
    picked = [s for s in summaries if s["issued_at"][:7] == month] if month else summaries
    if not month and len(picked) > 1:
        return _refuse_to_guess(name, picked)
    invoices = [_get_json(api_key, f"/api/v1/servers/{name}/invoices/{s['number']}")
                for s in picked]
    if None in invoices:
        return False
    return _show_invoices(invoices, pdf, as_json,
                          f"for {name}" + (f" issued in {month}" if month else ""))


def _show_row(api_key: str, name: str, summaries: list, row: int, pdf: Optional[str],
              as_json: bool) -> bool:
    """The invoice in row `row` of the list (1 = oldest), as the list numbers them."""
    if not 1 <= row <= len(summaries):
        console.print(f"\n[red]{name} has no invoice #{row}; it has {len(summaries)}.[/red]")
        console.print(f"[dim]co server invoice {name}   to list them[/dim]\n")
        return False
    number = summaries[row - 1]["number"]
    found = _get_json(api_key, f"/api/v1/servers/{name}/invoices/{number}")
    return found is not None and _show_invoices([found], pdf, as_json, number)


def _refuse_to_guess(name: str, summaries: list) -> bool:
    """--pdf with neither a number nor a month, and more than one invoice to pick from."""
    console.print(f"\n[red]{name} has {len(summaries)} invoices; say which one.[/red]")
    for s in summaries:
        console.print(f"  co server invoice {name} {s['number']} --pdf {s['number']}.pdf",
                      markup=False)
    console.print()
    return False


def _invoice_preflight() -> Optional[str]:
    """The API key, once we know this backend issues invoices."""
    from .project_cmd_lib import load_api_key

    api_key = load_api_key()
    if not api_key:
        console.print("\n[red]Not authenticated.[/red]")
        console.print("[cyan]co auth[/cyan] first — invoices belong to your account.\n")
        return None
    if not _monthly(_fetch_pricing()):
        console.print(f"\n[yellow]{backend_url()} does not issue server invoices yet.[/yellow]")
        console.print("[dim]It bills servers 12 months up front; invoices arrive with "
                      "monthly billing.[/dim]\n")
        return None
    return api_key


def _this_month() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m")


def _get_json(api_key: str, path: str, params: Optional[dict] = None) -> Optional[dict]:
    """GET an invoice endpoint; on anything but 200, say what the backend said."""
    import requests

    response = requests.get(f"{backend_url()}{path}", params=params, timeout=30,
                            headers={"Authorization": f"Bearer {api_key}"})
    if response.status_code == 200:
        return response.json()
    console.print(f"\n[red]{path} answered {response.status_code}.[/red]")
    console.print(response.text[:300] + "\n", style="dim", markup=False)
    return None


def _show_invoice_list(name: str, summaries: list, as_json: bool) -> bool:
    """One line per invoice; the full document is one --month away."""
    import json

    if as_json:
        print(json.dumps({"invoices": summaries}, indent=2))
        return True
    if not summaries:
        console.print(f"\n[dim]No invoices for {name} yet. The first is issued when its "
                      f"first month ends, or when it is destroyed.[/dim]\n")
        return True
    table = Table(box=None, padding=(0, 2))
    for column in ("#", "NUMBER", "ISSUED", "PERIOD", "AMOUNT", "STATUS"):
        table.add_column(column, justify="right" if column in ("#", "AMOUNT") else "left")
    for row, s in enumerate(summaries, 1):
        table.add_row(str(row), s["number"], s["issued_at"][:10],
                      f"{s['period_start'][:10]} to {s['period_end'][:10]}",
                      f"${s['amount_usd']:.2f}", s["status"])
    console.print()
    console.print(table)
    latest = summaries[-1]["number"]
    console.print(f"\n[dim]Full invoice:[/dim] [bold]co server invoice {name} {len(summaries)}[/bold]  "
                  f"[dim](the row, or its number; add --pdf {latest}.pdf to save it)[/dim]\n")
    return True


def _show_invoices(invoices: list, pdf: Optional[str], as_json: bool, what: str) -> bool:
    """Full invoices: the backend's JSON, readable text, or a PDF of that text."""
    import json

    if as_json:
        print(json.dumps({"invoices": invoices}, indent=2))
        return True
    if not invoices:
        console.print(f"\n[dim]No invoices {what}.[/dim]\n")
        return True
    if pdf:
        _write_invoice_pdf(invoices, Path(pdf))
        console.print(f"\n[green]✓[/green] {len(invoices)} invoice(s) {what} → {pdf}\n")
        return True
    for invoice in invoices:
        console.print()
        for line in _invoice_text(invoice):
            console.print(line, markup=False, highlight=False)
    console.print()
    return True


def _invoice_text(invoice: dict) -> list:
    """The invoice as plain lines: the terminal prints them, the PDF lays them out."""
    issuer, bill_to, server, period = (invoice["issuer"], invoice["bill_to"],
                                       invoice["server"], invoice["period"])
    lines = [f"INVOICE {invoice['number']}   {invoice['status'].upper()}",
             f"Issued    {invoice['issued_at'][:10]}",
             f"From      {issuer['name']}" + (f", ABN {issuer['abn']}" if issuer.get("abn") else "")]
    lines += [f"          {value}" for value in (issuer.get("address"), issuer.get("email")) if value]
    lines.append(f"Bill to   {bill_to.get('name') or bill_to['agent_address']}")
    if bill_to.get("name"):
        lines.append(f"          {bill_to['agent_address']}")
    if bill_to.get("address"):
        lines.append(f"          {bill_to['address']}")
    if bill_to.get("tax_id"):
        lines.append(f"          Tax ID {bill_to['tax_id']}")
    lines.append(f"Server    {server['name']} ({server['machine_type']}, {server['disk_gb']} GB disk)")
    lines.append(f"Period    {period['start'][:10]} to {period['end'][:10]}, {period['days']} days")
    if not period["full_month"]:
        lines.append("          Part of a month: the server was destroyed before it ended")
    return lines + [""] + _invoice_line_table(invoice) + [
        "", invoice["gst_treatment"], invoice["payment"]["note"]]


def _invoice_line_table(invoice: dict) -> list:
    width = max([len("Description")] + [len(line["description"]) for line in invoice["lines"]])
    rows = [f"{'Description':<{width}}  {'Months':>7}  {'Per month':>10}  {'Amount':>10}"]
    for line in invoice["lines"]:
        rows.append(f"{line['description']:<{width}}  {line['months']:>7g}  "
                    f"{'$%.2f' % line['unit_usd_month']:>10}  {'$%.2f' % line['amount_usd']:>10}")
    total = f"${invoice['total_usd']:.2f}"
    rows.append(f"{'Total ' + invoice['currency']:>{width + 21}}  {total:>10}")
    return rows


# 9pt Courier is 5.4pt a character; 95 of them fit between 40pt margins on A4.
PDF_LINE_CHARS = 95
PDF_LINES_PER_PAGE = 64


def _write_invoice_pdf(invoices: list, path: Path) -> None:
    """A4 pages in Courier so the columns line up; an invoice starts on a new page.

    Built with pypdf, already a dependency, and the PDF base-14 font, so no
    font file and no new package. The pages carry `_invoice_text`, wrapped.
    """
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Courier"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    writer = PdfWriter()
    for invoice in invoices:
        lines = _pdf_lines(invoice)
        for top in range(0, len(lines), PDF_LINES_PER_PAGE):
            page = writer.add_blank_page(width=595, height=842)
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(_pdf_text_ops(lines[top:top + PDF_LINES_PER_PAGE]))
            page.replace_contents(stream)
    with open(path, "wb") as handle:
        writer.write(handle)


def _shows_in_pdf(text: str) -> bool:
    """Can the base-14 font's encoding (cp1252) draw every character of this?"""
    return text.encode("cp1252", "replace") == text.encode("cp1252", "ignore")


def _pdf_lines(invoice: dict) -> list:
    """The invoice's lines, wrapped to the page, with a bill-to the font cannot draw left out.

    Courier carries no Chinese, Japanese or other non-Latin glyphs. Rather than
    a row of question marks where a company name should be, the page names the
    account address and says where the full name is.
    """
    import textwrap

    bill_to = invoice["bill_to"]
    hidden = [k for k in ("name", "address") if bill_to.get(k) and not _shows_in_pdf(bill_to[k])]
    shown = {**invoice, "bill_to": {**bill_to, **{k: None for k in hidden}}}
    lines = _invoice_text(shown)
    if hidden:
        at = next(i for i, line in enumerate(lines) if line.startswith("Bill to")) + 1
        lines.insert(at, f"          (bill-to {' and '.join(hidden)} not shown: this PDF's font "
                         f"cannot draw it; co server invoice {invoice['server']['name']} "
                         f"{invoice['number']} prints it)")
    wrapped = []
    for line in lines:
        wrapped += textwrap.wrap(line, PDF_LINE_CHARS, subsequent_indent=" " * 10,
                                 drop_whitespace=False, replace_whitespace=False) or [""]
    return wrapped


def _pdf_text_ops(lines: list) -> bytes:
    """PDF text operators for these lines, top of the page down, 9pt Courier."""
    def literal(text: str) -> bytes:
        raw = text.encode("cp1252", "replace")
        return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    ops = [b"BT /F1 9 Tf 40 800 Td 12 TL"]
    ops += [literal(line) + b" Tj T*" for line in lines]
    return b"\n".join(ops + [b"ET"])
