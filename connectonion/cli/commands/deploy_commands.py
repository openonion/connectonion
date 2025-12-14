"""
Purpose: Deploy agent projects to ConnectOnion Cloud with git archive packaging and secrets management
LLM-Note:
  Dependencies: imports from [os, subprocess, tempfile, time, toml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → validates git repo and .co/config.toml → _get_api_key() loads OPENONION_API_KEY → reads config.toml for project name and secrets path → dotenv_values() loads secrets from .env → git archive creates tarball of HEAD → POST to /api/v1/deploy with tarball + project_name + secrets → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | reads .co/config.toml, .env files | makes network POST request | prints progress to stdout via rich.Console | does not modify project files
  Integration: exposes handle_deploy() for CLI | expects git repo with .co/config.toml containing project.name, project.secrets, deploy.entrypoint | uses Bearer token auth | returns void (prints results)
  Performance: git archive is fast | network timeout 60s for upload, 10s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not git repo | fails if not ConnectOnion project (.co/config.toml missing) | fails if no API key | prints backend error messages
"""

import os
import subprocess
import tempfile
import time
import toml
import requests
from pathlib import Path
from rich.console import Console
from dotenv import dotenv_values, load_dotenv

console = Console()

API_BASE = "https://oo.openonion.ai"


def _get_api_key() -> str:
    """Get OPENONION_API_KEY from env or .env files."""
    if api_key := os.getenv("OPENONION_API_KEY"):
        return api_key

    for env_path in [Path(".env"), Path.home() / ".co" / "keys.env"]:
        if env_path.exists():
            load_dotenv(env_path)
            if api_key := os.getenv("OPENONION_API_KEY"):
                return api_key
    return None


def handle_deploy():
    """Deploy agent to ConnectOnion Cloud."""
    console.print("\n[cyan]Deploying to ConnectOnion Cloud...[/cyan]\n")

    project_dir = Path.cwd()

    # Must be a git repo
    if not (project_dir / ".git").exists():
        console.print("[red]Not a git repository. Run 'git init' first.[/red]")
        return

    # Must be a ConnectOnion project
    config_path = Path(".co") / "config.toml"
    if not config_path.exists():
        console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
        return

    # Must have API key
    api_key = _get_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
        return

    config = toml.load(config_path)
    project_name = config.get("project", {}).get("name", "unnamed-agent")
    secrets_path = config.get("project", {}).get("secrets", ".env")
    entrypoint = config.get("deploy", {}).get("entrypoint", "agent.py")

    # Load secrets from .env
    secrets = dotenv_values(secrets_path) if Path(secrets_path).exists() else {}

    # Create tarball from git
    tarball_path = Path(tempfile.mkdtemp()) / "agent.tar.gz"
    subprocess.run(
        ["git", "archive", "--format=tar.gz", "-o", str(tarball_path), "HEAD"],
        cwd=project_dir,
        check=True,
    )

    console.print(f"  Project: {project_name}")
    console.print(f"  Secrets: {len(secrets)} keys")
    console.print()

    # Upload
    console.print("Uploading...")
    with open(tarball_path, "rb") as f:
        response = requests.post(
            f"{API_BASE}/api/v1/deploy",
            files={"package": ("agent.tar.gz", f, "application/gzip")},
            data={
                "project_name": project_name,
                "secrets": str(secrets),
                "entrypoint": entrypoint,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    if response.status_code != 200:
        console.print(f"[red]Deploy failed: {response.text}[/red]")
        return

    deployment_id = response.json().get("id")

    # Wait for deployment
    console.print("Building...")
    for _ in range(100):
        status_resp = requests.get(
            f"{API_BASE}/api/v1/deploy/{deployment_id}/status",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if status_resp.status_code != 200:
            break
        status = status_resp.json().get("status")
        if status == "running":
            break
        if status == "error":
            console.print(f"[red]{status_resp.json().get('error_message')}[/red]")
            return
        time.sleep(3)

    url = response.json().get("url", "")
    console.print()
    console.print("[bold green]Deployed![/bold green]")
    console.print(f"Agent URL: {url}")
    console.print()
