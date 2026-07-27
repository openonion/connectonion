"""
Purpose: One-shot global setup of ~/.co/ — identity, agent.json, and skill library.

LLM-Note:
  Dependencies: imports from [json, os, subprocess, tempfile, pathlib, rich] | imported by [cli/main.py via handle_setup()]
  Data flow:
    1. Identity: ensure ~/.co/keys/agent.key (bootstrap via `co init` in tmpdir if missing)
    2. agent.json: write ~/.co/agent.json with {address, alias, name, bio, skills, version}
    3. Skills: handle_skills_discover → handle_skills_copy(all_=True) → handle_skills_manifest
  State/Effects: creates ~/.co/agent.json | reads ~/.co/keys for signing address | invokes skills commands which write index.json, ~/.co/skills/<name>/, and agent.json skills metadata
  Integration: replaces oo-init's manual phases | ~/.co/agent.json is the publishable profile (read by oo-publish at sign time)
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

CO_HOME = Path.home() / ".co"
KEYS_FILE = CO_HOME / "keys" / "agent.key"
AGENT_JSON = CO_HOME / "agent.json"
KEYS_ENV = CO_HOME / "keys.env"


def _ensure_identity() -> dict:
    """Make sure ~/.co/keys/agent.key exists; bootstrap via `co init` in a tmpdir if not."""
    if not KEYS_FILE.exists():
        console.print("[yellow]No identity found; bootstrapping via `co init` in tmpdir...[/yellow]")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["co", "init", "--yes"], cwd=td, check=True)
        if not KEYS_FILE.exists():
            console.print(f"[red]FAIL: `co init` did not create {KEYS_FILE}[/red]")
            raise SystemExit(1)

    from connectonion import address
    return address.load(CO_HOME)


def _write_agent_json(name: str, bio: str, addr: str):
    profile = {
        "address": addr,
        "alias":   name,
        "name":    name,
        "bio":     bio,
        "skills":  [],
        "version": "v0.1.0",
    }
    AGENT_JSON.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def handle_setup(
    name: Optional[str] = None,
    bio: Optional[str] = None,
    force: bool = False,
    skip_skills: bool = False,
):
    """Set up ~/.co/: identity, agent.json, skill library. Idempotent."""

    # Phase 1: identity
    keys = _ensure_identity()
    addr = keys["address"]
    console.print(f"[green]✓ Identity:[/green] {addr}")

    # Phase 2: agent.json
    if AGENT_JSON.exists() and not force:
        existing = json.loads(AGENT_JSON.read_text(encoding="utf-8"))
        console.print(f"[dim]✓ {AGENT_JSON} exists (alias={existing.get('alias')}, skip — pass --force to overwrite)[/dim]")
    else:
        if AGENT_JSON.exists() and force:
            backup = AGENT_JSON.with_suffix(".json.bak")
            AGENT_JSON.rename(backup)
            console.print(f"[yellow]Backed up existing agent.json → {backup}[/yellow]")
        alias = name or os.environ.get("USER", "agent").lower().replace(" ", "-")
        body = bio or f"Agent for {alias}. Edit ~/.co/agent.json to customize."
        _write_agent_json(alias, body, addr)
        console.print(f"[green]✓ Wrote[/green] {AGENT_JSON} (alias={alias})")
        if body.endswith("Edit ~/.co/agent.json to customize."):
            console.print(f"  [yellow]Bio is a placeholder — edit before publishing.[/yellow]")

    # Phase 3: skill library
    if not skip_skills:
        console.print("\n[cyan]Refreshing ~/.co/skills/ library...[/cyan]")
        from .skills_commands import handle_skills_discover, handle_skills_copy, handle_skills_manifest
        handle_skills_discover(save=True, json_out=False)
        handle_skills_copy(names=[], all_=True, force=False)
        handle_skills_manifest()

    # Auth check
    auth_ok = KEYS_ENV.exists() and "OPENONION_API_KEY=" in KEYS_ENV.read_text(encoding="utf-8")
    console.print()
    if auth_ok:
        console.print("[green]✓ Auth:[/green] OPENONION_API_KEY present")
    else:
        console.print("[yellow]⚠ Auth:[/yellow] run `co auth` to enable co/* managed models")

    console.print("\n[bold]Setup complete.[/bold] Run the oo-publish skill to sign + announce.")
