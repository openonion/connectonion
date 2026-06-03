"""
Purpose: Deploy agent projects to ConnectOnion Cloud with git archive packaging and env vars
LLM-Note:
  Dependencies: imports from [json, re, subprocess, tempfile, time, yaml, requests, pathlib, rich.console, deploy_co_ai] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → resolves project vs co-ai template → load_api_key() loads OPENONION_API_KEY → reads optional host.yaml/env → builds project git archive or generated co-ai package → POST to /api/v1/deploy with tarball + project_name + env vars/secrets → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | reads .co/host.yaml, .env files | makes network POST request | prints progress to stdout via rich.Console | does not modify project files
  Integration: exposes handle_deploy() for CLI | project deploy expects git repo with .co/host.yaml | co-ai deploy can generate a self-contained package from selected skills | uses Bearer token auth | returns void (prints results)
  Performance: git archive is fast | network timeout 600s for upload, 10s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not git repo | fails if not ConnectOnion project (no host.yaml) | fails if no API key | prints backend error messages
"""

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests
import yaml
from rich.console import Console

from .deploy_co_ai import (
    CO_AI_ENTRYPOINT,
    DEPLOY_ENV_KEY_ALLOWLIST,
    DeployConfigError,
    DeployPackage,
    create_co_ai_deploy_package,
    discover_deploy_skill_names,
    load_deploy_env_vars,
    parse_skill_names,
    resolve_deploy_skill,
    validate_deploy_name,
)
from .project_cmd_lib import load_api_key

console = Console()

API_BASE = "https://oo.openonion.ai"

__all__ = [
    "CO_AI_ENTRYPOINT",
    "DEPLOY_ENV_KEY_ALLOWLIST",
    "DeployConfigError",
    "DeployPackage",
    "create_deploy_package",
    "discover_deploy_skill_names",
    "handle_deploy",
    "load_deploy_env_vars",
    "parse_skill_names",
    "resolve_deploy_skill",
    "resolve_deploy_template",
    "validate_deploy_name",
]


def _archive_git_head(project_dir: Path, tarball_path: Path, *, gzip: bool) -> None:
    fmt = "tar.gz" if gzip else "tar"
    subprocess.run(
        ["git", "archive", f"--format={fmt}", "-o", str(tarball_path), "HEAD"],
        cwd=project_dir,
        check=True,
    )


def create_deploy_package(
    *,
    project_dir: Path,
    template: str,
    skills: list[str],
    all_skills: bool = False,
    project_name: str,
    entrypoint: str,
    model: str,
    max_iterations: int,
) -> DeployPackage:
    """Build the tarball sent to the deploy API."""
    if template == "project":
        temp_dir = Path(tempfile.mkdtemp())
        tarball_path = temp_dir / "agent.tar.gz"
        _archive_git_head(project_dir, tarball_path, gzip=True)
        return DeployPackage(tarball_path=tarball_path, entrypoint=entrypoint)

    if template == "co-ai":
        return create_co_ai_deploy_package(
            project_dir=project_dir,
            skills=skills,
            all_skills=all_skills,
            project_name=project_name,
            model=model,
            max_iterations=max_iterations,
        )

    raise DeployConfigError("Unsupported deploy template. Use 'project' or 'co-ai'.")


def resolve_deploy_template(
    template: str,
    skill_names: list[str],
    project_dir: Path,
    *,
    all_skills: bool = False,
) -> str:
    """Resolve the user-facing deploy mode."""
    if template == "auto":
        if skill_names or all_skills:
            return "co-ai"
        if (project_dir / ".git").exists() or (project_dir / ".co" / "host.yaml").exists():
            return "project"
        return "co-ai"

    if template in ("project", "co-ai"):
        return template

    raise DeployConfigError("Unsupported deploy template. Use 'auto', 'project', or 'co-ai'.")


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


def handle_deploy(
    name: str | None = None,
    template: str = "auto",
    skills: list[str] | None = None,
    all_skills: bool = False,
    model: str = "co/gemini-3-flash-preview",
    max_iterations: int = 100,
):
    """Deploy agent to ConnectOnion Cloud."""
    console.print("\n[cyan]Deploying to ConnectOnion Cloud...[/cyan]\n")

    project_dir = Path.cwd()
    skill_names = parse_skill_names(skills)

    try:
        deploy_template = resolve_deploy_template(
            template,
            skill_names,
            project_dir,
            all_skills=all_skills,
        )
    except DeployConfigError as e:
        console.print(f"[red]{e}[/red]")
        return

    if deploy_template == "project" and skill_names:
        console.print("[red]--skills requires --template co-ai[/red]")
        return
    if deploy_template == "project" and all_skills:
        console.print("[red]--all-skills requires --template co-ai[/red]")
        return

    host_yaml_path = Path(".co") / "host.yaml"
    config = {}

    if deploy_template == "project":
        # Must be a git repo
        if not (project_dir / ".git").exists():
            console.print("[red]Not a git repository. Run 'git init' first.[/red]")
            return

        # Must be a ConnectOnion project
        if not host_yaml_path.exists():
            console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
            return

    # Must have API key
    api_key = load_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
        return

    if host_yaml_path.exists():
        with open(host_yaml_path, 'r') as f:
            config = yaml.safe_load(f) or {}

    if name is not None:
        project_name = validate_deploy_name(name)
    elif deploy_template == "co-ai":
        project_name = "co-ai"
    else:
        project_name = config.get("name", "unnamed-agent")
    env_file = config.get("env", ".env")
    entrypoint = config.get("entrypoint", "agent.py" if deploy_template == "project" else CO_AI_ENTRYPOINT)

    if deploy_template == "project":
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
    env_vars = load_deploy_env_vars(env_file)
    if deploy_template == "co-ai" and api_key and "OPENONION_API_KEY" not in env_vars:
        env_vars["OPENONION_API_KEY"] = api_key

    try:
        package = create_deploy_package(
            project_dir=project_dir,
            template=deploy_template,
            skills=skill_names,
            all_skills=all_skills,
            project_name=project_name,
            entrypoint=entrypoint,
            model=model,
            max_iterations=max_iterations,
        )
    except DeployConfigError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Show package size
    tarball_path = package.tarball_path
    upload_entrypoint = package.entrypoint
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
    serialized_env_vars = json.dumps(env_vars)
    with open(tarball_path, "rb") as f:
        response = requests.post(
            f"{API_BASE}/api/v1/deploy",
            files={"package": ("agent.tar.gz", f, "application/gzip")},
            data={
                "project_name": project_name,
                "secrets": serialized_env_vars,
                "entrypoint": upload_entrypoint,
                "runtime": "local",
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

    # Always fetch and display container logs
    if deployment_id:
        logs_resp = requests.get(
            f"{API_BASE}/api/v1/deploy/{deployment_id}/logs?tail=20",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if logs_resp.status_code == 200:
            logs = logs_resp.json().get("logs", "")
            if logs:
                console.print()
                console.print("[dim]Container logs:[/dim]")
                console.print(f"[dim]{logs}[/dim]")

    console.print()
