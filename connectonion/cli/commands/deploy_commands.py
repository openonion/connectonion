"""
Purpose: Deploy agent projects to ConnectOnion Cloud with git archive packaging and secrets management
LLM-Note:
  Dependencies: imports from [os, subprocess, tempfile, time, toml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → validates git repo and .co/config.toml → _get_api_key() loads OPENONION_API_KEY → reads config.toml for project name and secrets path → dotenv_values() loads secrets from .env → git archive creates tarball of HEAD → POST to /api/v1/deploy with tarball + project_name + secrets → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | reads .co/config.toml, .env files | makes network POST request | prints progress to stdout via rich.Console | does not modify project files
  Integration: exposes handle_deploy() for CLI | expects git repo with .co/config.toml containing project.name, project.secrets, deploy.entrypoint | uses Bearer token auth | returns void (prints results)
  Performance: git archive is fast | network timeout 600s for upload+build, 10s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not git repo | fails if not ConnectOnion project (.co/config.toml missing) | fails if no API key | prints backend error messages
"""

import json
import os
import re
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


def _check_host_export(entrypoint: str) -> bool:
    """Check if entrypoint file exports an ASGI app via host().

    Looks for patterns like:
    - host(agent)
    - host(my_agent)
    - from connectonion import host
    """
    entrypoint_path = Path(entrypoint)
    if not entrypoint_path.exists():
        return False

    content = entrypoint_path.read_text()

    # Check for host() call pattern
    # Matches: host(agent), host(my_agent), host( agent ), etc.
    host_call_pattern = r'\bhost\s*\([^)]+\)'

    if re.search(host_call_pattern, content):
        return True

    return False


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

    # Validate entrypoint exists
    if not Path(entrypoint).exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print("[dim]Set entrypoint in .co/config.toml under [deploy][/dim]")
        return

    # Validate entrypoint exports ASGI app via host()
    if not _check_host_export(entrypoint):
        console.print(f"[red]Entrypoint '{entrypoint}' does not export an ASGI app.[/red]")
        console.print()
        console.print("[yellow]To deploy, your agent must call host():[/yellow]")
        console.print()
        console.print("  [cyan]from connectonion import Agent, host[/cyan]")
        console.print()
        console.print("  [cyan]agent = Agent('my-agent', ...)[/cyan]")
        console.print("  [cyan]host(agent)  # Starts HTTP server[/cyan]")
        console.print()
        console.print("[dim]See: https://docs.connectonion.com/deploy[/dim]")
        return

    # Load secrets from .env
    secrets = dotenv_values(secrets_path) if Path(secrets_path).exists() else {}

    # Create tarball from git
    tarball_path = Path(tempfile.mkdtemp()) / "agent.tar.gz"
    subprocess.run(
        ["git", "archive", "--format=tar.gz", "-o", str(tarball_path), "HEAD"],
        cwd=project_dir,
        check=True,
    )

    # Show package size
    tarball_size = tarball_path.stat().st_size
    if tarball_size < 1024:
        size_str = f"{tarball_size} B"
    elif tarball_size < 1024 * 1024:
        size_str = f"{tarball_size / 1024:.1f} KB"
    else:
        size_str = f"{tarball_size / (1024 * 1024):.2f} MB"

    console.print(f"  Project: {project_name}")
    console.print(f"  Package: {size_str}")
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
                "secrets": json.dumps(secrets),
                "entrypoint": entrypoint,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=600,  # 10 minutes for docker build
        )

    if response.status_code != 200:
        console.print(f"[red]Deploy failed: {response.text}[/red]")
        return

    result = response.json()

    # Check for error response (backend returns 200 with error dict)
    if "error" in result:
        console.print(f"[red]Deploy failed: {result['error']}[/red]")
        return

    deployment_id = result.get("id")
    url = result.get("url", "")

    # Wait for deployment
    console.print("Building...")
    deploy_success = False
    final_status = "unknown"
    timeout_count = 0

    for _ in range(100):
        try:
            status_resp = requests.get(
                f"{API_BASE}/api/v1/deploy/{deployment_id}/status",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,  # Increased timeout for slow SSH
            )
        except requests.exceptions.Timeout:
            timeout_count += 1
            if timeout_count >= 3:
                console.print("[yellow]Status checks timing out, but deploy may still succeed.[/yellow]")
                break
            time.sleep(3)
            continue
        except requests.exceptions.RequestException as e:
            console.print(f"[yellow]Network error: {e}[/yellow]")
            time.sleep(3)
            continue

        if status_resp.status_code != 200:
            console.print(f"[red]Status check failed: {status_resp.status_code}[/red]")
            break

        result = status_resp.json()
        final_status = result.get("status", "unknown")

        if final_status == "running":
            deploy_success = True
            # Update URL from status response (may be more up-to-date)
            url = result.get("url") or url
            break
        if final_status in ("error", "failed"):
            console.print(f"[red]Deploy failed: {result.get('error_message', 'Unknown error')}[/red]")
            return
        time.sleep(3)

    console.print()
    if deploy_success:
        console.print("[bold green]Deployed![/bold green]")
    else:
        console.print(f"[yellow]Deploy status: {final_status}[/yellow]")
        console.print("[yellow]Check status with 'co deployments' or try again.[/yellow]")

    # Always show URL if we have one
    if url:
        console.print(f"Agent URL: {url}")
    console.print()
