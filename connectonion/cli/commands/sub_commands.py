"""
Purpose: `co sub` — record a subscription relationship to a published agent, mirror their public skills locally, and fan out to every coding agent on this machine.
LLM-Note:
  Dependencies: imports from [json, re, shutil, pathlib, httpx, rich.console, rich.table, .fanout] | imported by [cli/main.py via handle_sub_sync_one/sync_all/list/remove] | tested by [tests/unit/test_sub_commands.py, tests/cli/test_cli_sub.py]
  Data flow:
    sync_one(target, relay?) → _resolve_target() validates 0x address or matches an alias already in subscriptions.txt → _fetch_profile() GET /api/agents/<addr>/profile → _mirror_bundle() writes ~/.co/subs/<alias>/agent.json + for each skill GET /api/agents/<addr>/skills/<name> → unwrap body (handles both JSON {body:...} and raw text/markdown content-types) → write SKILL.md → append `<address> <alias>` to ~/.co/subscriptions.txt (deduped) → fanout.install_all() symlinks/copies into ~/.claude, ~/.codex, ~/.openclaw, ~/.cursor, ~/.kiro
    sync_all(relay?) → walks ~/.co/subscriptions.txt, calls sync_one per entry, tolerates per-publisher failures, prints summary (ok/failed counts)
    list() → reads ~/.co/subscriptions.txt + ~/.co/subs/<alias>/agent.json → Rich table with alias, full address, version, skill count
    remove(target) → match by address or alias → fanout.uninstall_all() drops every per-tool install → rmtree ~/.co/subs/<alias>/ → rewrite subscriptions.txt without the line
  State/Effects: writes ~/.co/subscriptions.txt | writes ~/.co/subs/<alias>/agent.json + skills/<name>/SKILL.md | symlinks/files under ~/.<tool>/ via fanout | one synchronous httpx.get per profile + per skill body (no auth, no cache)
  Integration: exposes handle_sub_sync_one(target, relay=None), handle_sub_sync_all(relay=None), handle_sub_list(), handle_sub_remove(target) called from cli/main.py's `sub` typer group | module-level CO_HOME, SUBS_DIR, SUBS_LIST are monkeypatched by tests | httpx.get is the seam tests stub
  Performance: 1 + N HTTP GETs per subscribe (1 profile + 1 per skill body) | linear file I/O for mirror | idempotent (re-subscribe overwrites bundle, dedupes the line)
  Errors: SystemExit(1) when target isn't a 0x address and isn't a locally-pinned alias (aliases are mutable; first-time subscriptions require an address) | raise_for_status() bubbles network errors | missing skill body raises (relay should never return 404 for a name listed in profile)

Subscription persistence:
  ~/.co/subscriptions.txt — flat list, one `<address> <alias>` per line, `#` comments allowed.
  Matches ~/.co/contacts.txt / whitelist.txt / blocklist.txt shape.

Relay endpoints consumed (v1):
  GET /api/agents/{address}/profile       - {profile: {alias, bio, version, skills:[{name, description}, ...]}}
  GET /api/agents/{address}/skills/{name} - JSON {body: "..."} or raw markdown depending on Content-Type

⚠️ v1 trusts the relay — no Ed25519 signature verification (relay strips signer/signature from profile responses).
⚠️ No alias→address resolver on relay — aliases are dangerous (mutable), so first-time subs require 0x address.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.table import Table

from .fanout import install_all, uninstall_all
from ...backend import backend_url

console = Console()

CO_HOME = Path.home() / ".co"
SUBS_DIR = CO_HOME / "subs"
SUBS_LIST = CO_HOME / "subscriptions.txt"
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _relay_base(relay: Optional[str]) -> str:
    return (relay or backend_url()).rstrip("/")


def _read_subs() -> list[tuple[str, str]]:
    """Return [(address, alias), ...] from ~/.co/subscriptions.txt."""
    if not SUBS_LIST.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in SUBS_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            out.append((parts[0], parts[1]))
    return out


def _write_subs(subs: list[tuple[str, str]]) -> None:
    SUBS_LIST.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# ~/.co/subscriptions.txt — agents you follow\n"
        "# Format: <address> <alias>\n"
        "# Managed by `co sub`. Re-run `co sub sync <address>` to refresh one.\n"
    )
    body = "\n".join(f"{addr} {alias}" for addr, alias in subs)
    SUBS_LIST.write_text(header + body + ("\n" if body else ""), encoding="utf-8")


def _fetch_profile(address: str, relay: str) -> dict:
    r = httpx.get(f"{relay}/api/agents/{address}/profile", timeout=30)
    r.raise_for_status()
    data = r.json()
    # Relay wraps in {"profile": {...}} for this endpoint
    return data.get("profile", data)


def _fetch_skill(address: str, name: str, relay: str):
    """A skill's body, or None when the publisher kept it back.

    The relay answers a withheld body with 200 and an error inside it:

        GET /api/agents/0xcf1619…/skills/candidate-mapping
        HTTP 200  {"error": "skill body not published"}

    so raise_for_status() passes and indexing ["body"] raised KeyError — a
    traceback out of `co sub sync` for anyone subscribing to an agent that
    announces a skill without publishing its contents. That is the default
    (`publish: false`), so it was the common case, and the subscriber had done
    nothing wrong.

    A real transport or server failure still raises; only a 200 that carries no
    body is treated as "nothing to mirror".
    """
    r = httpx.get(f"{relay}/api/agents/{address}/skills/{name}", timeout=30)
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict) and "body" in payload:
        return payload["body"]
    return None


def _declared_tools(body: str) -> str:
    """What a skill's frontmatter asked to auto-approve, for the operator's eyes.

    Printed at sync time rather than written into the skill: the body is a
    prompt an agent reads, and this list is a decision the operator makes.
    """
    import yaml

    if not body.startswith("---"):
        return ""
    parts = body.split("---", 2)
    if len(parts) < 3:
        return ""
    try:
        front = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return ""
    if not isinstance(front, dict):
        return ""
    return str(front.get("tools", ""))


def strip_tool_grants(body: str, name: str) -> str:
    """Remove a subscribed skill's `tools:` grant, keeping its instructions.

    A SKILL.md is not only instructions. Its frontmatter carries a `tools:`
    list, and invoking the skill auto-approves those patterns for the turn --
    measured on a real agent: ['Bash(git status)', 'read_file']. So a skill
    fetched from the relay arrives asking for auto-approval, from a source
    nobody verified: this module's own header says v1 trusts the relay, which
    strips the signer and signature. It is then written verbatim and fanned out
    into ~/.claude, ~/.codex, ~/.openclaw, ~/.cursor and ~/.kiro (#654).

    The instructions are what you subscribed to. The grant is not, and the
    operator can add the patterns to their own .co/host.yaml, where the
    decision is theirs and visible.

    A skill with no frontmatter is a legitimate simple skill -- the whole file
    is the prompt (#629) -- and one whose frontmatter does not parse is not
    ours to rewrite. Both pass through untouched.

    Verifying the publisher's signature is the real answer (#654 option 3) and
    needs the relay to stop stripping it.
    """
    import yaml

    if not body.startswith("---"):
        return body
    parts = body.split("---", 2)
    if len(parts) < 3:
        return body

    try:
        front = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        # Rewriting what we cannot read is worse than passing it through; the
        # skill loader reports an unreadable one.
        return body
    if not isinstance(front, dict) or "tools" not in front:
        return body

    front.pop("tools")
    rendered = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).rstrip()
    # The note says what happened; it does not repeat the patterns. This body
    # becomes the prompt an agent reads, and the operator is the one who needs
    # the list -- so it goes to the terminal at sync time instead, where the
    # decision to add them is being made.
    note = ("\n> `tools:` removed on sync — a subscribed skill does not "
            "pre-authorise anything. Add what you want to your own "
            ".co/host.yaml.\n")
    return f"---\n{rendered}\n---\n{note}{parts[2]}"


def _mirror_bundle(address: str, alias: str, profile: dict, relay: str) -> int:
    """Write profile + each skill body under ~/.co/subs/<alias>/. Returns skill count."""
    bundle = SUBS_DIR / alias
    skills_root = bundle / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    (bundle / "agent.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")

    n = 0
    for skill in profile.get("skills", []):
        name = skill["name"]
        body = _fetch_skill(address, name, relay)
        if body is None:
            # Announced but not published. Named, because the profile promised a
            # skill the subscriber will not find, and skipped rather than written
            # — an error document saved as SKILL.md would reach an agent as
            # instructions.
            console.print(f"[dim]{name}: skipped — the publisher did not "
                          f"publish its body[/dim]")
            continue
        (skills_root / name).mkdir(parents=True, exist_ok=True)
        cleaned = strip_tool_grants(body, name)
        if cleaned != body:
            console.print(f"[yellow]{name}: removed its tools: grant[/yellow] "
                          f"[dim]{_declared_tools(body)}[/dim]")
        (skills_root / name / "SKILL.md").write_text(cleaned, encoding="utf-8")
        n += 1
    return n


def _resolve_target(target: str) -> tuple[str, Optional[str]]:
    """Return (address, alias_hint). v1 only accepts 0x addresses; aliases need
    a relay-side resolver that doesn't exist yet."""
    if ADDRESS_RE.match(target):
        return target, None
    # Maybe they typed an alias that's already in subscriptions.txt (refresh case)
    for addr, alias in _read_subs():
        if alias == target:
            return addr, alias
    console.print(
        f"[red]'{target}' is not a 0x address and I don't have it in subscriptions.txt.[/red]\n"
        "Alias resolution on the relay isn't available yet — paste the full 0x address."
    )
    raise SystemExit(1)


def handle_sub_sync_all(relay: Optional[str] = None) -> None:
    """Walk ~/.co/subscriptions.txt and sync each entry. Fails fast on first error."""
    subs = _read_subs()
    if not subs:
        console.print("\n[dim]No subscriptions yet. Try `co sub sync 0x...`[/dim]\n")
        return
    for address, _alias in subs:
        handle_sub_sync_one(address, relay=relay)


def handle_sub_sync_one(target: str, relay: Optional[str] = None) -> None:
    """Sync one publisher: resolve, fetch profile, record, mirror bodies, fan out."""
    address, alias_hint = _resolve_target(target)
    base = _relay_base(relay)

    console.print(f"[cyan]Fetching profile[/cyan] {address}")
    profile = _fetch_profile(address, base)
    alias = profile.get("alias") or alias_hint or address[:10]

    n_skills = _mirror_bundle(address, alias, profile, base)

    subs = [(a, al) for a, al in _read_subs() if a != address]
    subs.append((address, alias))
    _write_subs(subs)

    results = install_all(SUBS_DIR / alias, alias)
    console.print(f"[green]✓ Subscribed to {alias}[/green] ({address})")
    console.print(f"  mirrored {n_skills} skill(s) → {SUBS_DIR / alias}")

    # Report the roll-call and the restart only when something was actually
    # installed. Against a live publisher whose only skill was withheld, this
    # printed a green tick, four lines of "installed 0 skill(s)", and "Restart
    # your coding agent to load the new skills" — sending the reader off to
    # restart four tools for nothing. The subscription is still worth reporting:
    # it is recorded, so a later sync picks up bodies if they are ever published.
    installed = {tool: n for tool, n in (results or {}).items() if n}
    if installed:
        for tool, n in installed.items():
            console.print(f"  {tool}: installed {n} skill(s)")
        console.print("\n[yellow]→ Restart your coding agent to load the new skills.[/yellow]")
    elif not results:
        console.print("  [dim]No coding agents detected — bodies mirrored but not installed.[/dim]")
    else:
        console.print("  [dim]No skills to install — nothing to restart for. "
                      "A later `co sub sync` picks up bodies the publisher adds.[/dim]")


def handle_sub_list() -> None:
    """Show ~/.co/subscriptions.txt with local version info."""
    subs = _read_subs()
    if not subs:
        console.print(f"\n[dim]No subscriptions. Subscribe with `co sub 0x...`[/dim]\n")
        return

    table = Table(title="Subscriptions", show_lines=False, header_style="bold")
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("Address", overflow="fold")
    table.add_column("Version", style="green", no_wrap=True)
    table.add_column("Skills", justify="right", no_wrap=True)

    for address, alias in subs:
        profile_path = SUBS_DIR / alias / "agent.json"
        version = "—"
        skill_count = "—"
        if profile_path.exists():
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            version = data.get("version", "—")
            skill_count = str(len(data.get("skills", [])))
        table.add_row(alias, address, version, skill_count)

    console.print()
    console.print(table)
    console.print(f"\n[dim]Stored in: {SUBS_LIST}[/dim]\n")


def handle_sub_remove(target: str) -> None:
    """Unsubscribe: drop the line, uninstall fan-out, remove the mirror."""
    subs = _read_subs()
    match = next(((a, al) for a, al in subs if a == target or al == target), None)
    if match is None:
        console.print(f"[yellow]Not subscribed to '{target}'.[/yellow]")
        return
    address, alias = match

    uninstall_all(alias)
    bundle = SUBS_DIR / alias
    if bundle.exists():
        shutil.rmtree(bundle)

    _write_subs([(a, al) for a, al in subs if a != address])
    console.print(f"[green]✓ Unsubscribed from {alias}[/green] ({address})")
