"""
Purpose: Register, list and preflight the machines `co deploy --to` can target
LLM-Note:
  Dependencies: imports from [subprocess, shutil, pathlib, yaml, rich] | imported by [cli/main.py via handle_server_*] | tested by [tests/unit/test_server_commands.py]
  Data flow: handle_server_add(name, ssh_target) → _load()/_save() ~/.co/servers.yaml → handle_server_list() renders the table | handle_server_check(name) → _ssh(target, probe script) → parses one KEY=value line per requirement → prints every failure by name, and caches the first as `needs <requirement>` (the bare name read as a fact about the server in the LAST CHECK column)
  State/Effects: reads and writes ~/.co/servers.yaml (name → ssh target, last check result) | shells out to the system ssh binary | never stores a credential
  Integration: exposes handle_server_add(), handle_server_list(), handle_server_check(), load_server() for deploy | requirement list is Ubuntu 24.04, python 3.11+, systemd the user may manage, free disk
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
        console.print(f"[dim]Tip: your derived key is [bold]co keys --ssh[/bold] — it has to be in "
                      f"authorized_keys on that host.[/dim]\n")
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
            row.append(f"[dim]until {record['expires_at'][:10]}[/dim]" if record
                       else "[dim]not ours[/dim]")
        table.add_row(*row)

    # The expensive row: charged for, absent locally.
    unregistered = [s for s in (billed or []) if s["name"] not in servers]
    for record in unregistered:
        table.add_row(
            f"[yellow]{record['name']}[/yellow]",
            f"[dim]{record.get('ssh_target') or '—'}[/dim]",
            "[yellow]not registered here[/yellow]",
            f"[yellow]until {record['expires_at'][:10]}[/yellow]",
        )

    console.print()
    console.print(table)

    if unregistered:
        names = ", ".join(s["name"] for s in unregistered)
        console.print(f"\n[yellow]{len(unregistered)} server(s) you are billed for are not "
                      f"registered on this machine:[/yellow] {names}")
        console.print("[dim]co server add <name> --ssh <target>   to use one from here[/dim]")
        console.print("[dim]co server destroy <name>              to stop paying for one[/dim]")

    console.print(f"\n[dim]{_short(SERVERS_FILE)}[/dim]\n")
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
        response = requests.get(f"{API_BASE}/api/v1/servers",
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None
    try:
        return response.json().get("servers", [])
    except ValueError:
        return None


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

    if not yes:
        console.print(f"\n[red]This destroys the machine '{name}' and everything on it.[/red]")
        console.print("[dim]The disk, the agent's identity, its logs — none of it is "
                      "recoverable.[/dim]")
        console.print("[dim]The unused part of the term is refunded to your credit.[/dim]")
        console.print()

        import questionary
        typed = questionary.text(f"Type the server name to confirm ({name}):").ask()
        if typed != name:
            console.print("[dim]Nothing was destroyed.[/dim]\n")
            return False

    console.print(f"\n[dim]Destroying {name} …[/dim]")
    try:
        response = requests.delete(
            f"{API_BASE}/api/v1/servers/{name}",
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

    # State the amount, not the policy. "Prorated" tells the user nothing they
    # can check; a number against what they paid does.
    result = response.json() if response.content else {}
    refunded = result.get("refunded_usd")
    if refunded:
        charged = result.get("charged_usd")
        against = f" of ${charged:.2f}" if charged else ""
        console.print(f"[dim]${refunded:.2f}{against} refunded to your credit — "
                      f"the unused part of the term.[/dim]\n")
    else:
        console.print("[dim]Nothing refunded — the term had already run out.[/dim]\n")
    return True


API_BASE = "https://oo.openonion.ai"

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

    # Nothing can be answered on a stdin that is not a terminal, and the prompt
    # library does not decline politely — it registers the descriptor with
    # asyncio and raises OSError: [Errno 22]. On the one command that spends
    # money, a bare traceback also leaves the reader unable to tell whether the
    # charge went through.
    if not sys.stdin.isatty():
        console.print(
            f"[red]Cannot confirm: stdin is not a terminal.[/red]\n"
            f"  ${price:.2f} would be charged now. "
            f"Re-run with [bold]--yes[/bold] to confirm without being asked."
        )
        return False

    import questionary
    return bool(questionary.confirm("Create it?", default=False).ask())


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
            f"{API_BASE}/api/v1/servers/{name}/key",
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

    ssh_public_line = _ensure_ssh_key(name)
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

    console.print(f"\n[green]✓ {name} is ready[/green]")
    console.print(f"  [cyan]{server['ssh_target']}[/cyan]")
    if server.get("hostname"):
        console.print(f"  [cyan]https://{server['hostname']}[/cyan] "
                      f"[dim]— once you deploy something to it[/dim]")
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
