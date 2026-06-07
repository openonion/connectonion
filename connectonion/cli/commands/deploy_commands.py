"""
Purpose: Deploy agent projects to ConnectOnion Cloud with git archive packaging and env vars
LLM-Note:
  Dependencies: imports from [os, subprocess, tempfile, time, yaml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → validates git repo and .co/host.yaml → load_api_key() loads OPENONION_API_KEY → reads host.yaml for project name, entrypoint, env file path → dotenv_values() loads env vars from .env → git archive creates tarball of HEAD → POST to /api/v1/deploy with tarball + project_name + env_vars → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | reads .co/host.yaml, .env files | makes network POST request | prints progress to stdout via rich.Console | does not modify project files
  Integration: exposes handle_deploy() for CLI | expects git repo with .co/host.yaml (name, entrypoint, env) | uses Bearer token auth | returns void (prints results)
  Performance: git archive is fast | network timeout 600s for upload, 10s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not git repo | fails if not ConnectOnion project (no host.yaml) | fails if no API key | prints backend error messages
"""

import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
import yaml
import requests
from pathlib import Path
from rich.console import Console
from dotenv import dotenv_values

from .project_cmd_lib import load_api_key

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


def _should_skip_deploy_path(rel: Path) -> bool:
    """Return True for local-only files that must not be uploaded."""
    parts = rel.parts
    if not parts:
        return True
    if any(part in {".git", "__pycache__", "node_modules", "dist", "build"} for part in parts):
        return True
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return True
    if parts[0] == ".co" and len(parts) > 1 and parts[1] in {"keys", "cache", "logs", "history", "docs"}:
        return True
    return rel.suffix in {".pyc", ".pyo"}


def _iter_git_tracked_files(project_dir: Path) -> list[Path]:
    """Return tracked files, using current working-tree contents."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    return [
        Path(raw.decode())
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def _is_git_repo(project_dir: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project_dir,
        capture_output=True,
    )
    return result.returncode == 0 and result.stdout.strip() == b"true"


def _add_tree(tar: tarfile.TarFile, source: Path, arc_prefix: Path) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = arc_prefix / path.relative_to(source)
        if _should_skip_deploy_path(rel):
            continue
        tar.add(path, arcname=str(rel), recursive=False)


def _build_tarball(project_dir: Path, skills_paths: list[Path]) -> Path:
    """Package git-tracked files when available, otherwise the initialized folder.

    .env is read separately as deploy secrets and is never included in the package.
    External --skills directories are overlaid under .co/skills/ with the same
    deny rules applied recursively.
    """
    tarball = Path(tempfile.mkdtemp()) / "agent.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        if _is_git_repo(project_dir):
            for rel in sorted(_iter_git_tracked_files(project_dir)):
                if _should_skip_deploy_path(rel):
                    continue
                path = project_dir / rel
                if path.is_file():
                    tar.add(path, arcname=str(rel), recursive=False)
        else:
            for path in sorted(project_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(project_dir)
                if _should_skip_deploy_path(rel):
                    continue
                tar.add(path, arcname=str(rel), recursive=False)
        for skills_path in skills_paths:
            for item in sorted(skills_path.iterdir()):
                if item.name.startswith("."):
                    continue  # skip .git/.gitignore etc — only skill dirs
                if item.is_file():
                    rel = Path(".co") / "skills" / item.name
                    if not _should_skip_deploy_path(rel):
                        tar.add(item, arcname=str(rel), recursive=False)
                elif item.is_dir():
                    _add_tree(tar, item, Path(".co") / "skills" / item.name)
    return tarball


def handle_deploy(template: str | None = None, skills: list[str] | None = None):
    """Deploy agent to ConnectOnion Cloud."""
    console.print("\n[cyan]Deploying to ConnectOnion Cloud...[/cyan]\n")

    if template and template != "co-ai":
        console.print(f"[red]Unknown deploy template: {template}. Only 'co-ai' is supported.[/red]")
        return
    project_dir = Path.cwd()

    # Must be a ConnectOnion project
    host_yaml_path = Path(".co") / "host.yaml"

    if not host_yaml_path.exists():
        console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
        return

    skills_paths = [Path(s) for s in (skills or [])]
    for sp in skills_paths:
        if not sp.is_dir():
            console.print(f"[red]Skills path not found or not a directory: {sp}[/red]")
            return

    # Must have API key
    api_key = load_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
        return

    # Load config from host.yaml
    with open(host_yaml_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    project_name = config.get("name", "unnamed-agent")
    env_file = config.get("env", ".env")
    entrypoint = config.get("entrypoint", "agent.py")

    # Validate entrypoint exists
    if not Path(entrypoint).exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print("[dim]Set 'entrypoint' in .co/host.yaml[/dim]")
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

    # Load env vars from .env (user's API keys, config for the agent container)
    env_vars = dotenv_values(env_file) if Path(env_file).exists() else {}

    # Package source. Git projects upload tracked files with current working-tree
    # contents; non-git projects upload the initialized folder. Either way .env is
    # sent as secrets below, never included in the tarball, and --skills merge in.
    tarball_path = _build_tarball(project_dir, skills_paths)

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
    console.print(f"  Env vars: {len(env_vars)} keys")
    console.print()

    # Upload
    console.print("Uploading...")
    deploy_data = {
        "project_name": project_name,
        "secrets": json.dumps(env_vars),
        "entrypoint": entrypoint,
    }
    with open(tarball_path, "rb") as f:
        response = requests.post(
            f"{API_BASE}/api/v1/deploy",
            files={"package": ("agent.tar.gz", f, "application/gzip")},
            data=deploy_data,
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
            console.print(f"[red]Deploy failed: {result.get('error_message') or 'Unknown error'}[/red]")
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

    # Show the agent's startup logs (best-effort).
    if deployment_id:
        time.sleep(5)  # "running" fires when the container starts; wait for the app to print its banner or crash
        try:
            logs_resp = requests.get(
                f"{API_BASE}/api/v1/deploy/{deployment_id}/logs?tail=20",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
        except requests.exceptions.RequestException:
            logs_resp = None
        if logs_resp is not None and logs_resp.status_code == 200:
            logs = logs_resp.json().get("logs", "")
            if logs:
                console.print()
                console.print("[dim]Container logs:[/dim]")
                console.print(f"[dim]{logs}[/dim]")

    console.print()
