"""
Purpose: `co announce` — sign & send a publishable ANNOUNCE (profile + inlined SKILL.md bodies) to the relay.

LLM-Note:
  Dependencies: imports from [asyncio, json, pathlib, websockets, rich, connectonion.address, connectonion.network.announce] | imported by [cli/main.py via handle_announce()]
  Data flow:
    1. Read ~/.co/agent.json → load alias, bio, version, skills[]
    2. List all skills as metadata; inline body only when publish: true
    3. Allocate a monotonic signed profile revision under ~/.co/profile-publish-state/
    4. Build profile {alias, bio, version, attestation_version, revision, skills:[{name, description, body?}]}
    5. create_announce_message(..., profile=profile) — signs everything
    6. WS connect wss://oo.openonion.ai/ws/announce → send → persist accepted revision
  State/Effects: reads ~/.co/agent.json + ~/.co/skills/<name>/SKILL.md | writes the accepted publisher revision atomically | opens one outbound WS
  Integration: skills are listed by default; publish: true controls whether the body is public.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from ... import address
from ...network.announce import create_announce_message
from ...network.profile_freshness import next_revision, revision_lock, write_state

console = Console()

CO_HOME = Path.home() / ".co"
AGENT_JSON = CO_HOME / "agent.json"
SKILLS_DIR = CO_HOME / "skills"
DEFAULT_RELAY = "wss://oo.openonion.ai"


def _revision_path(publisher: str) -> Path:
    return CO_HOME / "profile-publish-state" / f"{publisher}.json"


def _load_profile() -> dict:
    if not AGENT_JSON.exists():
        console.print(f"[red]No {AGENT_JSON}. Run `co setup` first.[/red]")
        raise SystemExit(1)
    return json.loads(AGENT_JSON.read_text(encoding="utf-8"))


def _build_listed_skills(profile: dict) -> list:
    skills_out = []
    for skill in profile.get("skills", []):
        name = skill["name"]
        listed = {
            "name": name,
            "description": skill.get("description", ""),
        }
        if skill.get("publish"):
            body_path = SKILLS_DIR / name / "SKILL.md"
            if body_path.exists():
                listed["body"] = body_path.read_text(encoding="utf-8")
            else:
                console.print(f"[yellow]Listing {name} without body: {body_path} not found[/yellow]")
        skills_out.append(listed)
    return skills_out


def print_announce_summary(alias: str, skills: list) -> None:
    """How many skills were listed, how many carry a body, and which ones do.

    The names used to be all of them, printed straight after "N with public
    body". On this machine that read:

        Listing linkedin-thumbup without body: … not found
        ...
        skills: 39 listed, 19 with public body (co-install, …,
        linkedin-comment-draft, linkedin-comment-generate, linkedin-thumbup, …

    — the three the same command had just reported as missing, inside the list a
    reader takes to be the nineteen. The count was right; the names beside it
    were everything.

    A listed skill without a body is legitimate: it advertises something you have
    not published. So the total still says how many, and only the published ones
    are named.
    """
    published = [s["name"] for s in skills if "body" in s]
    console.print(f"  skills: {len(skills)} listed, {len(published)} with public body" + (
        f" ({', '.join(published)})" if published else ""
    ))


def _announce_ws_url(relay_url: str) -> str:
    """Return the concrete /ws/announce URL for a base or endpoint relay URL."""
    url = relay_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1).rstrip("/")
    if url.endswith("/ws/announce"):
        return url
    return url + "/ws/announce"


async def _send(message: dict, relay_url: str) -> None:
    import websockets
    ws_url = _announce_ws_url(relay_url)
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps(message))
        try:
            reply = await asyncio.wait_for(ws.recv(), timeout=3.0)
        except asyncio.TimeoutError:
            console.print("[red]Relay did not acknowledge announce.[/red]")
            raise SystemExit(1)

        parsed = json.loads(reply)
        if parsed.get("type") == "ERROR":
            console.print(f"[red]Relay rejected announce: {parsed.get('error')}[/red]")
            raise SystemExit(1)
        if parsed.get("type") != "ANNOUNCE_OK":
            console.print(f"[red]Unexpected relay response: {parsed.get('type')}[/red]")
            raise SystemExit(1)


def handle_announce(relay: Optional[str] = None, dry_run: bool = False):
    """Publish ~/.co/agent.json + selected SKILL.md bodies to the relay."""
    profile_file = _load_profile()
    addr_data = address.load(CO_HOME)

    state_path = _revision_path(addr_data["address"])
    with revision_lock(state_path):
        revision = next_revision(state_path)
        skills = _build_listed_skills(profile_file)
        profile = {
            "alias": profile_file.get("alias"),
            "bio": profile_file.get("bio", ""),
            "version": profile_file.get("version", "v0.1.0"),
            "attestation_version": "profile-v2",
            "revision": revision,
            "skills": skills,
        }
        summary = profile_file.get("bio") or f"Agent {profile['alias']}"

        relay_url = relay or DEFAULT_RELAY
        message = create_announce_message(
            address_data=addr_data,
            summary=summary[:1000],
            endpoints=[],
            relay=relay_url,
            profile=profile,
        )

        console.print(f"[cyan]Announcing[/cyan] {addr_data['address']} → {relay_url}")
        console.print(f"  alias:  {profile['alias']}")
        console.print(f"  revision: {revision}")
        print_announce_summary(profile['alias'], skills)

        if dry_run:
            console.print_json(data=message)
            return

        asyncio.run(_send(message, relay_url))
        write_state(state_path, revision)
    console.print("[green]✓ Announced.[/green]")
