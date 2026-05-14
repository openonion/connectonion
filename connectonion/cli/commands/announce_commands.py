"""
Purpose: `co announce` — sign & send a publishable ANNOUNCE (profile + inlined SKILL.md bodies) to the relay.

LLM-Note:
  Dependencies: imports from [asyncio, json, pathlib, websockets, rich, connectonion.address, connectonion.network.announce] | imported by [cli/main.py via handle_announce()]
  Data flow:
    1. Read ~/.co/agent.json → load alias, bio, version, skills[]
    2. Filter skills where publish: true → inline body from ~/.co/skills/<name>/SKILL.md
    3. Build profile {alias, bio, version, skills:[{name, description, body}]}
    4. create_announce_message(..., profile=profile) — signs everything
    5. WS connect wss://oo.openonion.ai/ws/announce → send → close
  State/Effects: reads ~/.co/agent.json + ~/.co/skills/<name>/SKILL.md | opens one outbound WS | no local writes
  Integration: publish: true is the only privacy knob — false/missing skills never leave the machine.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from ... import address
from ...network.announce import create_announce_message

console = Console()

CO_HOME = Path.home() / ".co"
AGENT_JSON = CO_HOME / "agent.json"
SKILLS_DIR = CO_HOME / "skills"
DEFAULT_RELAY = "wss://oo.openonion.ai"


def _load_profile() -> dict:
    if not AGENT_JSON.exists():
        console.print(f"[red]No {AGENT_JSON}. Run `co setup` first.[/red]")
        raise SystemExit(1)
    return json.loads(AGENT_JSON.read_text())


def _build_published_skills(profile: dict) -> list:
    skills_out = []
    for skill in profile.get("skills", []):
        if not skill.get("publish"):
            continue
        name = skill["name"]
        body_path = SKILLS_DIR / name / "SKILL.md"
        if not body_path.exists():
            console.print(f"[yellow]Skipping {name}: {body_path} not found[/yellow]")
            continue
        skills_out.append({
            "name": name,
            "description": skill.get("description", ""),
            "body": body_path.read_text(encoding="utf-8"),
        })
    return skills_out


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

    skills = _build_published_skills(profile_file)
    profile = {
        "alias":   profile_file.get("alias"),
        "bio":     profile_file.get("bio", ""),
        "version": profile_file.get("version", "v0.1.0"),
        "skills":  skills,
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
    console.print(f"  skills: {len(skills)} published" + (
        f" ({', '.join(s['name'] for s in skills)})" if skills else ""
    ))

    if dry_run:
        console.print_json(data=message)
        return

    asyncio.run(_send(message, relay_url))
    console.print("[green]✓ Announced.[/green]")
