"""
Purpose: Shared local onboarding and explicit profile/skill-library setup.

LLM-Note:
  Dependencies: imports from [json, os, pathlib, rich, environment, project_cmd_lib] | imported by [cli/main.py, init.py, create.py]
  Data flow:
    1. Identity: ensure_global_config() creates or repairs the global identity and keys.env in process
    2. agent.json: write ~/.co/agent.json with {address, alias, name, bio, skills, version}
    3. Local integration: complete_local_setup() creates a missing profile, links bundled skills, refreshes the command index
    4. Explicit setup only: handle_skills_discover → handle_skills_copy(all_=True) → handle_skills_manifest
  State/Effects: creates ~/.co/agent.json | reads ~/.co/keys for signing address | invokes skills commands which write index.json, ~/.co/skills/<name>/, and agent.json skills metadata
  Integration: replaces oo-init's manual phases | ~/.co/agent.json is the publishable profile (read by oo-publish at sign time)
"""

import json
import os
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console(highlight=False)

from ...environment import explicit_env_file, global_config_dir, read_env_file, selected_env_file, setting


def _ensure_identity() -> dict:
    """Reuse the machine identity and repair keys.env even when its key exists."""
    from .project_cmd_lib import ensure_global_config
    from connectonion import address

    ensure_global_config()
    return address.load(global_config_dir())


def _write_agent_json(path: Path, name: str, bio: str, addr: str):
    profile = {
        "address": addr,
        "alias":   name,
        "name":    name,
        "bio":     bio,
        "skills":  [],
        "version": "v0.1.0",
    }
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def _edit_profile(path: Path, name: Optional[str], bio: Optional[str]) -> None:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if name is not None:
        profile.update(alias=name, name=name)
    if bio is not None:
        profile["bio"] = bio
    profile.pop("signature", None)
    profile.pop("signer", None)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    console.print(f"[green]✓ Local profile: {path} (updated)[/green]")


def _repair_profile(path: Path) -> None:
    """Fill missing local fields; never discard malformed personal metadata."""
    from connectonion import address

    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ValueError(f"{path} must contain a JSON object")
    skills = profile.get("skills", [])
    if not isinstance(skills, list) or any(
            not isinstance(skill, dict) or not isinstance(skill.get("name"), str)
            or not skill["name"].strip() for skill in skills):
        raise ValueError(f"{path}: skills must be a list of objects with a nonempty name; "
                         "repair the file or run co setup --force to back it up and recreate it")
    for field in ("address", "alias", "name", "bio", "version"):
        if field in profile and not isinstance(profile[field], str):
            raise ValueError(f"{path}: {field} must be text; repair the file before running setup again")
    alias = profile.get("alias") or profile.get("name") or os.environ.get("USER", "agent")
    defaults = {"address": address.load(global_config_dir())["address"], "alias": alias,
                "name": alias, "bio": f"Agent for {alias}.", "skills": [], "version": "v0.1.0"}
    missing = defaults.keys() - profile.keys()
    if missing:
        profile.update({key: defaults[key] for key in missing})
        profile.pop("signature", None)
        profile.pop("signer", None)
        path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def _ensure_profile(name: Optional[str], bio: Optional[str], force: bool) -> None:
    from connectonion import address

    path = global_config_dir() / "agent.json"
    if path.exists() and not force:
        _repair_profile(path)
        if name is not None or bio is not None:
            _edit_profile(path, name, bio)
        else:
            console.print(f"[dim]✓ Local profile: {path} (kept)[/dim]")
        return
    if path.exists():
        backup = path.with_suffix(".json.bak")
        path.replace(backup)
        console.print(f"[yellow]Backed up existing agent.json → {backup}[/yellow]")
    alias = name or os.environ.get("USER", "agent").lower().replace(" ", "-")
    body = bio or f"Agent for {alias}. Edit {path} to customize."
    _write_agent_json(path, alias, body, address.load(global_config_dir())["address"])
    console.print(f"[green]✓ Local profile: {path} (created)[/green]")


def complete_local_setup(name: Optional[str] = None, bio: Optional[str] = None,
                         force: bool = False) -> None:
    """Finish local integration after ensure_global_config(); preserve user files.

    Profile --force is deliberately separate from skills link --force.
    """
    from .agent_index import handle_skills_index
    from .skills_commands import handle_skills_link

    _ensure_profile(name, bio, force)
    handle_skills_link(brief=True)
    handle_skills_index(brief=True)


def handle_setup(
    name: Optional[str] = None,
    bio: Optional[str] = None,
    force: bool = False,
    skip_skills: bool = False,
):
    """Set up ~/.co/: identity, agent.json, skill library. Idempotent."""

    if explicit_env_file() is not None:
        console.print("Global setup does not accept --env-file. Next: co setup")
        raise SystemExit(2)

    # A fresh setup retains the managed-key attempt without invoking another co.
    root = global_config_dir()
    new_identity = not (root / "keys" / "agent.key").exists()
    keys = _ensure_identity()
    addr = keys["address"]
    console.print(f"[green]✓ Identity:[/green] {addr}")
    if new_identity:
        from .auth_commands import authenticate
        authenticate(root, save_to_project=False)

    complete_local_setup(name, bio, force)

    # Phase 3: skill library
    if not skip_skills:
        console.print(f"\n[cyan]Refreshing {root / 'skills'} library...[/cyan]")
        from .skills_commands import handle_skills_copy, handle_skills_discover, handle_skills_manifest
        handle_skills_discover(save=True, json_out=False)
        handle_skills_copy(names=[], all_=True, force=False)
        handle_skills_manifest()

    # Auth check
    auth_ok = bool(setting("OPENONION_API_KEY") or
                   read_env_file(selected_env_file()).get("OPENONION_API_KEY"))
    console.print()
    if auth_ok:
        console.print("[green]✓ Auth:[/green] OPENONION_API_KEY present (not verified)")
    else:
        console.print("[yellow]⚠ Auth:[/yellow] run `co auth` to enable co/* managed models")

    console.print("\n[bold]Local setup complete.[/bold] Review the profile before publishing.")
